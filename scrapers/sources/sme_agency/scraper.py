#!/usr/bin/env python3
"""Recent funding posts from the Bulgarian SME Promotion Agency (sme.government.bg).

Uses the public WordPress REST API. The host certificate does not chain to a
public CA from this environment, so TLS verification is disabled for this host
only. Writes data/sme_agency_matches.json.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

API = "https://www.sme.government.bg/wp-json/wp/v2/posts"
SOURCE = "sme_agency"
HERE = Path(__file__).parent
PROFILE_PATH = HERE.parent / "eu_funding_tenders" / "company_profile.json"
OUTPUT_PATH = HERE.parent.parent.parent / "data" / "sme_agency_matches.json"
UA = (
    "Mozilla/5.0 (compatible; EuropeanFundingWorkflow-SmeScraper/1.0; "
    "+https://github.com/sageorgiev18/EuropeanFundingWorkflow.ByGrok)"
)
SEARCHES = (
    "покана за кандидатстване",
    "безвъзмездна финансова помощ",
    "прием на проектни предложения",
    "ваучер",
    "отворена процедура",
    "финансова подкрепа",
)
KEEP = re.compile(
    r"финансир|покана|процедур|безвъзмезд|грант|конкурс|ваучер|прием|кандидат|подкрепа",
    re.I,
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


def clean_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html or "")
    return re.sub(r"\s+", " ", text).strip()


def status_of(title: str, published: str) -> str:
    if re.search(r"приключ|прекрат|архив", title, re.I):
        return "closed"
    if re.search(r"покана|прием|отворен|процедур|ваучер|кандидат", title, re.I):
        return "open"
    return "unknown"


def main() -> int:
    profile = load_profile()
    scraped_at = datetime.now(timezone.utc).isoformat()
    http = requests.Session()
    http.headers.update({"User-Agent": UA, "Accept": "application/json"})
    posts: dict[int, dict] = {}
    for query in SEARCHES:
        resp = http.get(
            API,
            params={
                "search": query,
                "per_page": 20,
                "orderby": "date",
                "order": "desc",
                "_fields": "id,date,link,title,excerpt",
            },
            timeout=40,
            verify=False,
        )
        resp.raise_for_status()
        for post in resp.json():
            posts[post["id"]] = post
        print(f"search {query!r}: running total {len(posts)}")
    matches = []
    for post in posts.values():
        title = clean_html((post.get("title") or {}).get("rendered") or "")
        excerpt = clean_html((post.get("excerpt") or {}).get("rendered") or "")
        if not KEEP.search(title + " " + excerpt):
            continue
        published = (post.get("date") or "")[:10] or None
        if published and published < "2024-01-01":
            continue
        summary = excerpt or title
        score, hits = score_match(f"{title} {summary}", profile)
        matches.append({
            "id": f"{SOURCE}:{post['id']}",
            "call_identifier": str(post["id"]),
            "title": title,
            "summary": summary[:500],
            "url": post.get("link"),
            "status": status_of(title, published or ""),
            "start_date": published,
            "deadline": None,
            "source": SOURCE,
            "scraped_at": scraped_at,
            "match_score": score,
            "matched_keywords": hits,
            "program": "Изпълнителна агенция за насърчаване на малките и средните предприятия",
            "countries": ["BG"],
            "description": summary[:700],
        })
    matches.sort(key=lambda m: m.get("start_date") or "", reverse=True)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "profile": profile.get("name", "Your Company"),
        "scraped_at": scraped_at,
        "count": len(matches),
        "matches": matches,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"Wrote {len(matches)} posts -> {OUTPUT_PATH}")
    return len(matches)


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
