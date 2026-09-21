"""Curated participant identity maps (no heuristics).

``data/aliases/<sport>.json`` lists spellings of the same participant that
a human has verified against an evidence link (docs/DARTS-AUDIT.md §3.4
explains why heuristic merging is refused: "Michael Smith" vs "Ross Smith"
would be merged wrongly by a surname rule).  Strategies canonicalise the
name *only for rating lookups/updates*; stored events keep the source's
raw spelling so provenance is untouched and the applied alias is written
into the model trail.

An alias file is refused (ValueError) when an entry lacks evidence, when
one raw name maps to two canonicals, or when a canonical is itself listed
as an alias of something else - a silent bad map would launder identity.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, Dict, List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALIAS_DIR = os.path.join(ROOT, "data", "aliases")


def validate_alias_table(doc: Dict[str, Any]) -> Dict[str, str]:
    """Return {raw_name: canonical} or raise ValueError."""
    if not isinstance(doc, dict) or not isinstance(doc.get("aliases"), list):
        raise ValueError("alias file must be an object with an 'aliases' list")
    mapping: Dict[str, str] = {}
    canonicals = set()
    for entry in doc["aliases"]:
        canonical = entry.get("canonical")
        names = entry.get("aliases") or []
        evidence = entry.get("evidence") or []
        if not canonical or not isinstance(names, list) or not names:
            raise ValueError(f"malformed alias entry: {entry!r}")
        if not evidence or not all(str(u).startswith("http") for u in evidence):
            raise ValueError(f"alias entry for {canonical!r} has no evidence "
                             "link - refused")
        if canonical in mapping:
            raise ValueError(f"{canonical!r} is both canonical and alias")
        canonicals.add(canonical)
        for raw in names:
            if raw == canonical:
                raise ValueError(f"{raw!r} aliases itself")
            if raw in canonicals:
                raise ValueError(f"{raw!r} is both canonical and alias")
            if raw in mapping and mapping[raw] != canonical:
                raise ValueError(f"{raw!r} maps to two canonicals")
            mapping[raw] = canonical
    return mapping


@lru_cache(maxsize=None)
def alias_map(sport: str) -> Dict[str, str]:
    path = os.path.join(ALIAS_DIR, f"{sport}.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    return validate_alias_table(doc)


def alias_version(sport: str) -> str:
    path = os.path.join(ALIAS_DIR, f"{sport}.json")
    if not os.path.exists(path):
        return "none"
    with open(path, encoding="utf-8") as fh:
        return str(json.load(fh).get("version", "unversioned"))


def canonical_name(sport: str, name: str) -> str:
    return alias_map(sport).get(name, name)


def applied_aliases(sport: str, names: List[str]) -> Dict[str, str]:
    """{raw: canonical} for the names that were actually remapped."""
    m = alias_map(sport)
    return {n: m[n] for n in names if n in m}
