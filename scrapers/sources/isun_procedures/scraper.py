#!/usr/bin/env python3
"""Active Bulgarian EU-funds procedures from ISUN 2020 (eumis2020.government.bg).

The public "Отворени" list is server-rendered HTML. Each procedure page carries
the application window. Writes data/isun_procedures_matches.json.
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

LIST_URL = "https://eumis2020.government.bg/bg/s/Procedure/Active"
BASE = "https://eumis2020.government.bg"
SOURCE = "isun_procedures"
HERE = Path(__file__).parent
PROFILE_PATH = HERE.parent / "eu_funding_tenders" / "company_profile.json"
OUTPUT_PATH = HERE.parent.parent.parent / "data" / "isun_procedures_matches.json"
UA = (
    "Mozilla/5.0 (compatible; EuropeanFundingWorkflow-IsunScraper/1.0; "
    "+https://github.com/sageorgiev18/EuropeanFundingWorkflow.ByGrok)"
)
TODAY = date.today().isoformat()


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "bg,en;q=0.8"})
    retry = Retry(total=3, backoff_factor=0.4, status_forcelist=(429, 500, 502, 503, 504))
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def load_profile() -> dict:
    with open(PROFILE_PATH, encoding="utf-8") as f:
        return json.load(f)


def score_match(text: str, profile: dict) -> tuple[float, list[str]]:
    keywords = profile.get("keywords") or []
    full = re.sub(r"\s+", " ", (text or "").lower())
    hits = [kw for kw in keywords if kw.lower() in full]
    bonus = sum(0.5 for kw in hits if " " in kw)
    if not keywords:
        return 0.0, []
    return round(min(1.0, (len(hits) + bonus) / len(keywords)), 3), hits


def parse_listing(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    items = []
    seen = set()
    for li in soup.select("li[data-href]"):
        href = li.get("data-href") or ""
        if "/Procedure/Info/" not in href:
            continue
        text = " ".join(li.get_text(" ", strip=True).split())
        if " - " in text:
            code, title = text.split(" - ", 1)
        else:
            code, title = text, text
        program = ""
        parent = li.find_parent("li")
        if parent is not None:
            bits = []
            for child in parent.children:
                if getattr(child, "name", None) == "ul":
                    break
                if isinstance(child, str):
                    bits.append(child.strip())
                elif getattr(child, "get_text", None):
                    bits.append(child.get_text(" ", strip=True))
            program = re.sub(r"\s+", " ", " ".join(b for b in bits if b)).strip()
            program = re.sub(r"\s*\(\d+\)\s*$", "", program)
        url = urljoin(BASE, href)
        if url in seen:
            continue
        seen.add(url)
        items.append({
            "code": code.strip(),
            "title": (title or code).strip(),
            "program": program,
            "url": url,
        })
    return items


def _iso_after(text: str, label: str) -> str | None:
    m = re.search(label + r"\s*(\d{2})\.(\d{2})\.(\d{4})", text)
    if not m:
        return None
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"


def parse_detail(html: str) -> tuple[str | None, str | None, str | None]:
    text = BeautifulSoup(html, "lxml").get_text("\n", strip=True)
    start = _iso_after(text, r"Начален срок:")
    deadline = _iso_after(text, r"Краен срок:")
    goal = None
    m = re.search(r"Основна цел:\s*(.+)", text)
    if m:
        goal = m.group(1).strip()[:700]
    return start, deadline, goal


def fetch_detail(http: requests.Session, item: dict) -> dict:
    try:
        r = http.get(item["url"], timeout=30)
        r.raise_for_status()
        if not r.encoding or r.encoding.lower() in ("iso-8859-1", "ascii"):
            r.encoding = "utf-8"
        start, deadline, goal = parse_detail(r.text)
    except requests.RequestException as exc:
        print(f"detail failed {item['url']}: {exc}")
        start = deadline = goal = None
    item = dict(item)
    item.update(start_date=start, deadline=deadline, summary=goal)
    return item


def status_of(start: str | None, deadline: str | None) -> str:
    if start and start > TODAY and (not deadline or deadline >= TODAY):
        return "upcoming"
    if deadline and deadline < TODAY:
        return "closed"
    return "open"


def main() -> int:
    profile = load_profile()
    scraped_at = datetime.now(timezone.utc).isoformat()
    http = session()
    print(f"Fetching {LIST_URL}")
    listing = http.get(LIST_URL, timeout=40)
    listing.raise_for_status()
    listing.encoding = "utf-8"
    items = parse_listing(listing.text)
    print(f"Listing has {len(items)} procedures")
    enriched = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(fetch_detail, http, item) for item in items]
        for fut in as_completed(futures):
            enriched.append(fut.result())
    enriched.sort(key=lambda x: x["code"])
    matches = []
    for item in enriched:
        summary = item.get("summary") or item["title"]
        score, hits = score_match(f"{item['title']} {item.get('program') or ''} {summary}", profile)
        matches.append({
            "id": f"{SOURCE}:{item['code']}",
            "call_identifier": item["code"],
            "title": item["title"],
            "summary": summary[:500],
            "url": item["url"],
            "status": status_of(item.get("start_date"), item.get("deadline")),
            "start_date": item.get("start_date"),
            "deadline": item.get("deadline"),
            "source": SOURCE,
            "scraped_at": scraped_at,
            "match_score": score,
            "matched_keywords": hits,
            "program": item.get("program") or None,
            "countries": ["BG"],
            "description": summary[:700],
        })
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "profile": profile.get("name", "Your Company"),
        "scraped_at": scraped_at,
        "count": len(matches),
        "matches": matches,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"Wrote {len(matches)} procedures -> {OUTPUT_PATH}")
    return len(matches)


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
