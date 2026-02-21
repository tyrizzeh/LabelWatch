"""
LabelWatch AI – config and watchlist for validation MVP.
"""

# FDA DailyMed
DAILYMED_RSS_URL = "https://dailymed.nlm.nih.gov/dailymed/rss.cfm"
DAILYMED_SERVICES_BASE = "https://dailymed.nlm.nih.gov/dailymed/services/v2"

# Watchlist: drug name substrings to match against RSS titles (case-insensitive).
# Expand to 10 for your 7-day validation; these are examples.
WATCHLIST_DRUGS = [
    "sildenafil",      # Viagra
    "tramadol",
    "bupropion",
    "escitalopram",
    "anastrozole",
    "buprenorphine",
    "tamsulosin",
    "nortriptyline",
    "magnesium sulfate",
    "bumetanide",
]

# Sections to highlight in impact reports (SPL codes / display names)
LABEL_SECTIONS_OF_INTEREST = [
    "Warnings and Precautions",
    "Dosage and Administration",
    "Dosage",
    "Warnings",
]
