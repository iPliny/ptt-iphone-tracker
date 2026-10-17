"""暫時的探測：從 Actions 抓イオシス販賣頁與 Back Market，印出狀態與價格片段。不寫任何資料。"""
import json, re, time
from curl_cffi import requests

URLS = [
    "https://iosys.co.jp/robots.txt",
    "https://iosys.co.jp/items/smartphone/iphone/simfree/iphone17_pro_a3522",
    "https://iosys.co.jp/items/smartphone/iphone/simfree/iphone17_pro_a3522/389788",
    "https://www.backmarket.co.jp/robots.txt",
    "https://www.backmarket.co.jp/ja-jp/p/iphone-17-pro",
    "https://www.backmarket.co.jp/ja-jp/p/iphone-17-pro/5316d6b9-5505-4ab5-aa99-3bca655fb6a0",
]
for url in URLS:
    for fp in ("chrome", "safari"):
        try:
            r = requests.get(url, impersonate=fp, headers={"Accept-Language": "ja-JP,ja;q=0.9"}, timeout=45)
            text = r.text
            title = re.search(r"<title[^>]*>(.*?)</title>", text, re.S)
            prices = re.findall(r"[¥￥]\s?[\d,]{5,}|[\d,]{5,}\s?円", text)
            print(f"== {fp} {r.status_code} len={len(text)} {url}")
            print("   title:", (title[1].strip()[:120] if title else None))
            print("   prices:", prices[:12], "count", len(prices))
            if url.endswith("robots.txt"):
                print(text[:1500])
            if "backmarket" in url and "robots" not in url:
                for m in re.finditer(r'"price"\s*:\s*\{[^}]{0,120}\}|"amount"\s*:\s*"?[\d.]+', text):
                    print("   json:", m[0][:160]); break
                print("   captcha/block:", bool(re.search(r"captcha|cf-chl|Just a moment|Access Denied|datadome", text, re.I)))
            if "iosys" in url and "robots" not in url:
                names = re.findall(r"iPhone17 Pro[^<]{0,80}(?:SIMフリー|ランク)[^<]{0,20}", text)
                print("   names:", names[:6], "count", len(names))
                print("   ranks:", sorted(set(re.findall(r"[SABCJ]ランク|未使用品|中古[ABC]", text)))[:12])
        except Exception as e:
            print(f"== {fp} ERROR {url}: {type(e).__name__} {e}")
        time.sleep(8)
