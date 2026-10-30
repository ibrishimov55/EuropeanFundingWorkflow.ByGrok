# Scrapers

This folder contains all code that scrapes funding websites.

## Structure

```
scrapers/
├── run_all.py       # Runs every scraper.py under sources/
├── requirements.txt
└── sources/         # One subdirectory per funding source
    ├── eu_funding_tenders/
    ├── sofia_municipality/
    └── ...
```

## Run all scrapers

From the repo root:

```bash
python scrapers/run_all.py
```

or from the scrapers folder:

```bash
cd scrapers
python run_all.py
```

The script discovers every `sources/*/scraper.py` and runs them one by one. Each scraper is executed from its own directory so relative paths and local files work correctly.

## Conventions

- Each source should be independently runnable via its own `scraper.py`.
- Output JSON that matches the schema in `docs/scraper-to-web-contract.md` (or `docs/architecture.md`).
- Prefer writing results to `../data/` so the web app can consume them.
- Use clear logging and handle rate limits / errors gracefully.

## Adding a new source

1. Create `sources/<source_name>/`.
2. Add a `scraper.py` that can be run directly.
3. Make it write valid funding-opportunity JSON.
4. Document the source in its own README and optionally here.

## Available sources

- `sources/eu_funding_tenders/` — EU Funding & Tenders Portal (SEDIA API). Writes `data/eu_funding_tenders_matches.json`.
- `sources/eu_grants/` — EU Funding & Tenders grants and calls (SEDIA API: topics plus calls for EIC, LIFE, Erasmus+, Creative Europe, Digital Europe, CEF and others, deadline still ahead). Writes `data/eu_grants_matches.json`.
- `sources/isun_procedures/` — ISUN 2020 open procedures (https://eumis2020.government.bg/bg/s/Procedure/Active). Writes `data/isun_procedures_matches.json`.
- `sources/fmfib/` — Fund of Funds active instruments (https://fmfib.bg/finansi/aktivni-finansovi-instrumenti). Writes `data/fmfib_matches.json`.
- `sources/interreg/` — Open Interreg calls that list Bulgaria (public search index behind https://interreg.eu/calls-for-projects/). Writes `data/interreg_matches.json`.
- `sources/eufunds_news/` — Procedure announcements on https://www.eufunds.bg/bg/news-eip. Writes `data/eufunds_news_matches.json`.
- `sources/sme_agency/` — Bulgarian SME Promotion Agency posts (WordPress REST, https://www.sme.government.bg/). Writes `data/sme_agency_matches.json`.
- `sources/bbr/` — Bulgarian Development Bank financing programmes (https://bbr.bg/). Writes `data/bbr_matches.json`.
- `sources/fni/` — Bulgarian National Science Fund open competitions (https://www.fni.bg/?q=node/94). Writes `data/fni_matches.json`.
- `sources/sofia_municipality/` — Sofia Municipality funding programmes (sofia.bg, kultura.sofia.bg, mladite.sofia.bg, evropa-so.bg, investsofia.com, ogf-sofia.com). Run `python scraper.py`; writes `data/sofia_municipality_matches.json` in the `docs/scraper-to-web-contract.md` shape (`{profile, scraped_at, count, matches}`, `source: "sofia_municipality"`, `deadline` = `YYYY-MM-DD`/null, `status` = open/closed/upcoming/unknown, `match_score`/`matched_keywords` vs. the shared company profile) plus a flattened `.csv`. The web app merges all `data/*_matches.json`. See its README.

## Output location

Scrapers write results to `../data/` (or a path documented in each source) so the web application can load them.
