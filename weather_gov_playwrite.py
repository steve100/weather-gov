"""
weather_gov_playwrite.py
------------------------
Navigates to weather.gov, fills in the location search box,
selects the first "City, ST" match from the autocomplete dropdown,
and saves the forecast page as HTML, Markdown, and JSON.

Requirements:
    pip install playwright html2text
    playwright install chromium

Usage:
    python weather_gov_playwrite.py "Cary, NC, USA"
    python weather_gov_playwrite.py "Cary, NC" --now
    python weather_gov_playwrite.py "Cary, NC" --output reports
    python weather_gov_playwrite.py              # uses built-in default
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright
import html2text


DEFAULT_LOCATION = "Cary, NC, USA"
HOME_URL = "https://www.weather.gov/"


def location_slug(location: str) -> str:
    return re.sub(r"[,\s]+", "_", location).strip("_")


def safe_text(locator, default="") -> str:
    try:
        return locator.first.inner_text(timeout=3_000).strip()
    except Exception:
        return default


def safe_attr(locator, attr, default="") -> str:
    try:
        return locator.first.get_attribute(attr, timeout=3_000) or default
    except Exception:
        return default


def extract_current(page) -> dict:
    return {
        "temperature": safe_text(page.locator("#current-conditions .myforecast-current-lh")),
        "description": safe_text(page.locator("#current-conditions .myforecast-current")),
    }


def extract_forecast(page, location: str) -> dict:
    periods = []
    for container in page.locator("#seven-day-forecast-body .tombstone-container").all():
        periods.append({
            "name":        safe_text(container.locator(".period-name")).replace("\n", " "),
            "short_desc":  safe_text(container.locator(".short-desc")).replace("\n", " "),
            "temperature": safe_text(container.locator(".temp")),
            "detail":      safe_attr(container.locator("img"), "title"),
        })

    return {
        "location": location,
        "url": page.url,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "current_conditions": extract_current(page),
        "seven_day_forecast": periods,
    }


def extract_now(page, location: str) -> dict:
    return {
        "location": location,
        "url": page.url,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "current_conditions": extract_current(page),
    }


def search_weather(location: str = DEFAULT_LOCATION, headless: bool = False,
                   now: bool = False, output_dir: str = "output") -> str:
    slug = location_slug(location)
    os.makedirs(output_dir, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        pg = browser.new_page()

        print(f"[1/4] Loading {HOME_URL} ...")
        pg.goto(HOME_URL, wait_until="domcontentloaded")

        search_input = pg.locator("#inputstring")
        search_input.wait_for(state="visible", timeout=10_000)
        search_input.click()
        search_input.press_sequentially(location, delay=80)
        print(f"[2/4] Typed location: {location!r}")

        city_state = ", ".join(p.strip() for p in location.split(",")[:2])
        dropdown_item = pg.locator(f".autocomplete-suggestions div:has-text('{city_state}')").first
        dropdown_item.wait_for(state="visible", timeout=8_000)
        print(f"[3/4] Selecting first match for {city_state!r} from dropdown ...")
        with pg.expect_navigation(timeout=15_000):
            dropdown_item.click()

        final_url = pg.url
        print(f"      Forecast page: {final_url}")

        print(f"[4/4] Saving output ...")
        html_content = pg.content()

        if now:
            data = extract_now(pg, location)
            suffix = "_NOW_playwrite"
        else:
            data = extract_forecast(pg, location)
            suffix = "_playwrite"

            html_file = os.path.join(output_dir, f"{slug}{suffix}.html")
            with open(html_file, "w", encoding="utf-8") as f:
                f.write(html_content)
            print(f"      Saved HTML     -> {html_file}")

            converter = html2text.HTML2Text()
            converter.ignore_links = False
            converter.ignore_images = True
            md_file = os.path.join(output_dir, f"{slug}{suffix}.md")
            with open(md_file, "w", encoding="utf-8") as f:
                f.write(converter.handle(html_content))
            print(f"      Saved Markdown -> {md_file}")

        json_file = os.path.join(output_dir, f"{slug}{suffix}.json")
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"      Saved JSON     -> {json_file}")

        png_file = os.path.join(output_dir, f"{slug}{suffix}.png")
        pg.screenshot(path=png_file, full_page=True)
        print(f"      Saved PNG      -> {png_file}")

        browser.close()

    return final_url


if __name__ == "__main__":
    args = sys.argv[1:]
    now_flag = "--now" in args
    args = [a for a in args if a != "--now"]

    output_dir = "output"
    if "--output" in args:
        idx = args.index("--output")
        output_dir = args[idx + 1]
        args = args[:idx] + args[idx + 2:]

    loc = " ".join(args) if args else DEFAULT_LOCATION
    search_weather(loc, now=now_flag, output_dir=output_dir)
