import json, subprocess, collections
out = subprocess.run(["python", "jp/buyback.py", "--dry-run"], capture_output=True, text=True)
print(out.stderr[-3000:])
res = json.loads(out.stdout)
for r in res:
    print("==", r["shop"], r["status"], len(r["rows"]), r["error"][:200])
    for row in r["rows"]:
        if row["condition"] == "未開封" and row["carrier"] == "SIMフリー" and not row["color"]:
            print("  ", row["model"], row["storage"], row["price_jpy"])
