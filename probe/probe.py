import re, time, sys, pathlib
from urllib.parse import urljoin
from curl_cffi import requests
out = pathlib.Path("probe/out"); out.mkdir(parents=True, exist_ok=True)
H = {"Accept-Language": "ja-JP,ja;q=0.9"}
last = {}
def get(url):
    host = url.split("/")[2]
    gap = 60 if "iosys" in host else 6
    if host in last:
        w = gap - (time.monotonic() - last[host])
        if w > 0: time.sleep(w)
    time.sleep(1)
    last[host] = time.monotonic()
    r = requests.get(url, impersonate="chrome", headers=H, timeout=45)
    print(r.status_code, len(r.text), url, flush=True)
    return r.text
def save(name, text): (out / name).write_text(text, encoding="utf-8")
pat = re.compile(r"iphone-?17|iphone-?air|iphone17|17pro|air", re.I)
mm = get("https://mobile-mix.jp/?category=7"); save("mobilemix.html", mm)
for shop, index in [("iosys", "https://k-tai-iosys.com/pricelist/smartphone/iphone/"),
                    ("amemoba", "https://amemoba.com/smartphone/iphone/")]:
    html = get(index); save(f"{shop}-index.html", html)
    links = sorted({urljoin(index, h) for h in re.findall(r'href="([^"]+)"', html) if pat.search(h)})
    links = [l for l in links if l.startswith(index) and l.rstrip("/") != index.rstrip("/")]
    print(shop, "links:", *links, sep="\n  ", flush=True)
    for i, link in enumerate(links[:8]):
        try:
            save(f"{shop}-{re.sub(r'[^a-z0-9-]+','_',link[len(index):].strip('/').lower())}.html", get(link))
        except Exception as e:
            print("ERR", link, e)
