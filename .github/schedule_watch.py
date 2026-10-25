"""排程看門狗：GitHub 的 schedule 常延遲數小時、偶爾漏跑（審視 M5）。

- watch：由 watchdog.yml 每 15 分鐘左右執行。各 workflow 最近一個 cron 時間點過了 GRACE 分鐘，
  main 上卻還沒有任何一次執行（不論觸發方式）時，用 workflow_dispatch 補跑。只補最近一個時間點，不回補更早漏掉的。
- gate：放在 track.yml／jp.yml 最前面。schedule 晚到、而這個時間點已經被看門狗補跑過時輸出 run=false，避免同一時段跑兩次。

cron 直接從各 workflow 的 yml 讀，不另存一份時間表。API 出錯時一律照常執行（fail open），只留 warning。
"""
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parent / "workflows"
WATCHED = ["track.yml", "jp.yml", "column.yml", "pages.yml", "blog.yml"]
GRACE = dt.timedelta(minutes=5)
UTC = dt.timezone.utc


def parse_field(field, lo, hi):
    """cron 單一欄位 → 允許值集合；支援 *、數字、a-b、逗號、/n。"""
    values = set()
    for part in field.split(","):
        rng, _, step = part.partition("/")
        if rng == "*":
            a, b = lo, hi
        elif "-" in rng:
            a, b = map(int, rng.split("-"))
        else:
            a = b = int(rng)
        values.update(range(a, b + 1, int(step or 1)))
    return values


def parse_cron(expr):
    minute, hour, dom, month, dow = expr.split()
    return {
        "minute": parse_field(minute, 0, 59),
        "hour": parse_field(hour, 0, 23),
        "dom": parse_field(dom, 1, 31),
        "month": parse_field(month, 1, 12),
        # cron 的 0 和 7 都是週日；Python weekday() 週一＝0
        "dow": {(d - 1) % 7 for d in parse_field(dow.replace("7", "0"), 0, 6)},
        "dom_any": dom == "*",
        "dow_any": dow == "*",
    }


def matches(c, t):
    if t.minute not in c["minute"] or t.hour not in c["hour"] or t.month not in c["month"]:
        return False
    dom_ok, dow_ok = t.day in c["dom"], t.weekday() in c["dow"]
    if c["dom_any"] or c["dow_any"]:
        return dom_ok and dow_ok
    return dom_ok or dow_ok  # 兩欄都有指定時 cron 取聯集


def last_slot(crons, now):
    """now 之前（含）最近一個排程時間點（UTC），往回找 8 天。"""
    t = now.astimezone(UTC).replace(second=0, microsecond=0)
    parsed = [parse_cron(e) for e in crons]
    for _ in range(8 * 24 * 60):
        if any(matches(c, t) for c in parsed):
            return t
        t -= dt.timedelta(minutes=1)
    return None


def crons_of(workflow):
    text = (WORKFLOWS / workflow).read_text(encoding="utf-8")
    return re.findall(r'^\s*-\s*cron:\s*["\']([^"\']+)["\']', text, re.M)


def gh_api(path):
    out = subprocess.run(["gh", "api", path], check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def runs_since(repo, workflow, since):
    created = since.strftime("%Y-%m-%dT%H:%M:%SZ")
    data = gh_api(f"repos/{repo}/actions/workflows/{workflow}/runs?branch=main&per_page=20&created=%3E%3D{created}")
    return data.get("workflow_runs", [])


def counted(runs):
    """被取消的執行（concurrency 排隊時被較新的一次取代）不算這一輪跑過。"""
    return [r for r in runs if r.get("conclusion") != "cancelled"]


def needs_dispatch(slot, runs, now, grace=GRACE):
    return slot is not None and now - slot >= grace and not counted(runs)


def watch(repo, now):
    for wf in WATCHED:
        slot = last_slot(crons_of(wf), now)
        try:
            runs = runs_since(repo, wf, slot)
        except (subprocess.CalledProcessError, ValueError) as e:
            print(f"::warning::{wf} 查詢執行紀錄失敗：{e}")
            continue
        if not needs_dispatch(slot, runs, now):
            print(f"{wf}：{slot:%m-%d %H:%M} UTC 這一輪已有 {len(counted(runs))} 次執行，或還沒到時間。")
            continue
        late = int((now - slot).total_seconds() // 60)
        try:
            subprocess.run(["gh", "workflow", "run", wf, "--repo", repo, "--ref", "main"], check=True)
            print(f"::notice::{wf}：{slot:%m-%d %H:%M} UTC 的排程過了 {late} 分鐘還沒跑，已補跑。")
        except subprocess.CalledProcessError as e:
            print(f"::warning::{wf} 補跑失敗：{e}")


def should_run(slot, runs, own_number):
    """schedule 觸發時：同一時間點已有「更早建立」的執行（看門狗補跑或手動）就不再跑。

    只看 run_number 比自己小的：較晚建立、還在 concurrency 排隊（pending）的不算，
    否則兩次同時排隊會互相看到對方而都略過。較早那次若也被 gate 略過，代表再更早還有一次真的跑了。
    """
    own = int(own_number or 0)
    return slot is None or not [r for r in counted(runs) if int(r.get("run_number") or 0) < own]


def gate(repo, workflow, now):
    run = True
    if os.environ.get("GITHUB_EVENT_NAME") == "schedule":
        slot = last_slot(crons_of(workflow), now)
        try:
            run = should_run(slot, runs_since(repo, workflow, slot), os.environ.get("GITHUB_RUN_NUMBER"))
        except (subprocess.CalledProcessError, ValueError) as e:
            print(f"::warning::查詢執行紀錄失敗，照常執行：{e}")
        if not run:
            print(f"::notice::{slot:%m-%d %H:%M} UTC 這一輪已經跑過（看門狗補跑或手動），這次晚到的排程略過。")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"run={'true' if run else 'false'}\n")
    print(f"run={run}")


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=["watch", "gate"])
    p.add_argument("workflow", nargs="?")
    a = p.parse_args(argv)
    repo = os.environ["GITHUB_REPOSITORY"]
    now = dt.datetime.now(UTC)
    if a.mode == "watch":
        watch(repo, now)
    else:
        gate(repo, a.workflow, now)


if __name__ == "__main__":
    sys.exit(main())
