"""Source licensing and collection-permission gates.

Every source that can feed the pipeline must be registered here with its
verified licensing status and the collection modes that are permitted. The
pipeline *refuses* to run an unpermitted mode instead of failing silently.

All citations below were verified by direct retrieval on the capture date
recorded per source (see docs/LICENSING.md for the full matrix, links and
verbatim clause text).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


class PolicyError(RuntimeError):
    """Raised when a collection mode is not permitted for a source."""


@dataclass(frozen=True)
class SourcePolicy:
    source_id: str
    display_name: str
    license_id: str                    # machine id, e.g. "odbl-1.0"
    license_summary: str
    collection_modes: List[str] = field(default_factory=list)
    # e.g. ["automated_api", "manual_import", "manual_snapshot"]
    rate_limit: str = "n/a"
    verified_at: str = ""              # date the licensing evidence was checked
    evidence_urls: List[str] = field(default_factory=list)
    caveats: List[str] = field(default_factory=list)

    def permits(self, mode: str) -> bool:
        return mode in self.collection_modes

    def assert_permitted(self, mode: str) -> None:
        if not self.permits(mode):
            raise PolicyError(
                f"source '{self.source_id}' does not permit collection mode "
                f"'{mode}' (permitted: {self.collection_modes}). "
                f"License: {self.license_id}. See docs/LICENSING.md."
            )


# Mode vocabulary
MODE_AUTO_API = "automated_api"
MODE_MANUAL_IMPORT = "manual_import"          # human downloads/places a file
MODE_MANUAL_SNAPSHOT = "manual_snapshot"      # human-captured page review

_POLICIES: Dict[str, SourcePolicy] = {}


def _register(p: SourcePolicy) -> None:
    _POLICIES[p.source_id] = p


def get_policy(source_id: str) -> SourcePolicy:
    if source_id not in _POLICIES:
        raise PolicyError(f"unknown source '{source_id}'; register it first")
    return _POLICIES[source_id]


def all_policies() -> List[SourcePolicy]:
    return list(_POLICIES.values())


# --- OpenLigaDB -----------------------------------------------------------------
# Verified 2026-09-19 from https://openligadb.de/ and https://api.openligadb.de/:
#   "Die \u00fcber diese API bereitgestellten Daten stehen unter der Open Database
#    License (ODbL)" (https://openligadb.de/lizenz),
#   "Es gilt ein Limit von 60 Anfragen pro Minute und IP",
#   "Abgeschlossene Saisons \u00e4ndern sich nicht mehr".
# Data is community-entered, so it is an open-licensed *reference* source, not a
# governing-body feed; identity/reconciliation gates still apply.
_register(SourcePolicy(
    source_id="openligadb",
    display_name="OpenLigaDB",
    license_id="odbl-1.0",
    license_summary=(
        "Open Database License (ODbL) 1.0 - open, share-alike. Derivative "
        "databases must be ODbL-licensed with attribution. No auth, no key."
    ),
    collection_modes=[MODE_AUTO_API, MODE_MANUAL_IMPORT, MODE_MANUAL_SNAPSHOT],
    rate_limit="60 requests/minute/IP (stated on API front page)",
    verified_at="2026-09-19",
    evidence_urls=[
        "https://openligadb.de/",
        "https://api.openligadb.de/",
        "https://openligadb.de/lizenz",
        "https://opendatacommons.org/licenses/odbl/1-0/",
    ],
    caveats=[
        "Community-entered results, not a DFL/governing-body official feed.",
        "ODbL share-alike: derived database files must carry ODbL attribution.",
        "Completed seasons are stated to no longer change; live seasons can.",
    ],
))

# --- football-data.co.uk --------------------------------------------------------
# Verified 2026-09-19 from https://www.football-data.co.uk/data.php:
#   "All FREE!!! ... however its use is intended for private individuals only,
#    NOT commerical or data training products using automated bots/scrapers/AI."
# Also from https://www.football-data.co.uk/matches.php:
#   "the odds are collected for the downloadable weekend fixtures on Fridays
#    afternoons generally not later than 17:00 British Standard Time. Odds for
#    midweek fixtures are collected Tuesdays not later than 13:00 British
#    Standard Time."
#   and a warning that Pinnacle odds are systematically out of date since
#   23/07/2025 and excluded from market average/maximum calculations.
_register(SourcePolicy(
    source_id="football_data",
    display_name="football-data.co.uk (Football-Data)",
    license_id="none-public-no-bots",
    license_summary=(
        "No open/public license found. Stated policy: free for private "
        "individuals only; NOT for commercial use or data-training products "
        "using automated bots/scrapers/AI. Treated as research-use-only with "
        "a human (non-bot) import step."
    ),
    collection_modes=[MODE_MANUAL_IMPORT, MODE_MANUAL_SNAPSHOT],
    rate_limit="n/a - automated retrieval is disallowed by source policy",
    verified_at="2026-09-19",
    evidence_urls=[
        "https://www.football-data.co.uk/data.php",
        "https://www.football-data.co.uk/matches.php",
        "https://www.football-data.co.uk/notes.txt",
    ],
    caveats=[
        "No per-event odds timestamps: prices are batch-collected (Fri 17:00 UK "
        "for weekend fixtures, Tue 13:00 UK for midweek) - snapshots are "
        "window-close-inferred, never exact.",
        "Pinnacle columns unreliable since 2025-07-23 per site notice; not "
        "used for market-average calculations here.",
        "Derived data must not be redistributed; keep raw imports local "
        "(data/imports/) and out of the published site.",
        "Residual legal risk: obtain explicit permission or a licensed "
        "alternative before scaling or any commercial use.",
    ],
))

# --- OLBG -----------------------------------------------------------------------
# Verified 2026-09-19 from https://www.olbg.com/use (Terms of Use, last updated
# 09 July 2025, operator Invendium Ltd, England & Wales 04490764):
#   7.1  "personal, non-commercial use and lawful purposes"
#   7.3  "not to access without our consent, interfere with, hack into, damage
#         or disrupt: 7.3.1 any part of our service"
#   9.1  "owner or the licensee of all intellectual property rights in our
#         service ... All rights are reserved"
#   9.2  "No copying or distribution of our service for any commercial or
#         business purpose is permitted without our prior written consent"
#   13.3 "You agree not to use our service for any commercial or business purposes"
# robots.txt (https://www.olbg.com/robots.txt) additionally disallows
# /api/, /sports/, /tipster/, /premium/, /newbg/.
_register(SourcePolicy(
    source_id="olbg",
    display_name="OLBG (Online Betting Guide, Invendium Ltd)",
    license_id="copyright-reserved",
    license_summary=(
        "All IP rights reserved (ToU 9.1). Personal, non-commercial use only "
        "(7.1, 13.3). No copying/distribution without prior written consent "
        "(9.2). Automated access without consent prohibited (7.3)."
    ),
    collection_modes=[MODE_MANUAL_SNAPSHOT],
    rate_limit="no bulk collection - manual snapshots for review only",
    verified_at="2026-09-19",
    evidence_urls=[
        "https://www.olbg.com/use",
        "https://www.olbg.com/robots.txt",
        "https://www.olbg.com/betting-tips",
    ],
    caveats=[
        "Automated collection is NOT permitted. The collector module is "
        "disabled by default and raises PolicyError if auto mode is attempted.",
        "Tipster claims on OLBG pages are unverified user content (ToU 5.4); "
        "imported tips stay 'pending' and never count to verified PnL.",
        "No permissioned API exists; /api/ and /sports/ are robots-disallowed.",
    ],
))
