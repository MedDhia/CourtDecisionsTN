#!/usr/bin/env python3
"""Combine the two coded tables into one, without altering either.

``data/decisions.csv`` holds the judgments the court publishes whole;
``data/digests.csv`` holds the ones its annual reports report in extract.  They
share most of their variables, so a single table is convenient -- but the same
decision can appear in both, and a report can print the same decision twice, so
a merged file that says nothing about that invites double counting.

Every row therefore carries ``source_type`` and, where it repeats a decision
recorded elsewhere in the table, ``duplicate_of``.  Filtering on an empty
``duplicate_of`` leaves one row per distinct decision.

Reads and writes only; the two source tables are left exactly as they are.
"""

import argparse
import csv
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DECISIONS = os.path.join(ROOT, "data", "decisions.csv")
DIGESTS = os.path.join(ROOT, "data", "digests.csv")
OUT_CSV = os.path.join(ROOT, "data", "all_decisions.csv")
OUT_JSON = os.path.join(ROOT, "data", "all_decisions.json")

# Analytic variables first, then the text the court supplied, then where each
# row came from and how to check it.
COLUMNS = [
    "record_id", "source_type",
    "case_number", "case_year",
    "decision_date", "decision_year", "decision_month",
    "court", "court_seat", "formation", "chamber_number",
    "president", "chamber_presidents", "counselors", "n_counselors",
    "bench_size", "prosecutor", "clerk",
    "origin_court", "origin_city",
    "subject_matter", "outcome",
    "title", "headnote", "citation",
    "source_report", "first_page", "last_page", "n_pages",
    "n_chars", "extraction_method", "ocr_agreement",
    "source_url", "sha256", "pdf_path", "txt_path",
    "full_text_id", "duplicate_of", "flags",
]

INTEGERS = {"case_year", "decision_year", "decision_month", "chamber_number",
            "n_counselors", "bench_size", "first_page", "last_page",
            "n_pages", "n_chars"}


def read(path):
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def bench_size(row):
    """Judges named on the bench, counted the same way for both sources."""
    if row.get("bench_size"):
        return row["bench_size"]
    named = 1 if row.get("president") else 0
    for field in ("chamber_presidents", "counselors"):
        if row.get(field):
            named += len(row[field].split("؛"))
    return str(named)


def normalise(row, source_type, key):
    out = {column: "" for column in COLUMNS}
    out.update({k: v for k, v in row.items() if k in out})
    out["record_id"] = row[key]
    out["source_type"] = source_type
    out["bench_size"] = bench_size(row)
    return out


def mark_duplicates(rows):
    """Point every repeat at the row it repeats.

    A decision is the same decision when its case number and date match.  The
    judgment published whole wins over an extract of it, and the first extract
    wins over a later one -- including across reports, which the per-report
    check in ``split_reports`` could not see.
    """
    canonical = {}
    # Full texts first, so they are the ones kept.
    order = sorted(range(len(rows)),
                   key=lambda i: (rows[i]["source_type"] != "full_text", i))
    for i in order:
        row = rows[i]
        if not row["case_number"] or not row["decision_date"]:
            continue  # cannot be matched, so cannot be a known repeat
        key = (row["case_number"], row["decision_date"])
        if key in canonical:
            row["duplicate_of"] = canonical[key]
        else:
            canonical[key] = row["record_id"]
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()

    rows = [normalise(r, "full_text", "decision_id") for r in read(DECISIONS)]
    rows += [normalise(r, "digest", "digest_id") for r in read(DIGESTS)]
    rows = mark_duplicates(rows)
    rows.sort(key=lambda r: (r["decision_date"] or "9999", r["record_id"]))

    with open(OUT_CSV, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    typed = []
    for row in rows:
        record = dict(row)
        for field in INTEGERS:
            record[field] = int(record[field]) if record[field] != "" else None
        typed.append(record)
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(typed, fh, ensure_ascii=False, indent=1)

    full = sum(1 for r in rows if r["source_type"] == "full_text")
    repeats = sum(1 for r in rows if r["duplicate_of"])
    print(f"data/all_decisions.csv: {len(rows)} rows "
          f"({full} full judgments, {len(rows) - full} digests), "
          f"{len(COLUMNS)} columns")
    print(f"  {repeats} rows repeat a decision recorded elsewhere in the table")
    print(f"  {len(rows) - repeats} distinct decisions")


if __name__ == "__main__":
    main()
