"""UK civil time and odds-window utilities.

Two verified source facts drive this module:

1. football-data.co.uk ``Time`` column is UK local time. Verified 2026-09-19
   by cross-joining the D1 2024/25 file with OpenLigaDB ``matchDateTimeUTC``:
   23/08/2024 19:30 (CSV) == 18:30 UTC == 20:30 CEST; 09/11/2024 14:30 (CSV)
   == 14:30 UTC (UK on GMT after 27/10/2024); 01/02/2025 14:30 (CSV) ==
   14:30 UTC. All 27 pilot matches join exactly.

2. football-data.co.uk odds are batch-collected, quoted on
   https://www.football-data.co.uk/matches.php (verified 2026-09-19):
   "the odds are collected for the downloadable weekend fixtures on Fridays
   afternoons generally not later than 17:00 British Standard Time. Odds for
   midweek fixtures are collected Tuesdays not later than 13:00 British
   Standard Time."

So an odds snapshot's observed_at is the *close* of the collection window
that precedes kickoff - a conservative (earlier) bound that guarantees the
price existed before the event. Precision is recorded as
``window_close_inferred`` and never as ``exact``.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

UTC = timezone.utc

# "weekend fixtures" per the source = Fri-Sun (+ Mon) gameweek:
# Fri -> same day, Sat -> back 1 day, Mon -> back 3 days (to Friday)
WEEKEND_WEEKDAY_MAP = {4: 0, 5: 1, 0: 3}
MIDWEEK_TIMES = time(13, 0)          # Tue 13:00 UK (midweek fixtures)
WEEKEND_TIMES = time(17, 0)          # Fri 17:00 UK (weekend fixtures)


def _last_sunday(year: int, month: int) -> datetime:
    """Last Sunday of a month (UK clock change days)."""
    import calendar
    last_day = calendar.monthrange(year, month)[1]
    d = datetime(year, month, last_day, tzinfo=UTC)
    while d.weekday() != 6:
        d -= timedelta(days=1)
    return d


def uk_dst_start(year: int) -> datetime:
    """UK BST begins last Sunday of March, 01:00 UTC."""
    return _last_sunday(year, 3).replace(hour=1, minute=0)


def uk_dst_end(year: int) -> datetime:
    """UK BST ends last Sunday of October, 01:00 UTC."""
    return _last_sunday(year, 10).replace(hour=1, minute=0)


def uk_offset_at_utc(dt_utc: datetime) -> int:
    """UK civil offset in hours at a given instant (0=GMT, 1=BST)."""
    return 1 if uk_dst_start(dt_utc.year) <= dt_utc < uk_dst_end(dt_utc.year) else 0


def cet_offset_at_utc(dt_utc: datetime) -> int:
    """Central European civil offset in hours at a UTC instant (1=CET,
    2=CEST).  EU summer time runs from the last Sunday of March 01:00 UTC
    to the last Sunday of October 01:00 UTC - the same instants as the UK
    change (EU Directive 2000/84/EC), only the base offset differs.

    Used to cross-check OpenLigaDB rows: ``matchDateTime`` (local, tagged
    ``timeZoneID`` "W. Europe Standard Time") must equal
    ``matchDateTimeUTC`` + this offset.  Verified 2026-09-21 on all 1,187
    committed fixture rows (bl1/del pilots, bl1/del 2026, 8 PDC events):
    every row matches.
    """
    start = uk_dst_start(dt_utc.year)
    end = uk_dst_end(dt_utc.year)
    return 2 if start <= dt_utc < end else 1


def cet_local_to_utc(local) -> datetime:
    """Convert a naive CET/CEST wall time to an aware UTC instant.

    Verified source fact (docs/DARTS-AUDIT.md §3.2, reproduced 2026-09-22
    on 2,921 committed OpenLigaDB rows): ``lastUpdateDateTime`` and
    ``matchDateTime`` carry no timezone suffix and are German local time
    (CET/CEST) — a capture at 2026-09-20T20:08:53Z contained a row stamped
    ``22:07:50.923``, impossible if the stamp were UTC (22:07 > 20:08
    cannot be a retrieval time inside the capture that retrieved it).

    Reading rules (deterministic, tested):
    - an already-aware input is returned as UTC (nothing to resolve);
    - a naive wall time with exactly one self-consistent reading is exact;
    - the autumn fold-back hour (local 02:00–03:00 on the last Sunday of
      October, when it occurs twice) has two self-consistent readings and
      the spring-forward gap (the same local window on the last Sunday of
      March, when it occurs never) has none.  Both cases take the later
      (CET) algebraic reading: it is never *earlier* than the true
      instant, the conservative direction for every leakage-relevant use
      (availability/retrieval must not move earlier than provable).

    ``uk_local_to_utc`` refuses the clock-change days outright (human-
    entered OLBG times can simply ask a human again); this function serves
    bulk source ingestion where aborting a payload over one stamp would
    lose the whole matchday, so it degrades to the never-earlier bound
    instead of guessing the exact instant.  No committed OpenLigaDB stamp
    falls in either edge window (checked 2026-09-22).
    """
    if isinstance(local, str):
        local = datetime.fromisoformat(local)
    if local.tzinfo is not None:
        return local.astimezone(UTC)
    consistent = []
    for offset in (1, 2):  # CET (UTC+1), CEST (UTC+2)
        candidate = (local - timedelta(hours=offset)).replace(tzinfo=UTC)
        if cet_offset_at_utc(candidate) == offset:
            consistent.append(candidate)
    if len(consistent) == 2:      # fold-back hour: later (CET) reading
        return max(consistent)
    if consistent:                # unique reading: exact
        return consistent[0]
    # Spring-forward gap: the wall time cannot exist; take the later
    # (CET) algebraic reading — never earlier than the true instant.
    return (local - timedelta(hours=1)).replace(tzinfo=UTC)


def openligadb_local_matches_utc(local_iso: str, utc_iso: str) -> bool:
    """True when the source's local wall time equals UTC + CET/CEST."""
    local = datetime.fromisoformat(local_iso)
    utc_dt = datetime.fromisoformat(utc_iso.replace("Z", "+00:00"))
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=UTC)
    utc_dt = utc_dt.astimezone(UTC)
    expected = (utc_dt + timedelta(hours=cet_offset_at_utc(utc_dt))
                ).replace(tzinfo=None)
    return local.replace(tzinfo=None) == expected


def uk_local_to_utc(date, hm: time) -> datetime:
    """Convert a UK local wall time to UTC. ``date`` may be a date or a
    datetime (its date part is used).

    Raises ValueError on the two UK clock-change days (ambiguous/nonexistent
    local times) so a wrong assumption can never silently pass.
    """
    day = date.date() if isinstance(date, datetime) else date
    year = day.year
    change_days = {uk_dst_start(year).date(), uk_dst_end(year).date()}
    if day in change_days:
        raise ValueError(
            f"UK clock-change day {day}: local time ambiguous; "
            "refusing to guess. Use UTC directly."
        )
    dt_utc = datetime.combine(day, hm, tzinfo=UTC)
    # First guess assuming standard offset, then correct once.
    offset = uk_offset_at_utc(dt_utc)
    return dt_utc - timedelta(hours=offset)


def odds_collection_window_utc(kickoff_utc: datetime) -> datetime:
    """Close time (UTC) of the football-data.co.uk odds collection window
    that precedes the kickoff, per the source's own documented schedule.

    Weekend fixture (Fri-Sun or Mon kickoff): Friday 17:00 UK not later
    than. Midweek fixture (Tue-Thu kickoff): Tuesday 13:00 UK not later
    than. If the inferred window is not before kickoff (e.g. a Friday
    14:30 UK kickoff), fall back to the earlier documented window (same-
    week Tuesday 13:00 UK, else previous-week Friday 17:00 UK). The result
    is always <= the true collection time, i.e. the price provably existed
    before kickoff - the no-leakage direction.
    """
    # Work in UK wall time.
    offset = uk_offset_at_utc(kickoff_utc)
    uk_local = kickoff_utc + timedelta(hours=offset)
    weekday = uk_local.weekday()

    def window_utc_on(local: datetime) -> datetime:
        return local - timedelta(hours=uk_offset_at_utc(local))

    if weekday in WEEKEND_WEEKDAY_MAP:
        window_local = uk_local - timedelta(
            days=WEEKEND_WEEKDAY_MAP[weekday])
        window_local = window_local.replace(hour=17, minute=0, second=0,
                                            microsecond=0)
    else:
        window_local = uk_local - timedelta(days=weekday - 1)  # to Tuesday
        window_local = window_local.replace(hour=13, minute=0, second=0,
                                            microsecond=0)

    window_utc = window_utc_on(window_local)
    if window_utc >= kickoff_utc:
        tue_local = uk_local - timedelta(days=weekday - 1)
        tue_local = tue_local.replace(hour=13, minute=0, second=0,
                                      microsecond=0)
        window_utc = window_utc_on(tue_local)
        if window_utc >= kickoff_utc:
            fri_prev = uk_local - timedelta(days=weekday - 1 + 7)
            fri_prev = fri_prev.replace(hour=17, minute=0, second=0,
                                        microsecond=0)
            window_utc = window_utc_on(fri_prev)
    return window_utc
