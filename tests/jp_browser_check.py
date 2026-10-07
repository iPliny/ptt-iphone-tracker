"""選用的離線 Chromium 驗收；先依 docs/jp-buyback-validation.md 建置示意網站。"""
import argparse
import json
import mimetypes
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright


def check(site, home_site, screenshots):
    screenshots.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1380}, color_scheme="light")
        page.on("pageerror", lambda error: errors.append(str(error)))

        def serve(route):
            url = urlparse(route.request.url)
            root = home_site if url.hostname == "home.test" else site
            if url.hostname not in ("preview.test", "home.test"):
                route.abort()  # 截圖與驗收不送 GA、也不請求任何外站。
                return
            path = root / url.path.lstrip("/")
            if path.is_dir():
                path = path / "index.html"
            if not path.is_file():
                route.fulfill(status=404, body="not found")
                return
            route.fulfill(path=path, content_type=mimetypes.guess_type(path)[0] or "application/octet-stream")

        page.route("**/*", serve)
        page.goto("http://preview.test/jp/")
        page.wait_for_selector("#trend svg")
        assert page.locator(".jp-table tbody tr").count() == 4
        assert "シルバー 不收" in page.locator("#comparison").inner_text()
        assert "¥20,000" in page.locator("#comparison").inner_text()
        page.screenshot(path=screenshots / "desktop.png")
        page.select_option("#compare-model", "iPhone 18 Pro Max")
        assert "¥245,000" in page.locator("#comparison").inner_text()
        page.select_option("#trend-model", "iPhone 18 Pro Max")
        page.select_option("#trend-storage", "2TB")
        for period in ("30", "all", "7"):
            page.select_option("#trend-days", period)
            assert page.locator("#trend svg").count() == 1
        page.select_option("#compare-model", "iPhone 18 Pro")
        page.select_option("#trend-model", "iPhone 18 Pro")
        page.select_option("#trend-storage", "256GB")
        for theme in ("light", "dark"):
            page.set_viewport_size({"width": 375, "height": 1100})
            page.emulate_media(color_scheme=theme)
            page.evaluate("window.scrollTo(0,0)")
            assert page.evaluate("document.documentElement.scrollWidth <= 375")
            assert page.locator(".jp-table tbody tr").first.evaluate("e => getComputedStyle(e).display") == "block"
            page.screenshot(path=screenshots / f"mobile-375-{theme}.png")
            page.locator('section[aria-labelledby="trend-title"]').screenshot(path=screenshots / f"mobile-trend-{theme}.png")
        page.set_viewport_size({"width": 1440, "height": 500})
        page.emulate_media(color_scheme="light")
        page.goto("http://home.test/")
        page.wait_for_selector('header a[href="jp/"]')
        assert page.locator('header a[href="jp/"]').inner_text() == "日本買取價"
        page.locator("header").screenshot(path=screenshots / "homepage-header.png")
        # 無日本資料的建置仍有可用空狀態。
        page.goto("http://home.test/jp/")
        page.wait_for_selector("#statuses article")
        assert "資料準備中" in page.locator("#comparison").inner_text()
        assert not page.locator("#downloads a").count()
        assert not errors, errors
        browser.close()
    print(json.dumps({"page_errors": errors, "mobile_width": 375, "horizontal_overflow": False,
                      "themes": ["light", "dark"], "screenshots": len(list(screenshots.glob("*.png")))}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", required=True, type=Path)
    parser.add_argument("--home-site", required=True, type=Path)
    parser.add_argument("--screenshots", required=True, type=Path)
    args = parser.parse_args()
    check(args.site.resolve(), args.home_site.resolve(), args.screenshots.resolve())
