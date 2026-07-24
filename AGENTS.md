# AGENTS.md

## Cursor Cloud specific instructions

LabelWatch AI is a small Python app (no database, no build step). It has two entry points that share the same code: a Streamlit dashboard (`dashboard.py`) and a CLI (`run.py`). See `README.md` for the full command list; notes below only cover non-obvious caveats.

### Environment
- Dependencies live in a virtualenv at `.venv/` (created by the startup update script). Activate it before running anything: `source .venv/bin/activate`. If a command reports missing packages, you are likely not in the venv.
- Creating the venv requires the system package `python3.12-venv` (installed via `apt`, persisted in the VM snapshot). This is not part of the update script; if `python3 -m venv` ever fails on a fresh VM, install `python3.12-venv` first.

### Running
- Dashboard: `streamlit run dashboard.py` serves on `http://localhost:8501`. Use `--server.headless true` in the cloud VM so it does not try to open a browser.
- CLI: `python run.py` (writes `output/impact_report.md`). `output/*.md` and `output/*.pdf` are git-ignored.

### Live data vs demo/offline
- Live mode hits public FDA APIs (`dailymed.nlm.nih.gov`, `api.fda.gov`) with no auth/API keys required — outbound internet works in this environment (verified: RSS returns ~1000+ entries).
- The dashboard's "Include what changed in each label" option is ON by default and makes several extra network calls per matched label (can be slow/flaky with many matches). Turn it OFF for a fast smoke test.
- Fully offline paths: CLI `python run.py --demo` and the dashboard "Use demo data" checkbox use hardcoded sample data and make no network calls.

### Lint / tests
- There is no configured linter or test suite. Use `python -m py_compile config.py run.py dashboard.py report_pdf.py scrapers/*.py` as a quick syntax/import check.
