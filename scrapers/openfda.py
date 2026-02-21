"""
openFDA Drug Label API client for cross-validation with DailyMed.
FDA updates weekly; DailyMed (NLM) may have different sync timing.
"""

from dataclasses import dataclass
from datetime import date, datetime

import requests

OPENFDA_LABEL_URL = "https://api.fda.gov/drug/label.json"


@dataclass
class FDALabelInfo:
    """Minimal FDA label info for cross-validation."""
    set_id: str
    effective_date: date | None  # FDA effective_time (YYYYMMDD)
    effective_time_raw: str  # e.g. "20210902"
    found: bool


def _parse_effective_time(eff: str) -> date | None:
    """Parse FDA effective_time (YYYYMMDD) to date."""
    if not eff or len(eff) < 8:
        return None
    try:
        return datetime.strptime(eff[:8], "%Y%m%d").date()
    except ValueError:
        return None


def fetch_fda_label_by_setid(setid: str) -> FDALabelInfo | None:
    """
    Fetch drug label from openFDA by set_id (SPL set ID).
    Returns FDALabelInfo with effective date, or None on network/API error.
    """
    if not setid:
        return None
    # openFDA search: search=set_id:<value>
    try:
        r = requests.get(
            OPENFDA_LABEL_URL,
            params={"search": f"set_id:{setid}", "limit": 1},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        results = data.get("results") or []
        if not results:
            return FDALabelInfo(
                set_id=setid,
                effective_date=None,
                effective_time_raw="",
                found=False,
            )
        rec = results[0]
        eff = rec.get("effective_time") or ""
        return FDALabelInfo(
            set_id=setid,
            effective_date=_parse_effective_time(eff),
            effective_time_raw=eff,
            found=True,
        )
    except requests.RequestException:
        return None


def fetch_fda_validation_for_matches(
    setids: list[str],
    dailymed_dates: list[date | None],
) -> list[tuple[str, int | None]]:
    """
    For each setid, fetch FDA label and compare with DailyMed date.
    Returns list of (status_message, lag_days) per setid.
    """
    out = []
    for i, setid in enumerate(setids):
        dm_date = dailymed_dates[i] if i < len(dailymed_dates) else None
        fda_info = fetch_fda_label_by_setid(setid)
        msg, lag = cross_validate_dailymed_vs_fda(dm_date, fda_info)
        out.append((msg, lag))
    return out


def cross_validate_dailymed_vs_fda(
    dailymed_date: date | None,
    fda_info: FDALabelInfo | None,
) -> tuple[str, int | None]:
    """
    Compare DailyMed update date with FDA effective date.
    Returns (status_message, lag_days).
    lag_days: positive = DailyMed is ahead of FDA, negative = FDA is ahead, None = unknown.
    """
    if fda_info is None:
        return ("FDA (openFDA): not queried", None)
    if not fda_info.found:
        return ("FDA (openFDA): no record found for this set ID", None)
    fda_d = fda_info.effective_date
    if fda_d is None:
        return (f"FDA (openFDA): effective date not parsed (raw: {fda_info.effective_time_raw})", None)
    if dailymed_date is None:
        return (f"FDA effective date: {fda_d.isoformat()} (DailyMed date unknown)", None)
    lag = (dailymed_date - fda_d).days
    if lag == 0:
        return (f"FDA (openFDA): in sync — effective {fda_d.isoformat()}", 0)
    if lag > 0:
        return (f"FDA (openFDA): DailyMed {lag} day(s) ahead — FDA effective {fda_d.isoformat()}", lag)
    return (f"FDA (openFDA): FDA {-lag} day(s) ahead — FDA effective {fda_d.isoformat()}", lag)
