"""モバステ郵送買取頁；只解析 HTML，不讀寫檔案。"""
import re
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from . import buyback as jp

PASTEC_INDEX = "https://pastec.net/iphone"
PASTEC_SHOP = "モバステ"


def discover_pastec_pages(html):
    soup = BeautifulSoup(html, "html.parser")
    pages = {}
    for item in soup.select(".p-priceTable__inner"):
        name = item.select_one(".p-priceTable__name > span")
        spec = jp.model_storage(name.get_text(" ", strip=True)) if name else None
        if not spec:
            continue
        link = item.select_one('a[href*="purchase_type=net"]')
        if link is None:
            raise jp.ParseError("モバステ郵送買取の規格連結消失")
        url = urlsplit(urljoin(PASTEC_INDEX, link["href"]))
        if (url.scheme != "https" or url.netloc != "pastec.net"
                or not re.fullmatch(r"/iphone/[a-zA-Z0-9_-]+", url.path)):
            raise jp.ParseError("モバステ規格連結格式不明")
        clean = urlunsplit(("https", "pastec.net", url.path, "purchase_type=net", ""))
        if clean in pages and pages[clean] != spec:
            raise jp.ParseError("モバステ同一連結規格矛盾")
        pages[clean] = spec
    if not pages:
        raise jp.ParseError("モバステ目標機型連結為 0 筆")
    return pages


def parse_pastec(html, url):
    soup = BeautifulSoup(html, "html.parser")
    card = soup.select_one(".assess__model-card-content")
    name = card.select_one(".assess__model-card-name") if card else None
    if name is None:
        raise jp.ParseError("モバステ機型欄位消失")
    spec = jp.model_storage(name.get_text(" ", strip=True))
    if not spec:
        return [], ""
    badge = card.select_one(".assess__model-card-badges")
    version = jp.carrier_name(badge.get_text(" ", strip=True)) if badge else None
    if not version:
        raise jp.ParseError("モバステ版本不明；不推定 SIMフリー")
    table = soup.select_one("table.assess__table")
    if table is None:
        raise jp.ParseError("モバステ買取表消失")
    values = {}
    for tr in table.select("tr"):
        label, cell = tr.find("th"), tr.find("td")
        if label is None:
            continue
        condition = jp.normalized(label.get_text(" ", strip=True))
        if condition != "未開封" and not re.fullmatch(r"中古\s*[ABC]", condition):
            continue  # 開封済新品、ジャンク、不動品不混入中古上限。
        if condition in values:
            raise jp.ParseError("モバステ機況重複")
        values[condition] = jp.yen(cell)
    if "未開封" not in values or not any(k.startswith("中古") for k in values):
        raise jp.ParseError("モバステ未開封或中古機況列消失")
    updated = jp.page_date(soup)
    used = [v for k, v in values.items() if k.startswith("中古") and v is not None]
    rows = []
    for condition, price in (("未開封", values["未開封"]), ("中古上限", max(used, default=None))):
        if price is not None:
            rows.append(jp.make_row(PASTEC_SHOP, spec, condition, version, price, url, updated))
    return rows, updated
