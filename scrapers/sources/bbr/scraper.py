#!/usr/bin/env python3
"""Financing programmes of the Bulgarian Development Bank (bbr.bg).

Standing instruments and on-lending programmes published as HTML pages.
Writes data/bbr_matches.json.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

SOURCE = "bbr"
HERE = Path(__file__).parent
PROFILE_PATH = HERE.parent / "eu_funding_tenders" / "company_profile.json"
OUTPUT_PATH = HERE.parent.parent.parent / "data" / "bbr_matches.json"
UA = (
    "Mozilla/5.0 (compatible; EuropeanFundingWorkflow-BbrScraper/1.0; "
    "+https://github.com/sageorgiev18/EuropeanFundingWorkflow.ByGrok)"
)
# Public programme pages linked from the bank's own navigation (not news).
PAGES = [
    "https://bbr.bg/bg/kreditirane/",
    "https://bbr.bg/bg/za-finansovi-institucii/on-lending-programi-v-podkrepa-na-malkiya-i-sredniya-biznes/",
    "https://bbr.bg/bg/za-finansovi-institucii/on-lendng-programi-v-podkrepa-na-malkiya-i-sredniya-biznes/",
    "https://bbr.bg/bg/za-finansovi-institucii/vei-za-domakinstva-zeleni-proekti/",
    "https://bbr.bg/bg/za-finansovi-institucii/programa-za-kreditni-kooperacii-na-zemedelski-stopani/",
    "https://bbr.bg/bg/programa-za-obnovyavane-na-zhilishni-sgradi-po-npvu/",
    "https://bbr.bg/bg/programi-s-drzhaven-mandat/investicionna-programa-za-obshinski-proekti/",
    "https://bbr.bg/bg/investicionnata-programa-za-obshinski-proekti/",
    "https://bbr.bg/bg/energijna-efektivnost-national-programmes/",
    "https://bbr.bg/bg/energijna-efektivnost-national-programs/",
    "https://bbr.bg/bg/invest-eu/izbor-na-finansovi-posrednici-po-programa-investeu-2026/",
    "https://bbr.bg/bg/podkrepa-za-postradali-ot-covid-19-national-programmes/",
]


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


def page_record(html: str, url: str) -> tuple[str, str] | None:
    soup = BeautifulSoup(html, "lxml")
    main = soup.select_one("main") or soup.body
    if main is None:
        return None
    for tag in main.select("script, style, nav, footer"):
        tag.decompose()
    h1 = main.find("h1")
    title = " ".join(h1.get_text(" ", strip=True).split()) if h1 else ""
    if not title or title.lower().startswith("управление на бисквитките"):
        title = ""
    if soup.title and not title:
        title = re.sub(r"\s+-\s+.*$", "", soup.title.get_text(" ", strip=True)).strip()
    text = re.sub(r"\s+", " ", main.get_text(" ", strip=True)).strip()
    if title and text.startswith(title):
        text = text[len(title):].strip()
    # drop cookie-banner residue
    text = re.sub(r"^Управление на бисквитките.*?(?=За |Ние |Програма|Кредит|ББР|Инвест)", "", text)
    summary = text[:700]
    if len(title) < 4 or len(summary) < 40:
        return None
    return title, summary


def main() -> int:
    profile = load_profile()
    scraped_at = datetime.now(timezone.utc).isoformat()
    http = requests.Session()
    http.headers.update({"User-Agent": UA, "Accept-Language": "bg,en;q=0.8"})
    matches = []
    seen_titles = set()
    for url in PAGES:
        try:
            resp = http.get(url, timeout=30)
        except requests.RequestException as exc:
            print("fail", url, exc)
            time.sleep(1.0)
            continue
        time.sleep(1.0)
        if resp.status_code != 200:
            print("skip", resp.status_code, url)
            continue
        resp.encoding = "utf-8"
        parsed = page_record(resp.text, url)
        if not parsed:
            print("no content", url)
            continue
        title, summary = parsed
        key = title.lower()
        if key in seen_titles:
            continue
        seen_titles.add(key)
        score, hits = score_match(f"{title} {summary}", profile)
        slug = url.rstrip("/").split("/")[-1] or "bbr"
        closed = bool(re.search(r"приключи(ла)?|прекратен", summary, re.I))
        matches.append({
            "id": f"{SOURCE}:{slug}",
            "call_identifier": slug,
            "title": title,
            "summary": summary[:500],
            "url": url,
            "status": "closed" if closed else "open",
            "start_date": None,
            "deadline": None,
            "source": SOURCE,
            "scraped_at": scraped_at,
            "match_score": score,
            "matched_keywords": hits,
            "program": "Българска банка за развитие (Bulgarian Development Bank)",
            "countries": ["BG"],
            "description": summary[:700],
        })
        print("kept", title[:80])
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "profile": profile.get("name", "Your Company"),
        "scraped_at": scraped_at,
        "count": len(matches),
        "matches": matches,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"Wrote {len(matches)} programmes -> {OUTPUT_PATH}")
    return len(matches)


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
