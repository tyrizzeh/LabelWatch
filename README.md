# LabelWatch AI

**Automated Regulatory Labeling Tracker** – Monitors FDA DailyMed for drug label (PI) changes and surfaces updates for Warnings/Precautions and Dosing.

- **Phase:** Solo-validatable MVP (7-day validation plan).
- **Day 1–2:** This repo delivers the DailyMed scraper + watchlist filter + impact report output.

## Quick start

```bash
cd labelwatch-ai
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**Dashboard (generate report in the browser):**

```bash
streamlit run dashboard.py
```

Then open the URL (e.g. http://localhost:8501), click **Generate report**, and use **Download report (.md)** to save.

**CLI (same report to file):**

```bash
python run.py
```

Output: `output/impact_report.md` – watchlist matches from the last 7 days with setid, version, and link. Use this (or a PDF export) for **Day 3** LinkedIn outreach.

## What’s included

| Component        | Purpose |
|-----------------|--------|
| `config.py`     | Watchlist drug names, DailyMed URLs, sections of interest. |
| `scrapers/dailymed.py` | RSS parser (last 7 days), filter by watchlist, SPL history API. |
| `run.py`        | Fetches RSS → filters by watchlist → builds report (CLI + `generate_report()` for dashboard). |
| `dashboard.py`  | Streamlit dashboard: generate report in-browser, view, and download .md. |

## 7-day validation plan (tactical)

- **Day 1–2:** ✅ Scrape FDA DailyMed; watchlist filter; impact report.
- **Day 3:** Manually create 3 “Impact Reports” (PDFs) from `impact_report.md` or add a few high-value drugs to the watchlist and re-run.
- **Day 4–5:** LinkedIn outreach to 50 Regulatory Affairs Managers; offer reports for feedback.
- **Day 6–7:** If 5+ want “this every week,” add landing page + waitlist.

## Watchlist

Edit `config.py` → `WATCHLIST_DRUGS`. Entries are matched case-insensitively against the RSS item title (e.g. `"sildenafil"` matches Viagra). Start with 10 drugs for validation.

## Next steps (post-validation)

- **Diff visuals:** Use `/spls/{setid}/history` + older SPL XML (e.g. `getFile.cfm?type=zip&setid=&version=`) to extract Warnings/Dosage sections and diff (e.g. difflib or OpenAI for summary).
- **Alerts:** Resend + cron or Supabase Edge to email when watchlist drugs appear in RSS.
- **Dashboard:** Next.js + Supabase for watchlist and diff UI.

## Push to GitHub

To publish this project to [LabelWatch](https://github.com/tyrizzeh/LabelWatch):

```bash
cd labelwatch-ai
git init
git add .
git commit -m "Initial commit: LabelWatch AI"
git branch -M main
git remote add origin https://github.com/tyrizzeh/LabelWatch.git
git push -u origin main
```

If the repo already has a remote or you get "origin already exists", use `git remote set-url origin https://github.com/tyrizzeh/LabelWatch.git` then `git push -u origin main`. Use a [personal access token](https://github.com/settings/tokens) if GitHub prompts for a password.

## Sources

- [DailyMed RSS (last 7 days)](https://dailymed.nlm.nih.gov/dailymed/rss.cfm)
- [DailyMed REST API v2](https://dailymed.nlm.nih.gov/dailymed/app-support-web-services.cfm) – `/spls`, `/spls/{setid}`, `/spls/{setid}/history`
