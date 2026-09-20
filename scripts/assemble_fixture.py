"""Assemble fetched JSON chunks into a validated canonical fixture.

The chunks were captured from the OpenLigaDB API (ODbL-1.0, automated API
collection is a permitted mode for this source) via the agent's page-fetch
channel, which splits long payloads into ordered chunks with ```json fences
on the first/last chunk. This script concatenates the chunks, strips the
fences, validates strictly (parse + expected match IDs), and writes the
canonical compact JSON to the fixture path. Anything that does not parse or
fails the expected-match check is rejected - nothing is guessed.
"""
import json
import sys


def main() -> int:
    out_path, expected_ids = sys.argv[1], None
    chunk_paths = sys.argv[2:-1]
    try:
        expected_ids = set(json.loads(sys.argv[-1]))
    except json.JSONDecodeError:
        print("last arg must be a JSON list of expected matchIDs")
        return 2

    text = "".join(open(p, encoding="utf-8").read() for p in chunk_paths)
    if text.startswith("```json"):
        text = text[len("```json"):]
    text = text.strip()
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    payload = json.loads(text)  # raises on any corruption
    ids = [m["matchID"] for m in payload]
    missing = expected_ids - set(ids)
    extra = set(ids) - expected_ids
    if missing or extra:
        print(f"ID mismatch: missing={sorted(missing)} extra={sorted(extra)}")
        return 1
    for m in payload:
        assert m["leagueShortcut"] in ("del", "bl1"), m["leagueShortcut"]
        assert isinstance(m["matchIsFinished"], bool)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write("\n")
    print(f"OK {out_path}: {len(payload)} matches, ids {min(ids)}-{max(ids)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
