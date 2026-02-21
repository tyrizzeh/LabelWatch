"""
LabelWatch AI – Dashboard to generate and view the impact report.
Run: streamlit run dashboard.py
"""

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st
from config import WATCHLIST_DRUGS
from report_pdf import build_pdf
from run import build_impact_report_md, generate_report, generate_report_with_changes
from scrapers.dailymed import apply_filters, fetch_drug_classes, parse_label_date
from scrapers.openfda import fetch_fda_validation_for_matches

st.set_page_config(
    page_title="LabelWatch AI",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Sidebar: options
st.sidebar.header("Options")
use_demo = st.sidebar.checkbox(
    "Use demo data (no network)",
    value=False,
    help="Show sample label updates instead of fetching live DailyMed RSS.",
)
include_history = st.sidebar.checkbox(
    "Include SPL version history",
    value=False,
    help="Call DailyMed API per match for version counts (slower).",
)
include_changes = st.sidebar.checkbox(
    "Include what changed in each label",
    value=True,
    help="Fetch previous SPL version and diff Warnings/Dosage/Contraindications (slower, live data only).",
)
cross_validate_fda = st.sidebar.checkbox(
    "Cross-validate with FDA (openFDA)",
    value=False,
    help="Compare each label to FDA's openFDA API to detect lag between DailyMed and FDA data (openFDA updates weekly).",
)

# Filters
st.sidebar.markdown("---")
st.sidebar.markdown("### Filters")
st.sidebar.caption("Narrow results after the report is generated.")
default_end = date.today()
default_start = default_end - timedelta(days=7)
filter_date_start = st.sidebar.date_input(
    "From date",
    value=default_start,
    help="Only include labels updated on or after this date.",
)
filter_date_end = st.sidebar.date_input(
    "To date",
    value=default_end,
    help="Only include labels updated on or before this date.",
)
if filter_date_start > filter_date_end:
    st.sidebar.warning("From date is after To date; results may be empty.")

# Drug class dropdown (cached)
if "drug_classes" not in st.session_state:
    with st.spinner("Loading drug classes..."):
        try:
            st.session_state["drug_classes"] = fetch_drug_classes(pagesize=100, max_pages=5)
        except Exception:
            st.session_state["drug_classes"] = []
drug_classes = st.session_state.get("drug_classes", [])
drug_class_options = ["All drug classes"] + [f"{c['name']} ({c['type']})" for c in drug_classes]
drug_class_choice = st.sidebar.selectbox(
    "Drug class",
    options=drug_class_options,
    index=0,
    help="Only include labels in this pharmacologic class (e.g. Opioid, SSRI).",
)
filter_drug_class_code = None
if drug_class_choice != "All drug classes":
    for c in drug_classes:
        if f"{c['name']} ({c['type']})" == drug_class_choice:
            filter_drug_class_code = c["code"]
            break

filter_keyword = st.sidebar.text_input(
    "Keyword in title",
    placeholder="e.g. tramadol, tablet",
    help="Only include labels whose title contains this text.",
)
filter_manufacturer = st.sidebar.text_input(
    "Manufacturer (in title)",
    placeholder="e.g. Pfizer, Teva",
    help="Only include labels whose title contains this manufacturer name.",
)

st.sidebar.markdown("---")
st.sidebar.markdown("### Watchlist")
st.sidebar.caption("Drug name substrings used to filter the RSS feed (edit in config.py).")
for drug in WATCHLIST_DRUGS:
    st.sidebar.code(drug, language=None)

# Main area
st.title("LabelWatch AI")
st.markdown("Automated regulatory labeling tracker — FDA DailyMed (last 7 days).")

if st.button("Generate report", type="primary", use_container_width=False):
    with st.spinner(
        "Fetching data and building report..."
        + (" Comparing label versions for changes..." if include_changes and not use_demo else "")
    ):
        try:
            if include_changes:
                matches, markdown, change_texts = generate_report_with_changes(
                    demo=use_demo,
                )
            else:
                matches, markdown = generate_report(
                    demo=use_demo,
                    fetch_history=include_history and not use_demo,
                )
                change_texts = [""] * len(matches)
            # Apply filters (date range, drug class, keyword, manufacturer)
            filtered_matches, filtered_change_texts = apply_filters(
                matches,
                date_start=filter_date_start,
                date_end=filter_date_end,
                drug_class_code=filter_drug_class_code,
                keyword=filter_keyword.strip() or None,
                manufacturer=filter_manufacturer.strip() or None,
                change_texts=change_texts,
            )
            fda_validation = None
            if cross_validate_fda and filtered_matches:
                with st.spinner("Cross-validating with FDA (openFDA)..."):
                    dailymed_dates = [
                        parse_label_date(u.updated_date or u.pub_date)
                        for u in filtered_matches
                    ]
                    fda_validation = fetch_fda_validation_for_matches(
                        [u.setid for u in filtered_matches],
                        dailymed_dates,
                    )
            markdown = build_impact_report_md(
                filtered_matches,
                fetch_history=False,
                change_texts=filtered_change_texts,
                fda_validation=fda_validation,
            )
            pdf_bytes = build_pdf(
                filtered_matches,
                filtered_change_texts or [],
                fda_validation=fda_validation,
            )
            st.session_state["report_md"] = markdown
            st.session_state["report_matches"] = len(filtered_matches)
            st.session_state["report_pdf"] = pdf_bytes
        except Exception as e:
            st.error(f"Report generation failed: {e}")
            if "report_md" in st.session_state:
                del st.session_state["report_md"]
            if "report_pdf" in st.session_state:
                del st.session_state["report_pdf"]

if "report_md" in st.session_state:
    n = st.session_state.get("report_matches", 0)
    st.success(f"Report generated ({n} watchlist match(es)).")
    filters_used = []
    if filter_date_start != default_start or filter_date_end != default_end:
        filters_used.append(f"date {filter_date_start}–{filter_date_end}")
    if filter_drug_class_code:
        filters_used.append("drug class")
    if filter_keyword.strip():
        filters_used.append("keyword")
    if filter_manufacturer.strip():
        filters_used.append("manufacturer")
    if filters_used:
        st.caption(f"Filters applied: {', '.join(filters_used)}.")
    # Download buttons at top so they're always visible (no scrolling to find PDF)
    st.markdown("### Download report")
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            label="Download PDF",
            data=st.session_state.get("report_pdf", b""),
            file_name="labelwatch_impact_report.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
    with col2:
        st.download_button(
            label="Download .md",
            data=st.session_state["report_md"],
            file_name="labelwatch_impact_report.md",
            mime="text/markdown",
            use_container_width=True,
        )
    st.markdown("---")
    st.subheader("Impact report")
    st.markdown(st.session_state["report_md"])
else:
    st.info("Click **Generate report** to fetch DailyMed updates and build the impact report (with optional PDF and what changed).")
    st.caption("Use the sidebar to include label diffs (Warnings, Dosage, etc.) and download as PDF.")
