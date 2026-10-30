#!/usr/bin/env python3
"""Grant-procedure news from the Bulgarian EU funds portal (eufunds.bg).

Open procedures themselves live in ISUN (see isun_procedures). This scraper
collects procedure announcements, guideline updates and public consultations
from the portal news listing. Writes data/eufunds_news_matches.json.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
from urllib import robotparser

import requests
from bs4 import BeautifulSoup

BASE = "https://www.eufunds.bg"
PAGES = [
    "https://www.eufunds.bg/bg/news-eip",
    "https://www.eufunds.bg/bg/news-eip?page=1",
]
SOURCE = "eufunds_news"
HERE = Path(__file__).parent
PROFILE_PATH = HERE.parent / "eu_funding_tenders" / "company_profile.json"
OUTPUT_PATH = HERE.parent.parent.parent / "data" / "eufunds_news_matches.json"
UA = (
    "Mozilla/5.0 (compatible; EuropeanFundingWorkflow-EufundsScraper/1.0; "
    "+https://github.com/sageorgiev18/EuropeanFundingWorkflow.ByGrok)"
)
KEEP = re.compile(r"процедур|покана|насоки|прием|кандидат|обсъждане|конкурс|финансов инструмент", re.I)
DROP = re.compile(r"^виж повече|доставка на|обществена поръчка", re.I)


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


def allowed(url: str) -> bool:
    rp = robotparser.RobotFileParser()
    try:
        r = requests.get(BASE + "/robots.txt", headers={"User-Agent": UA}, timeout=20)
        rp.parse(r.text.splitlines() if r.status_code == 200 else [])
    except requests.RequestException:
        return True
    return rp.can_fetch(UA, url)


def status_of(title: str) -> str:
    if re.search(r"отворен|прием|покана за кандидат|обществено обсъждане", title, re.I):
        return "open"
    if re.search(r"приключ|прекрат", title, re.I):
        return "closed"
    return "unknown"


def parse_page(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    rows = soup.select(".views-row") or soup.select("article")
    found = []
    seen = set()
    nodes = rows or [soup]
    for row in nodes:
        for a in row.select("a[href]"):
            title = " ".join(a.get_text(" ", strip=True).split())
            href = a["href"]
            if not title or DROP.search(title) or not KEEP.search(title):
                continue
            if "node/" not in href and "/node/" not in href:
                continue
            url = urljoin(BASE, href)
            if url in seen:
                continue
            seen.add(url)
            time_el = row.find("time")
            published = None
            if time_el is not None:
                published = (time_el.get("datetime") or time_el.get_text(" ", strip=True) or "")[:10] or None
            found.append({"title": title, "url": url, "start_date": published})
        if rows:
            continue
        break
    return found


def main() -> int:
    profile = load_profile()
    scraped_at = datetime.now(timezone.utc).isoformat()
    http = requests.Session()
    http.headers.update({"User-Agent": UA, "Accept-Language": "bg,en;q=0.8"})
    items = []
    seen = set()
    for url in PAGES:
        if not allowed(url):
            print("robots.txt disallows", url)
            continue
        resp = http.get(url, timeout=40)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        for item in parse_page(resp.text):
            if item["url"] in seen:
                continue
            seen.add(item["url"])
            items.append(item)
        time.sleep(1.2)
    matches = []
    for item in items:
        summary = item["title"]
        score, hits = score_match(summary, profile)
        node = item["url"].rstrip("/").split("/")[-1]
        matches.append({
            "id": f"{SOURCE}:{node}",
            "call_identifier": node,
            "title": item["title"],
            "summary": summary[:500],
            "url": item["url"],
            "status": status_of(item["title"]),
            "start_date": item.get("start_date"),
            "deadline": None,
            "source": SOURCE,
            "scraped_at": scraped_at,
            "match_score": score,
            "matched_keywords": hits,
            "program": "eufunds.bg",
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
    print(f"Wrote {len(matches)} news items -> {OUTPUT_PATH}")
    return len(matches)


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
