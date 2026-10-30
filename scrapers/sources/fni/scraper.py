#!/usr/bin/env python3
"""Open competitions of the Bulgarian National Science Fund (fni.bg).

robots.txt asks for Crawl-delay: 10, which this scraper honours.
Writes data/fni_matches.json.
"""
from __future__ import annotations

import json
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
from urllib import robotparser

import requests
from bs4 import BeautifulSoup

BASE = "https://www.fni.bg/"
LIST_URL = "https://www.fni.bg/?q=node/94"
SOURCE = "fni"
HERE = Path(__file__).parent
PROFILE_PATH = HERE.parent / "eu_funding_tenders" / "company_profile.json"
OUTPUT_PATH = HERE.parent.parent.parent / "data" / "fni_matches.json"
UA = (
    "Mozilla/5.0 (compatible; EuropeanFundingWorkflow-FniScraper/1.0; "
    "+https://github.com/sageorgiev18/EuropeanFundingWorkflow.ByGrok)"
)
TODAY = date.today().isoformat()
CALL_RE = re.compile(r"покана|конкурс", re.I)
DATE_RE = re.compile(r"(\d{1,2})[./](\d{1,2})[./](20\d{2})")
DEADLINE_RE = re.compile(r"краен срок|срок за|deadline|до\s+\d{1,2}[./]\d{1,2}", re.I)


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


class DelayedSession:
    def __init__(self, delay: float):
        self.delay = delay
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA, "Accept-Language": "bg,en;q=0.8"})
        self._last = 0.0

    def get(self, url: str) -> requests.Response:
        wait = self.delay - (time.time() - self._last)
        if wait > 0 and self._last:
            time.sleep(wait)
        try:
            resp = self.s.get(url, timeout=40)
            resp.raise_for_status()
        finally:
            self._last = time.time()
        if not resp.encoding or resp.encoding.lower() in ("iso-8859-1", "ascii"):
            resp.encoding = "utf-8"
        return resp


def crawl_delay() -> float:
    rp = robotparser.RobotFileParser()
    try:
        r = requests.get(BASE + "robots.txt", headers={"User-Agent": UA}, timeout=20)
        rp.parse(r.text.splitlines() if r.status_code == 200 else [])
    except requests.RequestException:
        return 10.0
    if not rp.can_fetch(UA, LIST_URL):
        raise SystemExit(f"robots.txt disallows {LIST_URL}")
    delay = rp.crawl_delay(UA)
    return float(delay) if delay else 10.0


def listing_links(html: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    root = soup.select_one("#content") or soup.select_one(".region-content") or soup
    out = []
    seen = set()
    for a in root.select("a[href]"):
        title = " ".join(a.get_text(" ", strip=True).split())
        href = urljoin(BASE, a["href"])
        if "node/" not in href or href.rstrip("/") in seen:
            continue
        if not CALL_RE.search(title) or len(title) < 20:
            continue
        if title.lower().startswith("конкурси за програми"):
            continue
        seen.add(href.rstrip("/"))
        out.append((title, href))
    return out


def parse_detail(html: str) -> tuple[str | None, str]:
    soup = BeautifulSoup(html, "lxml")
    root = soup.select_one("#content") or soup.select_one(".node") or soup.body
    text = root.get_text("\n", strip=True) if root else ""
    deadline = None
    for line in text.split("\n"):
        if not DEADLINE_RE.search(line):
            continue
        m = DATE_RE.search(line)
        if m:
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            try:
                deadline = date(y, mo, d).isoformat()
            except ValueError:
                continue
            break
    summary = re.sub(r"\s+", " ", text).strip()[:700]
    return deadline, summary


def main() -> int:
    profile = load_profile()
    delay = crawl_delay()
    print(f"FNI crawl delay {delay}s")
    http = DelayedSession(delay)
    scraped_at = datetime.now(timezone.utc).isoformat()
    page = http.get(LIST_URL)
    links = listing_links(page.text)
    print(f"Announced competitions: {len(links)}")
    matches = []
    for title, url in links:
        try:
            detail = http.get(url)
            deadline, summary = parse_detail(detail.text)
        except requests.RequestException as exc:
            print("detail failed", url, exc)
            deadline, summary = None, title
        if not summary:
            summary = title
        status = "open"
        if deadline and deadline < TODAY:
            status = "closed"
        score, hits = score_match(f"{title} {summary}", profile)
        node = url.split("node/")[-1].split("&")[0]
        matches.append({
            "id": f"{SOURCE}:{node}",
            "call_identifier": f"fni-node-{node}",
            "title": title,
            "summary": summary[:500],
            "url": url,
            "status": status,
            "start_date": None,
            "deadline": deadline,
            "source": SOURCE,
            "scraped_at": scraped_at,
            "match_score": score,
            "matched_keywords": hits,
            "program": "Фонд „Научни изследвания“ (Bulgarian National Science Fund)",
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
    print(f"Wrote {len(matches)} competitions -> {OUTPUT_PATH}")
    return len(matches)


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
