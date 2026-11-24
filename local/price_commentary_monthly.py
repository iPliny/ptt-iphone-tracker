#!/usr/bin/env python3
"""每月底在家用 Mac 更新機型頁「價格短評」：Codex 寫好的 facts → agy（Gemini）寫稿 → 驗稿 →
寫入私人資料庫 commentary/price.json → 推送並觸發網站部署。

launchd 每天跑一次；不是月底（也沒有漏掉的上個月）就直接結束。--force 可指定月份手動重跑。
"""
import argparse
import calendar
import fcntl
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent.parent
# 專用 clone，不與本機爬蟲（local/run.sh）共用工作目錄，避免兩邊的 Git 操作互相干擾。
DATA_DIR = Path(os.environ.get("PTT_COMMENTARY_DATA_DIR",
                               Path.home() / "Documents/Codex/dispatch/ptt-iphone-data-commentary"))
DATA_REMOTE = "https://github.com/iPliny/ptt-iphone-data.git"
MODEL = os.environ.get("PTT_AGY_MODEL", "gemini-4-neon-medium")
AGY = os.environ.get("PTT_AGY") or str(Path.home() / ".local/bin/agy")
LOG = Path.home() / "Library/Logs/ptt-price-commentary.log"
LOCK = Path.home() / "Library/Application Support/crawlsnek/ptt-price-commentary.lock"
TAIPEI = timezone(timedelta(hours=8))
FIX_ROUNDS = 3


def log(message):
    line = f"{datetime.now(TAIPEI).isoformat(timespec='seconds')} {message}"
    print(line, flush=True)


def run(cmd, **kwargs):
    return subprocess.run(cmd, check=True, text=True, capture_output=True, **kwargs)


def python():
    venv = CODE_DIR / ".venv/bin/python"
    return str(venv) if venv.exists() else sys.executable


def target_month(today, force):
    """回傳 (YYYY-MM, 資料截止日)；今天不需要更新時回傳 None。"""
    if force:
        year, month = map(int, force.split("-"))
        last = calendar.monthrange(year, month)[1]
        end = datetime(year, month, last).date()
        return force, min(end, today).isoformat()
    last_day = calendar.monthrange(today.year, today.month)[1]
    if today.day == last_day:
        return f"{today.year}-{today.month:02d}", today.isoformat()
    prev = today.replace(day=1) - timedelta(days=1)  # 月初補跑上個月
    return f"{prev.year}-{prev.month:02d}", prev.isoformat()


def published_as_of():
    """遠端 main 上已發布的稿件日期（尚未產生時為空字串）。"""
    try:
        return json.loads(git("show", "origin/main:commentary/price.json")).get("as_of") or ""
    except subprocess.CalledProcessError:
        return ""


def ensure_clone():
    if not (DATA_DIR / ".git").exists():
        DATA_DIR.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", DATA_REMOTE, str(DATA_DIR)])


def agy_json(prompt, scratch):
    """呼叫 agy 要 JSON 物件；有被拒絕的動作就視為失敗。"""
    out = run([AGY, "-p", prompt, "--model", MODEL, "--mode", "plan", "--add-dir", str(scratch),
               "--output-format", "json", "--print-timeout", "900s"], cwd=CODE_DIR, stdin=subprocess.DEVNULL).stdout
    result = json.loads(out)
    if result.get("denied_actions"):
        raise RuntimeError(f"agy 有被拒絕的動作：{result['denied_actions']}")
    text = re.sub(r"^```(?:json)?|```$", "", (result.get("response") or "").strip(), flags=re.M).strip()
    return json.loads(text)


def length(text):
    return len("".join(text.split()))


def write_draft(data_dir, month, as_of, models):
    path = data_dir / "commentary/price.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({"month": month, "as_of": as_of, "models": models},
                               ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def check(data_dir):
    p = subprocess.run([python(), str(CODE_DIR / "site/price_commentary.py"), "check", "--data", str(data_dir)],
                       text=True, capture_output=True)
    return p.returncode == 0, p.stderr.strip()


def generate(month, as_of, scratch):
    facts = scratch / "facts.json"
    run([python(), str(CODE_DIR / "site/price_commentary.py"), "facts", "--data", str(DATA_DIR),
         "--month", month, "--as-of", as_of, "--out", str(facts)])
    label = f"{int(month[5:])} 月"
    prompt = (CODE_DIR / "local/price_commentary_prompt.txt").read_text(encoding="utf-8") \
        .replace("{FACTS}", str(facts)).replace("{AS_OF}", as_of).replace("{MONTH_LABEL}", label)
    models = agy_json(prompt, scratch)
    for round_no in range(FIX_ROUNDS):
        bad = {k: {"目前字數": length(v), "原文": v} for k, v in models.items()
               if not isinstance(v, str) or not 250 <= length(v) <= 300}
        if not bad:
            break
        log(f"第 {round_no + 1} 輪修字數：{len(bad)} 則")
        (scratch / "fix.json").write_text(json.dumps(bad, ensure_ascii=False, indent=1), encoding="utf-8")
        fix_prompt = (f"讀取 {scratch}/fix.json 與 {facts}（絕對路徑）。每個機型的短評字數不在 250–300 字（不含空白）。"
                      "請改寫成約 275 字（目標 265–290，寧可落在中間）：不足的用 facts 內的事實補充（不可編造），"
                      "過長的刪次要句子；保留文風與已有事實，樣本少的機型維持「樣本太少僅供參考」的誠實說法。"
                      "單一段落純文字、只用 facts 的數字、不給買賣建議、不出現人名帳號。不要執行任何指令。"
                      "只輸出一個 JSON 物件，鍵為機型名稱，值為改寫後文字，不要程式碼區塊。")
        models.update(agy_json(fix_prompt, scratch))
    return models


def git(*args):
    return run(["git", "-C", str(DATA_DIR), *args]).stdout.strip()


def push_with_retry():
    for attempt in range(4):
        try:
            git("push", "origin", "main")
            return
        except subprocess.CalledProcessError as error:
            log(f"push 失敗（第 {attempt + 1} 次）：{error.stderr.strip()[:200]}")
            git("pull", "--rebase", "origin", "main")
    raise RuntimeError("push 重試 4 次仍失敗")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", metavar="YYYY-MM", help="指定月份強制重跑")
    parser.add_argument("--dry-run", action="store_true", help="只產稿到暫存目錄驗證，不改資料庫")
    args = parser.parse_args()
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    lock = LOCK.open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("另一輪正在執行，結束。")
        return 0
    today = datetime.now(TAIPEI).date()
    target = target_month(today, args.force)
    month, as_of = target
    ensure_clone()
    if git("branch", "--show-current") != "main":
        raise RuntimeError("私人資料庫不在 main 分支")
    if git("status", "--porcelain"):
        raise RuntimeError("私人資料庫有未提交變更，停止")
    git("fetch", "origin", "main")
    if git("rev-list", "origin/main..HEAD") and not args.dry_run:  # 上次已 commit 但沒推送成功：先補推送與部署
        git("pull", "--rebase", "origin", "main")
        push_with_retry()
        run(["gh", "workflow", "run", "pages.yml", "--repo", "iPliny/ptt-iphone-tracker", "--ref", "main"])
        log("補推送上次未完成的短評並觸發部署。")
    if not args.force and published_as_of() >= as_of:
        return 0  # 這個月底（或更晚）的稿已經發布
    if not args.force and today.day != calendar.monthrange(today.year, today.month)[1] and today.day > 3:
        return 0  # 非月底也非月初補跑期間
    log(f"開始更新 {month} 價格短評（資料截至 {as_of}）")
    git("pull", "--rebase", "origin", "main")
    with tempfile.TemporaryDirectory(prefix="price-commentary-") as tmp:
        models = generate(month, as_of, Path(tmp))
        write_draft(DATA_DIR, month, as_of, models)
    ok, errors = check(DATA_DIR)
    if not ok:
        git("checkout", "--", ".")
        git("clean", "-fdq", "commentary")
        raise RuntimeError("驗稿未通過：\n" + errors[:1500])
    if args.dry_run:
        git("checkout", "--", ".")
        git("clean", "-fdq", "commentary")
        log("dry-run 完成，稿件通過驗證，資料庫已還原。")
        return 0
    git("add", "commentary/price.json")
    git("commit", "-m", f"價格短評 {month}（截至 {as_of}）")
    push_with_retry()
    run(["gh", "workflow", "run", "pages.yml", "--repo", "iPliny/ptt-iphone-tracker", "--ref", "main"])
    log("完成：已推送並觸發網站部署。")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:  # 通知後讓 launchd 記為失敗
        log(f"失敗：{error}")
        subprocess.run(["osascript", "-e", 'display notification "價格短評月更失敗，請看 ~/Library/Logs/ptt-price-commentary.log" with title "PTT 追蹤器"'])
        sys.exit(1)
