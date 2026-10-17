"""暫時的探測 2：看イオシス商品一覧頁的價格與分頁標記。不寫任何資料。"""
import re
from curl_cffi import requests

url = "https://iosys.co.jp/items/smartphone/iphone/simfree/iphone17_pro_a3522"
text = requests.get(url, impersonate="chrome", headers={"Accept-Language": "ja-JP,ja;q=0.9"}, timeout=45).text
i = text.find("(MG874J/A) 256GB")
print("SNIPPET1", re.sub(r"\s+", " ", text[i-1500:i+2500]))
print("YEN-like:", re.findall(r"[0-9]{1,3}(?:,[0-9]{3})+\s*(?:<[^>]+>\s*)*(?:円|yen)", text)[:10])
print("tax:", re.findall(r".{0,60}税込.{0,60}", text)[:5])
print("pager:", re.findall(r'href="[^"]*page=\d+[^"]*"', text)[:10])
print("count:", re.findall(r".{0,40}件.{0,40}", text)[:8])
print("ld+json:", [m[:300] for m in re.findall(r'<script type="application/ld\+json">(.*?)</script>', text, re.S)][:3])
