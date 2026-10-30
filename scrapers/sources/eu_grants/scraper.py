#!/usr/bin/env python3
"""Open and forthcoming EU grant topics from the official SEDIA Search API.

Same portal as eu_funding_tenders, but calls for proposals (type=1) rather than
tenders. Writes data/eu_grants_matches.json in the scraper-to-web contract shape.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

import requests

API_URL = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"
API_KEY = "SEDIA"
HERE = Path(__file__).parent
PROFILE_PATH = HERE.parent / "eu_funding_tenders" / "company_profile.json"
OUTPUT_PATH = HERE.parent.parent.parent / "data" / "eu_grants_matches.json"
SOURCE = "eu_grants"
TODAY = date.today().isoformat()

PROGRAMMES = (
    ("HORIZON-EIC", "EIC (Horizon Europe)"),
    ("HORIZON-EIE", "European Innovation Ecosystems"),
    ("HORIZON", "Horizon Europe"),
    ("DIGITAL", "Digital Europe"),
    ("LIFE", "LIFE"),
    ("CREA", "Creative Europe"),
    ("ERASMUS", "Erasmus+"),
    ("CEF", "Connecting Europe Facility"),
    ("INNOVFUND", "Innovation Fund"),
    ("EU4H", "EU4Health"),
    ("EDF", "European Defence Fund"),
    ("SMP", "Single Market Programme"),
    ("CERV", "Citizens, Equality, Rights and Values"),
    ("JUST", "Justice programme"),
    ("AMIF", "Asylum, Migration and Integration Fund"),
    ("ISF", "Internal Security Fund"),
    ("BMVI", "Border Management and Visa Instrument"),
    ("EMFAF", "European Maritime, Fisheries and Aquaculture Fund"),
)
STATUS = {"31094501": "upcoming", "31094502": "open", "31094503": "closed"}


def load_profile() -> dict:
    with open(PROFILE_PATH, encoding="utf-8") as f:
        return json.load(f)


def programme_of(identifier: str | None) -> str | None:
    ident = identifier or ""
    for prefix, name in PROGRAMMES:
        if ident.startswith(prefix):
            return name
    head = ident.split("-")[0]
    return head or None


def score_match(text: str, profile: dict) -> tuple[float, list[str]]:
    keywords = profile.get("keywords") or []
    full = re.sub(r"\s+", " ", (text or "").lower())
    hits = [kw for kw in keywords if kw.lower() in full]
    bonus = sum(0.5 for kw in hits if " " in kw)
    if not keywords:
        return 0.0, []
    return round(min(1.0, (len(hits) + bonus) / len(keywords)), 3), hits


def fetch_page(page: int, page_size: int = 50) -> dict:
    query = {
        "bool": {
            "must": [
                {"terms": {"type": ["1"]}},
                {"terms": {"status": ["31094501", "31094502"]}},
                {"range": {"deadlineDate": {"gte": TODAY + "T00:00:00.000Z"}}},
            ]
        }
    }
    files = {"query": ("query.json", json.dumps(query), "application/json")}
    data = {"pageSize": str(page_size), "pageNumber": str(page)}
    resp = requests.post(
        API_URL,
        params={"apiKey": API_KEY, "text": "***"},
        data=data,
        files=files,
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def portal_url(identifier: str | None, raw_url: str | None) -> str | None:
    if identifier:
        return (
            "https://ec.europa.eu/info/funding-tenders/opportunities/portal/"
            f"screen/opportunities/topic-details/{identifier}"
        )
    return raw_url


def extract(raw: dict, profile: dict, scraped_at: str) -> dict:
    meta = raw.get("metadata") or {}

    def first(key: str):
        vals = meta.get(key) or []
        return vals[0] if vals else None

    identifier = first("identifier") or raw.get("reference")
    title = first("title") or raw.get("summary") or "Untitled"
    summary = (raw.get("summary") or "").strip()
    if not summary:
        desc = re.sub(r"<[^>]+>", " ", first("descriptionByte") or "")
        summary = re.sub(r"\s+", " ", desc).strip()[:400]
    score, hits = score_match(f"{title} {summary}", profile)
    deadline = (first("deadlineDate") or "")[:10] or None
    return {
        "id": str(identifier),
        "call_identifier": first("callIdentifier") or identifier,
        "title": title,
        "summary": summary[:500],
        "url": portal_url(identifier, raw.get("url")),
        "status": STATUS.get(first("status") or "", "open"),
        "start_date": (first("startDate") or "")[:10] or None,
        "deadline": deadline,
        "source": SOURCE,
        "scraped_at": scraped_at,
        "match_score": score,
        "matched_keywords": hits,
        "program": programme_of(str(identifier or "")),
        "countries": ["EU", "BG"],
        "description": summary[:700],
    }


def main(max_pages: int = 2) -> int:
    profile = load_profile()
    scraped_at = datetime.now(timezone.utc).isoformat()
    matches: list[dict] = []
    seen: set[str] = set()
    for page in range(1, max_pages + 1):
        print(f"Fetching SEDIA grants page {page}...")
        results = fetch_page(page).get("results") or []
        if not results:
            break
        for raw in results:
            opp = extract(raw, profile, scraped_at)
            if not opp["id"] or opp["id"] in seen:
                continue
            if not opp["deadline"] or opp["deadline"] < TODAY:
                continue
            seen.add(opp["id"])
            matches.append(opp)
        if len(results) < 50:
            break
    matches.sort(key=lambda x: (x["deadline"] or "9999", -x["match_score"]))
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "profile": profile.get("name", "Your Company"),
        "scraped_at": scraped_at,
        "count": len(matches),
        "matches": matches,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"Wrote {len(matches)} grants -> {OUTPUT_PATH}")
    return len(matches)


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
