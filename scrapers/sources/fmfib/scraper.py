#!/usr/bin/env python3
"""Active financial instruments of the Bulgarian Fund of Funds (fmfib.bg).

One public HTML listing. Writes data/fmfib_matches.json.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib import robotparser

import requests
from bs4 import BeautifulSoup

PAGE = "https://fmfib.bg/finansi/aktivni-finansovi-instrumenti"
SOURCE = "fmfib"
HERE = Path(__file__).parent
PROFILE_PATH = HERE.parent / "eu_funding_tenders" / "company_profile.json"
OUTPUT_PATH = HERE.parent.parent.parent / "data" / "fmfib_matches.json"
UA = (
    "Mozilla/5.0 (compatible; EuropeanFundingWorkflow-FmfibScraper/1.0; "
    "+https://github.com/sageorgiev18/EuropeanFundingWorkflow.ByGrok)"
)


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
        r = requests.get(urlparse(url).scheme + "://" + urlparse(url).netloc + "/robots.txt",
                         headers={"User-Agent": UA}, timeout=20)
        rp.parse(r.text.splitlines() if r.status_code == 200 else [])
    except requests.RequestException:
        return True
    return rp.can_fetch(UA, url)


def main() -> int:
    if not allowed(PAGE):
        print("robots.txt disallows", PAGE)
        return 1
    profile = load_profile()
    scraped_at = datetime.now(timezone.utc).isoformat()
    resp = requests.get(PAGE, headers={"User-Agent": UA, "Accept-Language": "bg,en;q=0.8"}, timeout=40)
    resp.raise_for_status()
    resp.encoding = resp.encoding or "utf-8"
    soup = BeautifulSoup(resp.text, "lxml")
    seen = set()
    matches = []
    for a in soup.select("a[href]"):
        href = urljoin(PAGE, a["href"].strip())
        path = urlparse(href).path.rstrip("/")
        parts = [p for p in path.split("/") if p]
        if len(parts) != 2 or parts[0] != "instrument":
            continue
        if href in seen:
            continue
        title = " ".join(a.get_text(" ", strip=True).split())
        if not title or len(title) < 8 or len(title) > 180:
            continue
        seen.add(href)
        summary = f"Активен финансов инструмент на Фонда на фондовете: {title}"
        score, hits = score_match(f"{title} {summary}", profile)
        matches.append({
            "id": f"{SOURCE}:{parts[1]}",
            "call_identifier": parts[1],
            "title": title,
            "summary": summary,
            "url": href,
            "status": "open",
            "start_date": None,
            "deadline": None,
            "source": SOURCE,
            "scraped_at": scraped_at,
            "match_score": score,
            "matched_keywords": hits,
            "program": "Фонд на фондовете (Fund of Funds)",
            "countries": ["BG"],
            "description": summary,
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
    print(f"Wrote {len(matches)} instruments -> {OUTPUT_PATH}")
    return len(matches)


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
