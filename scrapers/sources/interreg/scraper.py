#!/usr/bin/env python3
"""Open and forthcoming Interreg calls from the public search index behind interreg.eu.

Keeps calls whose eligible countries include Bulgaria (Danube, Black Sea, Euro-MED,
Interreg Europe, Greece-Bulgaria, Romania-Bulgaria, and others that list BG).
Writes data/interreg_matches.json.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import requests

APP_ID = "2E032DRCNS"
API_KEY = "afcd3bc5094a8f54ceb9cb221c74dbc7"
INDEX = "prod_en-us_content"
SEARCH_URL = f"https://{APP_ID}-dsn.algolia.net/1/indexes/{INDEX}/query"
SOURCE = "interreg"
HERE = Path(__file__).parent
PROFILE_PATH = HERE.parent / "eu_funding_tenders" / "company_profile.json"
OUTPUT_PATH = HERE.parent.parent.parent / "data" / "interreg_matches.json"
SITE = "https://interreg.eu"


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


def search(status: str) -> list[dict]:
    label = "Coming" if status == "coming" else "Open"
    body = {
        "query": "",
        "filters": f"contentType:callForProjectsPage AND callStatus:{label}",
        "hitsPerPage": 100,
    }
    resp = requests.post(
        SEARCH_URL,
        headers={
            "X-Algolia-Application-Id": APP_ID,
            "X-Algolia-API-Key": API_KEY,
            "Content-Type": "application/json",
            "User-Agent": "EuropeanFundingWorkflow-InterregScraper/1.0",
        },
        json=body,
        timeout=40,
    )
    resp.raise_for_status()
    return resp.json().get("hits") or []


def covers_bulgaria(hit: dict) -> bool:
    countries = [c.lower() for c in (hit.get("callEligibleCountryNames") or hit.get("countries") or [])]
    if "bulgaria" in countries:
        return True
    blob = " ".join(hit.get("associatedProgrammes") or []).lower() + " " + (hit.get("title") or "").lower()
    return any(k in blob for k in ("bulgaria", "danube", "black sea", "greece-bulgaria", "romania-bulgaria"))


def main() -> int:
    profile = load_profile()
    scraped_at = datetime.now(timezone.utc).isoformat()
    matches = []
    seen = set()
    for status in ("open", "coming"):
        hits = search(status)
        print(f"{status}: {len(hits)} hits")
        for hit in hits:
            if not covers_bulgaria(hit):
                continue
            pid = str(hit.get("pageId") or hit.get("objectID"))
            if pid in seen:
                continue
            seen.add(pid)
            title = (hit.get("title") or hit.get("nodeName") or "Interreg call").strip()
            programmes = hit.get("associatedProgrammes") or []
            program = programmes[0] if programmes else "Interreg"
            countries = hit.get("callEligibleCountryNames") or hit.get("countries") or []
            deadline = (hit.get("callDeadlineDate") or "")[:10] or None
            start = (hit.get("callOpenDate") or "")[:10] or None
            external = hit.get("callExternalUrl") or ""
            content = hit.get("contentUrl") or ""
            url = external or (SITE + content if content.startswith("/") else content or SITE + "/calls-for-projects/")
            themes = ", ".join(hit.get("callThemes") or hit.get("themes") or [])
            summary = f"{program}. Eligible: {', '.join(countries[:12])}."
            if themes:
                summary += f" Themes: {themes}."
            score, kws = score_match(f"{title} {summary}", profile)
            mapped = "upcoming" if status == "coming" else "open"
            if deadline and deadline < datetime.now(timezone.utc).date().isoformat() and mapped != "upcoming":
                mapped = "closed"
            matches.append({
                "id": f"{SOURCE}:{pid}",
                "call_identifier": hit.get("nodeName") or pid,
                "title": title,
                "summary": summary[:500],
                "url": url,
                "status": mapped,
                "start_date": start,
                "deadline": deadline,
                "source": SOURCE,
                "scraped_at": scraped_at,
                "match_score": score,
                "matched_keywords": kws,
                "program": program,
                "countries": countries or ["BG"],
                "description": summary[:700],
            })
    matches.sort(key=lambda m: (m["deadline"] or "9999", m["title"]))
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "profile": profile.get("name", "Your Company"),
        "scraped_at": scraped_at,
        "count": len(matches),
        "matches": matches,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"Wrote {len(matches)} Interreg calls -> {OUTPUT_PATH}")
    return len(matches)


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
