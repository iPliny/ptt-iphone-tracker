"""イオシス販賣列表的純 HTML 解析；販賣價與買取價分開儲存。"""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from .buyback import (ParseError, carrier_name, make_row, model_storage,
                      normalized, page_date, row_key, yen)

IOSYS_SELL_INDEX = "https://iosys.co.jp/items/smartphone/iphone"
# 原頁的 Pro 入口同時列 Pro Max；不以入口名稱將它誤記成 Pro。
IOSYS_SELL_GROUPS = {
    f"{IOSYS_SELL_INDEX}/iphone18_pro": ("iPhone 18 Pro", "iPhone 18 Pro Max"),
    f"{IOSYS_SELL_INDEX}/iphone17_pro": ("iPhone 17 Pro", "iPhone 17 Pro Max"),
    f"{IOSYS_SELL_INDEX}/iphone_air": ("iPhone Air",),
    f"{IOSYS_SELL_INDEX}/iphone17?not=pro+17e": ("iPhone 17",),
}
SELL_CONDITIONS = ("未使用品", "中古A", "中古B", "中古C")
_CONDITION_NAMES = {"未使用品": "未使用品", **{
    f"中古{grade}ランク": f"中古{grade}" for grade in "ABC"
}}


def discover_iosys_pages(html):
    """只使用目錄內實際存在的已知入口；不猜測 Duo 或其他商品網址。"""
    soup = BeautifulSoup(html, "html.parser")
    links = {urljoin(IOSYS_SELL_INDEX, a["href"])
             for a in soup.select("a[href]")}
    pages = {url: models for url, models in IOSYS_SELL_GROUPS.items() if url in links}
    if len(pages) != len(IOSYS_SELL_GROUPS):
        raise ParseError("イオシス販賣目錄的既有機型入口不完整")
    return pages


def minimum_prices(rows):
    """同店、規格、等級、版本取最低刊登價；色名不參與販賣分組。"""
    minimum = {}
    for row in rows:
        key = row_key(row)
        previous = minimum.get(key)
        if previous is None or (row["price_jpy"], row["source_url"]) < (
                previous["price_jpy"], previous["source_url"]):
            minimum[key] = row
    return [minimum[key] for key in sorted(minimum)]


def _models_for_url(url):
    path = urlsplit(url).path
    for page, models in IOSYS_SELL_GROUPS.items():
        if urlsplit(page).path == path:
            return models
    raise ParseError("イオシス販賣頁不屬於已確認的機型入口")


def parse_iosys_sell(html, url):
    soup = BeautifulSoup(html, "html.parser")
    container = soup.select_one("#ajax-item-main")
    if container is None:
        raise ParseError("イオシス販賣商品列表消失")
    allowed = _models_for_url(url)
    updated, rows = page_date(soup), []
    for item in container.select(":scope > li.item"):
        name = item.select_one(".name")
        if name is None:
            raise ParseError("イオシス販賣商品名稱消失")
        title = normalized(name.get_text(" ", strip=True))
        # 販賣標題在機型與容量間插入 A3522 (MG8D4J/A) 等硬體型號。
        spec_text = re.sub(r"\bA\d{4}\s*(?:\([A-Z0-9/]+\))?", " ", title, flags=re.I)
        spec = model_storage(spec_text)
        version = carrier_name(title)
        if not spec or spec[0] not in allowed or not version:
            continue
        condition_node = item.select_one(".condition")
        condition = _CONDITION_NAMES.get(normalized(condition_node.get_text(" ", strip=True))) if condition_node else None
        if condition is None:
            raise ParseError("イオシス販賣商品等級不明")
        price = yen(item.select_one(".price > p"))
        if price is None:
            raise ParseError("イオシス販賣商品價格不是正數")
        link = item.select_one("a[href]")
        source = urljoin(url, link["href"]) if link else ""
        parts = urlsplit(source)
        if (parts.scheme != "https" or parts.netloc != "iosys.co.jp"
                or not parts.path.startswith("/items/smartphone/iphone/")):
            raise ParseError("イオシス販賣商品連結不明")
        source = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
        rows.append(make_row("イオシス", spec, condition, version, price, source, updated))
    return minimum_prices(rows), updated


def iosys_next_page(html, url):
    """沿原頁 next 逐頁讀取，拒絕跳站、跳機型或丟掉排除條件。"""
    soup = BeautifulSoup(html, "html.parser")
    pagination = soup.select_one("#pagination")
    if pagination is None:
        raise ParseError("イオシス販賣分頁區塊消失")
    link = pagination.select_one('a[rel~="next"]')
    current = urlsplit(url)
    current_query = dict(parse_qsl(current.query))
    current_page = int(current_query.pop("page", "1"))
    if link is None:
        # 還有更後面的頁碼卻失去 next 時，不能把首幾頁當成完整結果。
        for candidate in pagination.select("a[href]"):
            query = dict(parse_qsl(urlsplit(candidate["href"]).query))
            if query.get("page", "").isdigit() and int(query["page"]) > current_page:
                raise ParseError("イオシス販賣下一頁連結消失")
        return None
    target = urljoin(url, link["href"])
    parts = urlsplit(target)
    query = dict(parse_qsl(parts.query))
    next_page = query.pop("page", "")
    if (parts.scheme != "https" or parts.netloc != "iosys.co.jp"
            or parts.path != current.path or query != current_query
            or not next_page.isdigit() or int(next_page) != current_page + 1
            or parts.fragment):
        raise ParseError("イオシス販賣下一頁網址不符合目前查詢")
    return target
