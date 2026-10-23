#!/usr/bin/env python3
"""Capture clean, current viewport screenshots of four public portfolio sites.

The script only visits a fixed allowlist of company websites and never reads
private CRM systems. Each successful screenshot is saved as optimized WebP.
Failed captures leave existing images untouched; the page has fallback images.
"""
from __future__ import annotations

import io
import json
import pathlib
from PIL import Image, ImageOps
from playwright.sync_api import sync_playwright

OUT = pathlib.Path("img")
OUT.mkdir(parents=True, exist_ok=True)
TARGETS = {
    "portfolio-case-ramp.webp": [
        "https://gzrichtone.com/",
        "https://ae.gzrichtone.com/",
        "https://cm.gzrichtone.com/",
    ],
    "portfolio-case-humanbusiness.webp": [
        "https://h-b.group/",
    ],
    "portfolio-case-mariroberto.webp": [
        "https://mari-russia.ru/",
    ],
    "portfolio-case-stroyideya.webp": [
        "https://shop-idea.ru/",
    ],
}
BAD_TITLES = ["403 forbidden", "404 not found", "access denied", "attention required", "just a moment", "cloudflare", "privacy error", "502 bad gateway", "504 gateway"]
BAD_BODY = ["checking your browser before accessing", "error 403", "access denied", "please enable cookies", "checking if the site connection is secure"]


def make_preview(page, file_name: str) -> int:
    raw = page.screenshot(type="png", full_page=False, animations="disabled", timeout=30000)
    image = Image.open(io.BytesIO(raw)).convert("RGB")
    image = ImageOps.fit(image, (1200, 750), method=Image.Resampling.LANCZOS)
    target = OUT / file_name
    image.save(target, format="WEBP", quality=85, method=6)
    return target.stat().st_size


def capture(browser, file_name: str, urls: list[str]) -> dict:
    record = {"file": file_name, "status": "not_captured", "attempts": []}
    for url in urls:
        context = browser.new_context(
            viewport={"width": 1200, "height": 750},
            device_scale_factor=1,
            locale="en-US",
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        )
        page = context.new_page()
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=45000)
            status = response.status if response else None
            page.wait_for_timeout(2200)
            # Dismiss public-site UI overlays before capturing the viewport.
            if file_name == "portfolio-case-ramp.webp":
                try:
                    page.get_by_role("button", name="Yes", exact=True).first.click(timeout=2500)
                    page.wait_for_timeout(800)
                except Exception:
                    pass
                page.add_style_tag(content="""
                  iframe,
                  [class*="chat-widget"], [id*="chat-widget"],
                  [class*="chatbot"], [id*="chatbot"],
                  [class*="intercom"], [id*="intercom"],
                  [class*="tawk"], [id*="tawk"],
                  [class*="crisp"], [id*="crisp"],
                  [class*="popup"], [class*="country-modal"],
                  [class*="country-popup"] {visibility:hidden!important;}
                """)
            elif file_name == "portfolio-case-humanbusiness.webp":
                # The home hero contains a third-party video that fails
                # security validation in headless environments. Photograph
                # the visible brands section instead of that error overlay.
                try:
                    page.get_by_text("Наши бренды", exact=True).last.scroll_into_view_if_needed(timeout=6000)
                    page.evaluate("window.scrollBy(0,-100)")
                except Exception:
                    page.evaluate("window.scrollTo(0,1150)")
                page.wait_for_timeout(1100)
            elif file_name == "portfolio-case-stroyideya.webp":
                try:
                    page.get_by_text("Согласен", exact=True).first.click(timeout=2200)
                    page.wait_for_timeout(450)
                except Exception:
                    pass
            title = (page.title() or "").strip()
            body = (page.locator("body").inner_text(timeout=6000) or "")[:3500]
            problem = (
                status is not None and status >= 400
                or any(x in title.lower() for x in BAD_TITLES)
                or any(x in body.lower() for x in BAD_BODY)
                or len(body.strip()) < 100
            )
            if problem:
                record["attempts"].append({"url": url, "http_status": status, "title": title[:100], "result": "unusable"})
                continue
            # No account authentication or private-data extraction; only a public viewport.
            size = make_preview(page, file_name)
            record.update({"status": "captured", "url": url, "title": title[:100], "bytes": size})
            break
        except Exception as exc:
            record["attempts"].append({"url": url, "result": type(exc).__name__, "detail": str(exc)[:110]})
        finally:
            context.close()
    return record


def main() -> int:
    results = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            for filename, websites in TARGETS.items():
                result = capture(browser, filename, websites)
                results.append(result)
                print(json.dumps(result, ensure_ascii=False))
        finally:
            browser.close()
    (OUT / "portfolio-screenshot-audit.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("Captured", sum(x["status"] == "captured" for x in results), "of", len(TARGETS), "sites")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
