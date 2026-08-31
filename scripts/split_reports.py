#!/usr/bin/env python3
"""Split the court's annual reports into the individual decisions they report.

The reports are digests: for each decision the court prints a headnote, a
citation line, and the passage of the judgment it wants on the record.  In
running text those blur into one another, which is why plain-text search finds
no boundaries -- but they are set in different type, and the citation line is
always bold and always opens with "قرار".  That is the seam.

Each digest is written out as its own text file and coded with the same rules
as the standalone judgments in ``code_decisions``.  What comes out is an
extract, not a full judgment: it is recorded separately for that reason, and
carries the report and pages it was taken from.
"""

import argparse
import collections
import csv
import json
import os
import re
import sys

import pymupdf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import code_decisions as C  # noqa: E402
import pdf_text  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXTRACTION = os.path.join(ROOT, "data", "extraction.json")
TXT_DIR = os.path.join(ROOT, "digests", "txt")
OUT_CSV = os.path.join(ROOT, "data", "digests.csv")
OUT_JSON = os.path.join(ROOT, "data", "digests.json")
DECISIONS = os.path.join(ROOT, "data", "decisions.json")

# A citation line opens with "قرار", possibly after a bullet or dash.
ANCHOR = re.compile(r"^[\s\-–—«»•·]*قرار\s")
# It always carries a case number -- "عدد 407", or "عـ2016 / 370 ـدد" once
# justification kashidas are stripped -- and the year it issued.
HAS_NUMBER = re.compile(r"عدد|عـ|ـدد")
HAS_YEAR = re.compile(r"(?:19|20)\d{2}")
# Where the citation stops and the quoted judgment starts.
BODY_OPENS = re.compile(r"^[\s«»\"]*(?:حيث|عن\s|أولا|ثانيا|من\s+حيث|و?حيث)")

# Digests quote the reasoning, not the order; only a handful reach the operative
# part, and without it "رفض" in the text is the court describing an argument.
OPERATIVE = re.compile(r"لهذه\s+الاسباب|قررت\s+المحكمة")

MAX_HEADNOTE_LINES = 6
MAX_CITATION_LINES = 4


def is_anchor(text):
    return bool(ANCHOR.match(text) and HAS_NUMBER.search(text)
                and HAS_YEAR.search(text))


# Folio numbers and rules carry no content, and a citation that wraps across a
# page break is interrupted by them.
FURNITURE = re.compile(r"^[\d\s_.\-–—|]+$")


def read_report(path):
    """Every printed line of the report, with its styling and page.

    Page furniture is removed first.  It is not merely noise: the running
    header sits between the two halves of any citation that wraps onto the next
    page, and would otherwise cut the bench off mid-name.
    """
    doc = pymupdf.open(path)
    items = []
    try:
        pages = doc.page_count
        for number, page in enumerate(doc):
            for item in pdf_text.page_items(page):
                item = dict(item, page=number)
                item["text"] = pdf_text.normalise(item["text"])
                if item["text"] and not FURNITURE.match(item["text"]):
                    items.append(item)
    finally:
        doc.close()

    # Running heads repeat on nearly every page; nothing else does.
    seen = collections.Counter(
        (it["text"], it["page"]) for it in items if len(it["text"]) < 80)
    per_page = collections.Counter(text for text, _page in seen)
    running = {t for t, n in per_page.items() if n > pages * 0.4}
    return [it for it in items if it["text"] not in running]


def split(items):
    """Carve the report into one record per decision."""
    anchors = [i for i, it in enumerate(items)
               if it["bold"] and is_anchor(it["text"])]

    records = []
    for position, start in enumerate(anchors):
        # The headnote is the bold run immediately above the citation.
        headnote = []
        i = start - 1
        while (i >= 0 and items[i]["bold"] and len(headnote) < MAX_HEADNOTE_LINES
               and not is_anchor(items[i]["text"])
               and not BODY_OPENS.match(items[i]["text"])):
            headnote.insert(0, items[i]["text"])
            i -= 1

        # The citation itself often wraps onto the following bold lines.
        citation = [items[start]["text"]]
        j = start + 1
        while (j < len(items) and items[j]["bold"]
               and len(citation) < MAX_CITATION_LINES
               and not BODY_OPENS.match(items[j]["text"])
               and not is_anchor(items[j]["text"])):
            citation.append(items[j]["text"])
            j += 1

        end = anchors[position + 1] if position + 1 < len(anchors) else len(items)
        # Anything the next decision claims as its headnote is not ours.
        body_end = end
        k = end - 1
        while (k > j and items[k]["bold"]
               and end - k <= MAX_HEADNOTE_LINES
               and not BODY_OPENS.match(items[k]["text"])):
            body_end = k
            k -= 1

        body = [items[b]["text"] for b in range(j, body_end)]
        records.append({
            "headnote": " ".join(headnote),
            "citation": " ".join(citation),
            "body": "\n".join(body),
            "first_page": items[start]["page"] + 1,
            "last_page": items[max(body_end - 1, start)]["page"] + 1,
        })
    return records


YEAR = r"(?:19|20)\d{2}"
# The reports write the case number four ways.  Kashidas are stripped before
# matching, so "عـ2016 / 370 ـدد" arrives as "ع2016 / 370 دد".
NUMBER_FORMS = [
    # 2017's plenary citations put the year first: "عـ2016 / 370 ـدد"
    (rf"ع\s*({YEAR})\s*/\s*(\d{{1,6}})\s*د{{1,2}}", "year_first"),
    # Files joined for one decision: "عدد 46727 / 46728"
    (r"عدد\s*(\d{2,6})\s*[-/]\s*(\d{2,6})(?!\d)", "joined"),
    # "عدد 80441.2019" -- number then year of registration
    (rf"عدد\s*(\d{{2,6}})\s*[.,]\s*({YEAR})", "with_year"),
    (r"عدد\s*(\d{2,6})(?!\d)", "plain"),
    # Kashida form with nothing between: "عـ19190 ـدد"
    (r"ع\s*(\d{2,6})\s*د{1,2}", "plain"),
]


def citation_numbers(citation):
    """Case number(s) and year of registration, from a report's citation line."""
    folded = C.fold(citation)
    for pattern, kind in NUMBER_FORMS:
        m = re.search(pattern, folded)
        if not m:
            continue
        if kind == "year_first":
            return [m.group(2)], m.group(1)
        if kind == "joined":
            return [m.group(1), m.group(2)], ""
        if kind == "with_year":
            return [m.group(1)], m.group(2)
        return [m.group(1)], ""
    return [], ""


def code(record, report, index):
    """Code one digest, reading the bench out of its citation line."""
    citation = record["citation"]
    text = "\n".join(x for x in (record["headnote"], citation, record["body"]) if x)

    numbers, case_year = citation_numbers(citation)
    dates = C._dates_in(C.fold(citation))
    # The citation line is the whole of what the report says about the bench.
    people = C.panel(citation, block=citation)
    court_name, city = C.origin_court(text)

    # Kashida justification drops spaces into words: "الدوائر المجتم عة".
    folded_citation = re.sub(r"\s+", "", C.fold(citation))
    formation = ("الدوائر المجتمعة" if "الدوائرالمجتمعة" in folded_citation
                 else "دائرة" if "دائرة" in folded_citation else "")
    chamber = (None if formation == "الدوائر المجتمعة"
               else C.chamber_number(citation, block=citation))

    date = dates[0] if dates else ""
    return {
        "digest_id": f"{report}-{index:03d}",
        "case_number": "/".join(numbers),
        "case_year": case_year or "",
        "decision_date": date,
        "decision_year": date[:4] if date else "",
        "decision_month": date[5:7] if date else "",
        "court": "محكمة التعقيب",
        "court_seat": "تونس",
        "formation": formation,
        "chamber_number": chamber or "",
        "president": people["president"],
        "counselors": "؛".join(people["counselors"]),
        "n_counselors": len(people["counselors"]),
        "prosecutor": people["prosecutor"],
        "clerk": people["clerk"],
        "origin_court": court_name,
        "origin_city": city,
        "subject_matter": C.subject_matter(text),
        "outcome": C.outcome(text) if OPERATIVE.search(C.fold(text)) else "",
        "headnote": record["headnote"],
        "citation": citation,
        "source_report": report,
        "first_page": record["first_page"],
        "last_page": record["last_page"],
        "n_chars": len(text),
        "txt_path": f"digests/txt/{report}-{index:03d}.txt",
        "full_text_id": "",
        "flags": "",
    }, text


REPORTS = {
    "2019": "publications/pdf/2019.pdf",
    "2020": "publications/pdf/2020.pdf",
    "2017": "publications/pdf/rapport-annuel-2017.pdf",
}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", help="process a single report by key")
    args = ap.parse_args()

    os.makedirs(TXT_DIR, exist_ok=True)
    rows = []
    for report, rel in REPORTS.items():
        if args.only and args.only != report:
            continue
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            print(f"missing {rel}; run scripts/extract.py first")
            continue
        items = read_report(path)
        records = split(items)
        print(f"{report}: {len(records)} decisions over {items[-1]['page'] + 1} pages")
        for index, record in enumerate(records, 1):
            row, text = code(record, report, index)
            with open(os.path.join(ROOT, row["txt_path"]), "w",
                      encoding="utf-8") as fh:
                fh.write(text + "\n")
            rows.append(row)

    # A handful of the digested decisions are also published whole on the
    # court's site.  Linking them lets the two readings be compared, and they
    # agree: case number, date, formation and chamber match on every pair.
    if os.path.exists(DECISIONS):
        full = {}
        for row in json.load(open(DECISIONS, encoding="utf-8")):
            for number in row["case_number"].split("/"):
                if number:
                    full[(number, row["decision_date"])] = row["decision_id"]
        for row in rows:
            for number in row["case_number"].split("/"):
                match = full.get((number, row["decision_date"]))
                if match:
                    row["full_text_id"] = match
                    break

    # A report sometimes discusses one decision twice, under two headings, with
    # a different extract each time.  Both are kept -- the headnotes differ and
    # are part of what the report says -- but the repeat is marked so nobody
    # counts the same judgment twice.
    seen = {}
    for row in rows:
        key = (row["source_report"], row["case_number"], row["decision_date"])
        if not row["case_number"]:
            continue
        if key in seen:
            row["flags"] = f"repeat_of:{seen[key]}"
        else:
            seen[key] = row["digest_id"]

    rows.sort(key=lambda r: (r["source_report"], r["digest_id"]))
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=1)

    filled = {k: sum(1 for r in rows if str(r[k]).strip()) for k in rows[0]}
    print(f"\ncoded {len(rows)} digests -> data/digests.csv\n")
    for key, count in filled.items():
        print(f"{key:<18} {count:>5}/{len(rows)}")


if __name__ == "__main__":
    main()
