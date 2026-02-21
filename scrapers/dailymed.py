"""
FDA DailyMed RSS and REST API client.
- RSS: last 7 days of label updates (title, link with setid/version).
- API: SPL history by setid, SPL XML by setid, fetch old version (zip) for diff.
"""

import difflib
import io
import re
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from urllib.parse import urlparse, parse_qs

import feedparser
import requests
from lxml import etree

from config import DAILYMED_RSS_URL, DAILYMED_SERVICES_BASE

# DailyMed URLs for SPL content
DAILYMED_BASE = "https://dailymed.nlm.nih.gov/dailymed"
# LOINC codes for key label sections (FDA SPL)
SPL_SECTION_CODES = {
    "34067-9": "Warnings and Precautions",
    "34068-7": "Dosage and Administration",
    "43685-7": "Contraindications",
    "42232-9": "Indications and Usage",
}


@dataclass
class LabelUpdate:
    """One item from DailyMed RSS (one label update in last 7 days)."""
    title: str
    link: str
    setid: str
    version: int
    updated_date: str
    pub_date: str


def parse_setid_version_from_link(link: str) -> tuple[str | None, int | None]:
    """Extract setid and version from DailyMed lookup URL."""
    parsed = urlparse(link)
    if "lookup.cfm" not in parsed.path:
        return None, None
    qs = parse_qs(parsed.query)
    setid = (qs.get("setid") or [None])[0]
    ver_str = (qs.get("version") or ["1"])[0]
    try:
        version = int(ver_str)
    except ValueError:
        version = 1
    return setid, version


def fetch_rss_updates(rss_url: str = DAILYMED_RSS_URL) -> list[LabelUpdate]:
    """Fetch and parse DailyMed RSS (last 7 days of updates)."""
    feed = feedparser.parse(rss_url)
    updates = []
    for entry in feed.entries:
        link = entry.get("link") or ""
        setid, version = parse_setid_version_from_link(link)
        if not setid:
            continue
        # description often like "Updated Date: Fri, 13 Feb 2026 00:00:00 EST"
        desc = entry.get("description", "")
        updated_date = desc.replace("Updated Date: ", "").strip() if "Updated Date:" in desc else ""
        pub = entry.get("published", "")
        updates.append(
            LabelUpdate(
                title=entry.get("title", ""),
                link=link,
                setid=setid,
                version=version,
                updated_date=updated_date,
                pub_date=pub,
            )
        )
    return updates


def filter_updates_by_watchlist(
    updates: list[LabelUpdate],
    drug_substrings: list[str],
) -> list[LabelUpdate]:
    """Keep only updates whose title contains any of the watchlist strings."""
    out = []
    lower_substrings = [s.lower() for s in drug_substrings]
    for u in updates:
        title_lower = u.title.lower()
        if any(sub in title_lower for sub in lower_substrings):
            out.append(u)
    return out


def parse_label_date(date_str: str) -> date | None:
    """Parse RSS date string (e.g. 'Fri, 13 Feb 2026 00:00:00 EST') to date."""
    if not date_str:
        return None
    s = date_str.strip()
    # Strip timezone suffix for strptime (e.g. " EST" or " EDT")
    for tz in (" EST", " EDT", " UTC", " PST", " PDT"):
        if s.endswith(tz):
            s = s[: -len(tz)].strip()
            break
    try:
        for fmt in (
            "%a, %d %b %Y %H:%M:%S",
            "%Y-%m-%d",
            "%b %d, %Y",
            "%d %b %Y",
        ):
            try:
                dt = datetime.strptime(s[:30], fmt)
                return dt.date()
            except ValueError:
                continue
    except Exception:
        pass
    return None


def fetch_drug_classes(pagesize: int = 100, max_pages: int = 20) -> list[dict]:
    """Fetch drug class list from DailyMed (name, code, type). Returns list of {name, code, type}."""
    out = []
    page = 1
    while page <= max_pages:
        url = f"{DAILYMED_SERVICES_BASE}/drugclasses.json?pagesize={pagesize}&page={page}"
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            data = r.json()
            items = (data.get("data") or [])
            if not items:
                break
            for item in items:
                out.append({
                    "name": item.get("name", ""),
                    "code": item.get("code", ""),
                    "type": item.get("type", ""),
                })
            meta = data.get("metadata") or {}
            if str(meta.get("next_page", "")) == "null" or not items:
                break
            page += 1
        except requests.RequestException:
            break
    return out


def fetch_spl_setids_for_drug_class(
    drug_class_code: str,
    published_date_gte: str | None = None,
    max_pages: int = 50,
) -> set[str]:
    """Fetch all setids for SPLs in the given drug class (optionally published on or after date)."""
    if not drug_class_code:
        return set()
    setids = set()
    page = 1
    params = {"drug_class_code": drug_class_code, "pagesize": 100}
    if published_date_gte:
        params["published_date"] = published_date_gte
        params["published_date_comparison"] = "gte"
    while page <= max_pages:
        params["page"] = page
        try:
            r = requests.get(f"{DAILYMED_SERVICES_BASE}/spls.json", params=params, timeout=30)
            r.raise_for_status()
            data = r.json()
            items = (data.get("data") or [])
            if not items:
                break
            for item in items:
                sid = item.get("setid")
                if sid:
                    setids.add(sid)
            meta = data.get("metadata") or {}
            if str(meta.get("next_page", "")) == "null":
                break
            page += 1
        except requests.RequestException:
            break
    return setids


def apply_filters(
    matches: list[LabelUpdate],
    *,
    date_start: date | None = None,
    date_end: date | None = None,
    drug_class_code: str | None = None,
    drug_class_setids: set[str] | None = None,
    keyword: str | None = None,
    manufacturer: str | None = None,
    change_texts: list[str] | None = None,
) -> tuple[list[LabelUpdate], list[str] | None]:
    """
    Filter matches by date range, drug class, keyword in title, manufacturer in title.
    If change_texts is provided, returns (filtered_matches, filtered_change_texts); else (filtered_matches, None).
    """
    result = list(matches)
    texts = list(change_texts) if change_texts is not None else None
    if texts is not None and len(texts) != len(result):
        texts = (texts + [""] * len(result))[:len(result)]

    if date_start is not None or date_end is not None:
        filtered = []
        filtered_texts = [] if texts else None
        for i, u in enumerate(result):
            d = parse_label_date(u.updated_date or u.pub_date)
            if d is None:
                filtered.append(u)
                if filtered_texts is not None:
                    filtered_texts.append(texts[i])
            else:
                if date_start is not None and d < date_start:
                    continue
                if date_end is not None and d > date_end:
                    continue
                filtered.append(u)
                if filtered_texts is not None:
                    filtered_texts.append(texts[i])
        result = filtered
        texts = filtered_texts

    if drug_class_code or drug_class_setids is not None:
        allowed = drug_class_setids if drug_class_setids is not None else set()
        if drug_class_code and not allowed:
            allowed = fetch_spl_setids_for_drug_class(drug_class_code)
        if allowed:
            filtered = []
            filtered_texts = [] if texts else None
            for i, u in enumerate(result):
                if u.setid in allowed:
                    filtered.append(u)
                    if filtered_texts is not None:
                        filtered_texts.append(texts[i])
            result = filtered
            texts = filtered_texts

    keyword = (keyword or "").strip().lower()
    if keyword:
        filtered = []
        filtered_texts = [] if texts else None
        for i, u in enumerate(result):
            if keyword in u.title.lower():
                filtered.append(u)
                if filtered_texts is not None:
                    filtered_texts.append(texts[i])
        result = filtered
        texts = filtered_texts

    manufacturer = (manufacturer or "").strip().lower()
    if manufacturer:
        filtered = []
        filtered_texts = [] if texts else None
        for i, u in enumerate(result):
            # Manufacturer often in [Brackets] at end of title
            if manufacturer in u.title.lower():
                filtered.append(u)
                if filtered_texts is not None:
                    filtered_texts.append(texts[i])
        result = filtered
        texts = filtered_texts

    return result, texts


def fetch_spl_history(setid: str) -> dict | None:
    """Fetch version history for an SPL (setid). Returns JSON data or None."""
    url = f"{DAILYMED_SERVICES_BASE}/spls/{setid}/history.json"
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        return r.json()
    except requests.RequestException:
        return None


def get_previous_version(setid: str, current_version: int) -> int | None:
    """From history, return the previous version number (for diff), or None."""
    data = fetch_spl_history(setid)
    if not data:
        return None
    history = (data.get("data") or {}).get("history") or []
    versions = sorted((int(h["spl_version"]) for h in history), reverse=True)
    for v in versions:
        if v < current_version:
            return v
    return None


def fetch_spl_xml(setid: str) -> str | None:
    """Fetch current SPL document as XML string."""
    url = f"{DAILYMED_SERVICES_BASE}/spls/{setid}.xml"
    try:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        return r.text
    except requests.RequestException:
        return None


def fetch_spl_zip(setid: str, version: int) -> bytes | None:
    """Fetch a specific SPL version as ZIP (for older versions)."""
    url = f"{DAILYMED_BASE}/getFile.cfm?type=zip&setid={setid}&version={version}"
    try:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        return r.content
    except requests.RequestException:
        return None


def _extract_xml_from_spl_zip(zip_bytes: bytes) -> str | None:
    """Extract the main SPL XML from a DailyMed ZIP (single .xml or in subdir)."""
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as z:
            for name in z.namelist():
                if name.endswith(".xml") and "spl" in name.lower():
                    return z.read(name).decode("utf-8", errors="replace")
            # fallback: first .xml
            for name in z.namelist():
                if name.endswith(".xml"):
                    return z.read(name).decode("utf-8", errors="replace")
    except Exception:
        pass
    return None


def _strip_html_to_text(html_fragment: str) -> str:
    """Crude strip of HTML tags for plain-text diff."""
    if not html_fragment:
        return ""
    text = re.sub(r"<[^>]+>", " ", html_fragment)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_spl_sections(xml_str: str) -> dict[str, str]:
    """Extract key sections from SPL XML. Returns dict: section_name -> plain text."""
    if not xml_str:
        return {}
    ns = {"hl7": "urn:hl7-org:v3"}
    out = {}
    try:
        root = etree.fromstring(xml_str.encode("utf-8"))
        for code, name in SPL_SECTION_CODES.items():
            sections = root.xpath(
                f"//hl7:section[hl7:code[@code='{code}']]",
                namespaces=ns,
            )
            if not sections:
                sections = root.xpath(
                    f"//*[local-name()='section'][*[local-name()='code'][@code='{code}']]"
                )
            for sec in sections:
                text_el = sec.xpath(".//hl7:text", namespaces=ns)
                if not text_el:
                    text_el = sec.xpath(".//*[local-name()='text']")
                if text_el:
                    raw = etree.tostring(
                        text_el[0],
                        encoding="unicode",
                        method="text",
                        with_tail=False,
                    )
                    out[name] = _strip_html_to_text(raw)[:8000]
                    break
    except Exception:
        pass
    return out


def _parse_unified_diff_to_added_removed(
    old_lines: list[str],
    new_lines: list[str],
) -> tuple[list[str], list[str]]:
    """Convert unified diff to (added_lines, removed_lines) for readable formatting."""
    diff = list(
        difflib.unified_diff(old_lines, new_lines, lineterm="", n=0),
    )
    added: list[str] = []
    removed: list[str] = []
    for line in diff:
        if line.startswith("+") and not line.startswith("+++"):
            added.append(line[1:].strip())
        elif line.startswith("-") and not line.startswith("---"):
            removed.append(line[1:].strip())
    return added, removed


def get_label_changes(
    setid: str,
    current_version: int,
    include_sections: dict[str, str] | None = None,
) -> str:
    """
    Compare current SPL to previous version; return human-readable summary of changes.
    include_sections: optional {section_name: text} to use as "current" when XML fetch fails.
    """
    sections_to_use = include_sections or SPL_SECTION_CODES
    prev_version = get_previous_version(setid, current_version)
    if prev_version is None:
        return "No previous version available for comparison."

    current_xml = fetch_spl_xml(setid)
    current_sections = parse_spl_sections(current_xml) if current_xml else {}

    zip_bytes = fetch_spl_zip(setid, prev_version)
    old_xml = _extract_xml_from_spl_zip(zip_bytes) if zip_bytes else None
    old_sections = parse_spl_sections(old_xml) if old_xml else {}

    if not current_sections and not old_sections:
        return "Could not retrieve label content for comparison (API may be temporarily unavailable)."

    lines = []
    all_names = sorted(set(current_sections.keys()) | set(old_sections.keys()))
    for name in all_names:
        old_text = (old_sections.get(name) or "").strip()
        new_text = (current_sections.get(name) or "").strip()
        if old_text == new_text:
            continue
        lines.append(f"{name}")
        if not old_text:
            lines.append("  Added in this version.")
            snippet = new_text[:1500].replace("\n", " ")
            if len(new_text) > 1500:
                snippet += "..."
            lines.append(f"  {snippet}")
        elif not new_text:
            lines.append("  Removed in this version.")
        else:
            added, removed = _parse_unified_diff_to_added_removed(
                old_text.splitlines()[:200],
                new_text.splitlines()[:200],
            )
            if removed:
                lines.append("  **Removed:**")
                for line in removed[:30]:
                    lines.append(f"  - {line[:500]}")
                if len(removed) > 30:
                    lines.append(f"  - ... and {len(removed) - 30} more line(s)")
                lines.append("")
            if added:
                lines.append("  **Added:**")
                for line in added[:30]:
                    lines.append(f"  - {line[:500]}")
                if len(added) > 30:
                    lines.append(f"  - ... and {len(added) - 30} more line(s)")
            if not added and not removed:
                lines.append("  (Content reflow or minor edits; no clear added/removed lines.)")
        lines.append("")

    return "\n".join(lines).strip() if lines else "No text changes detected in key sections (Warnings, Dosage, etc.)."
