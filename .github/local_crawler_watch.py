"""雲端檢查本機買取成功時間；只公開店名與時間，不公開原始列或錯誤。"""
import argparse
import csv
import datetime as dt
import json
import subprocess
from pathlib import Path

SHOPS = ("モバステ", "イオシス")
TITLE = "本機爬蟲停更告警"
REPO = "iPliny/ptt-iphone-tracker"
LIMIT = dt.timedelta(hours=14)


def latest_success(path, now):
    latest = {shop: None for shop in SHOPS}
    if not Path(path).is_file():
        return latest
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            shop = row.get("shop")
            if shop not in latest or row.get("status") != "ok":
                continue
            try:
                when = dt.datetime.fromisoformat(row.get("run_at", ""))
            except ValueError:
                continue
            # 無時區或未來紀錄不能當成健康證據。
            if when.tzinfo is None or when > now:
                continue
            if latest[shop] is None or when > latest[shop]:
                latest[shop] = when
    return latest


def report(latest, now):
    stale = [shop for shop, when in latest.items() if when is None or now - when > LIMIT]
    lines = [f"檢查時間：{now.isoformat(timespec='seconds')}",
             "超過 14 小時未成功：" + "、".join(stale) if stale else "兩家本機店皆已恢復（14 小時內成功）。"]
    for shop, when in latest.items():
        stamp = when.isoformat(timespec="seconds") if when else "無有效成功紀錄"
        lines.append(f"- {shop}：最後成功 {stamp}")
    return stale, "\n\n".join(lines)


def gh(*args):
    result = subprocess.run(["gh", *args], text=True, capture_output=True)
    if result.returncode:
        # gh 的 stderr 可能包含私人 checkout／內部資訊，不轉印。
        raise RuntimeError("GitHub 告警 API 失敗")
    return result.stdout


def open_alerts(api=gh):
    pages = json.loads(api("api", "--paginate", "--slurp",
                           f"repos/{REPO}/issues?state=open&per_page=100"))
    return [issue for page in pages for issue in page
            if issue.get("title") == TITLE and "pull_request" not in issue]


def reconcile(stale, body, issues, api=gh):
    if not issues:
        if stale:
            api("issue", "create", "--repo", REPO, "--title", TITLE, "--body", body + "\n\n<!-- stale-shops:" +
                json.dumps(sorted(stale), ensure_ascii=False) + " -->")
        return
    # 狀態保存在內文，停更集合不變時只更新內文，不發留言通知。
    marker = "<!-- stale-shops:" + json.dumps(sorted(stale), ensure_ascii=False) + " -->"
    for issue in issues:
        number = issue["number"]
        previous = issue.get("body") or ""
        api("issue", "edit", str(number), "--repo", REPO, "--body", body + "\n\n" + marker)
        if not stale or marker not in previous:
            api("issue", "comment", str(number), "--repo", REPO, "--body", body)
        if not stale:
            api("issue", "close", str(number), "--repo", REPO)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", type=Path)
    args = parser.parse_args()
    now = dt.datetime.now(dt.timezone.utc)
    stale, body = report(latest_success(args.runs, now), now)
    reconcile(stale, body, open_alerts())


if __name__ == "__main__":
    main()
