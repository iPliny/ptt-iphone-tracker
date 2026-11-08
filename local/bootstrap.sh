#!/bin/bash
# 此檔安裝到 repo 外，避免搬動 checkout 後 launchd 失聯。
set -euo pipefail
umask 077

CONFIG_DIR="$HOME/Library/Application Support/crawlsnek"
CONFIG="$CONFIG_DIR/ptt-local-crawler.conf"
DEFAULT_BASE="$HOME/ai-cowork/ptt-local-crawler"

log() { printf '%s %s\n' "$(TZ=Asia/Tokyo date +%FT%T%z)" "$*"; }

# 外部指令設逾時；macOS 沒有 timeout 時使用系統 perl。
timed() {
    local seconds="$1"; shift
    if command -v timeout >/dev/null 2>&1; then timeout "$seconds" "$@"
    elif command -v perl >/dev/null 2>&1; then perl -e 'alarm shift; exec @ARGV or die $!' "$seconds" "$@"
    else "$@"; fi
}

# shell 保留 fd；Perl 與它共用 open-file description，退出不解鎖。
acquire_runner_lock() {
    export PTT_LOCAL_LOCK_PATH="${PTT_LOCAL_LOCK_PATH:-$CONFIG_DIR/ptt-local-crawler.lock}"
    mkdir -p "$(dirname "$PTT_LOCAL_LOCK_PATH")"
    chmod 700 "$(dirname "$PTT_LOCAL_LOCK_PATH")"
    local new_lock=0
    if [ -z "${PTT_LOCAL_LOCK_FD:-}" ]; then
        exec 9<> "$PTT_LOCAL_LOCK_PATH"
        chmod 600 "$PTT_LOCAL_LOCK_PATH"
        export PTT_LOCAL_LOCK_FD=9
        new_lock=1
    fi
    if ! /usr/bin/perl -MFcntl=:flock -e '
        open(my $lock, "+<&=$ENV{PTT_LOCAL_LOCK_FD}") or die "$!\n";
        my @actual = stat($lock); my @expected = stat($ENV{PTT_LOCAL_LOCK_PATH});
        die "invalid lock\n" unless @actual && @expected && $actual[0] == $expected[0] && $actual[1] == $expected[1];
        unless ($ARGV[0]) {
            open(my $probe, "<", $ENV{PTT_LOCAL_LOCK_PATH}) or die "$!\n";
            die "unlocked fd\n" if flock($probe, LOCK_EX | LOCK_NB);
        }
        flock($lock, LOCK_EX | LOCK_NB) or die "busy lock\n";
    ' "$new_lock"; then
        log '爬蟲正在執行，或繼承的檔案鎖無效；停止更新。' >&2
        return 1
    fi
}

find_python() {
    local python
    for python in /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
        if [ -x "$python" ]; then printf '%s\n' "$python"; return; fi
    done
    log '找不到 Python 3' >&2; return 1
}

protected_path() {
    local path home
    path="$(printf '%s' "$1/" | tr '[:upper:]' '[:lower:]')"
    home="$(printf '%s' "$(cd "$HOME" && pwd -P)" | tr '[:upper:]' '[:lower:]')"
    case "$path" in
        "$home/documents/"*|"$home/desktop/"*|"$home/downloads/"*|"$home/library/"*|"$home/.trash/"*) return 0 ;;
    esac
    return 1
}

allowed_path() {
    local path="$1"
    case "$path" in /*) ;; *) return 1 ;; esac
    local lexical_home="$HOME"
    protected_path "$path" && return 1
    path="${path/#$lexical_home/$(cd "$HOME" && pwd -P)}"
    protected_path "$path" && return 1
    while [ ! -e "$path" ] && [ "$path" != / ]; do path="$(dirname "$path")"; done
    path="$(cd "$path" 2>/dev/null && pwd -P)" || return 1
    ! protected_path "$path"
}

valid_clone() {
    local dir="$1" repo="$2" remote
    [ -d "$dir/.git" ] || return 1
    [ "$(timed 120 git -C "$dir" rev-parse --show-toplevel 2>/dev/null)" = "$(cd "$dir" && pwd -P)" ] || return 1
    for remote in "$(timed 120 git -C "$dir" remote get-url --all origin)" "$(timed 120 git -C "$dir" remote get-url --push --all origin)"; do
        case "${remote%.git}" in
            "https://github.com/iPliny/$repo"|"git@github.com:iPliny/$repo") ;;
            *) return 1 ;;
        esac
    done
}

valid_base() {
    allowed_path "$1" &&
        allowed_path "$1/ptt-iphone-tracker" && allowed_path "$1/ptt-iphone-data" &&
        valid_clone "$1/ptt-iphone-tracker" ptt-iphone-tracker &&
        valid_clone "$1/ptt-iphone-data" ptt-iphone-data
}

read_base() {
    BASE="$DEFAULT_BASE"
    BASE_EXISTED=0
    if [ -f "$CONFIG" ]; then
        # 純文字 BASE=/絕對路徑；不執行設定檔內容。
        local line
        BASE_EXISTED=1 # 舊版 conf 也代表曾安裝，不自動建立替代資料庫。
        while IFS= read -r line || [ -n "$line" ]; do
            case "$line" in BASE=*) BASE="${line#BASE=}" ;; BASE_EXISTED=0) BASE_EXISTED=0 ;; BASE_EXISTED=1) BASE_EXISTED=1 ;; esac
        done < "$CONFIG"
    fi
    allowed_path "$BASE" || { log 'BASE 不可位於 TCC 目錄或使用相對路徑'; return 1; }
}

save_base() {
    mkdir -p "$CONFIG_DIR"
    printf 'BASE=%s\nBASE_EXISTED=1\n' "$BASE" > "$CONFIG.tmp"
    mv "$CONFIG.tmp" "$CONFIG"
}

locate_base() {
    read_base
    if valid_base "$BASE"; then return; fi
    local candidate stamp best_stamp=-1 best=""
    local candidates=()
    # 不限制 BASE 名稱；從資料 clone 找父目錄。保護目錄在走訪前 prune。
    while IFS= read -r -d '' candidate; do
        candidate="$(dirname "$candidate")"
        if valid_base "$candidate"; then
            candidates+=("$candidate")
        fi
    done < <(find "$HOME" -maxdepth 5 \( -iname Documents -o -iname Desktop -o -iname Downloads -o -iname Library -o -iname .Trash -o -name .git \) -prune -o -type d -name ptt-iphone-data -print0 2>/dev/null)
    for candidate in "${candidates[@]:-}"; do
        [ -n "$candidate" ] || continue
        stamp="$(timed 120 git -C "$candidate/ptt-iphone-data" log -1 --format=%ct 2>/dev/null)" || stamp=0
        [[ "$stamp" =~ ^[0-9]+$ ]] || stamp=0
        log "有效候選：${candidate}（資料庫 commit 時間 ${stamp}）"
        if [ "$stamp" -gt "$best_stamp" ] || { [ "$stamp" -eq "$best_stamp" ] && [[ "$candidate" < "$best" ]]; }; then
            best="$candidate"; best_stamp="$stamp"
        fi
    done
    if [ -n "$best" ]; then
        BASE="$best"; save_base; log "搜尋找到爬蟲，更新 BASE：$BASE"; return
    fi
    if [ -f "$CONFIG" ] && { [ "$BASE_EXISTED" = 1 ] || [ -e "$BASE" ]; }; then
        log "嚴重錯誤：既有 BASE 失聯或無效且找不到候選，拒絕 clone：$BASE" >&2
        return 1
    fi
    # 不覆寫錯誤 origin 或非空目錄；clone 失敗時保留現場供下輪重試。
    mkdir -p "$BASE"
    for candidate in ptt-iphone-tracker ptt-iphone-data; do
        if ! valid_clone "$BASE/$candidate" "$candidate"; then
            if [ -e "$BASE/$candidate" ]; then log "clone 無效，停止而不覆寫：$BASE/$candidate"; return 1; fi
            local status=0
            timed 300 git clone "https://github.com/iPliny/$candidate.git" "$BASE/$candidate" || status=$?
            if [ "$status" -ne 0 ]; then log "嚴重錯誤：clone 失敗（exit ${status}）：$candidate" >&2; return "$status"; fi
        fi
    done
    valid_base "$BASE" || { log "clone 驗證失敗：$BASE"; return 1; }
    save_base
    log "已建立兩個 clone：$BASE"
}

main() {
    mkdir -p "$HOME/Library/Logs"
    exec >> "$HOME/Library/Logs/ptt-local-crawler.log" 2>&1
    export GIT_TERMINAL_PROMPT=0
    acquire_runner_lock
    locate_base
    local code="$BASE/ptt-iphone-tracker"
    if ! timed 120 git -C "$code" pull --ff-only; then log '程式庫 pull 失敗，沿用現有版本'; fi
    export PTT_DATA_DIR="$BASE/ptt-iphone-data"
    export PTT_PYTHON="$code/.venv/bin/python"
    if [ ! -x "$PTT_PYTHON" ]; then
        "$(find_python)" -m venv "$code/.venv"
    fi
    # 安裝中斷或依賴更新後，下輪會重試；僅成功後保存版本。
    if ! cmp -s "$code/requirements.txt" "$code/.venv/ptt-requirements.txt"; then
        timed 600 "$PTT_PYTHON" -m pip install -r "$code/requirements.txt"
        cp "$code/requirements.txt" "$code/.venv/ptt-requirements.txt"
    fi
    exec /bin/bash "$code/local/run.sh"
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then main "$@"; fi
