#!/usr/bin/env python3
"""Sort the downloaded PDFs and give each one a clean UTF-8 .txt rendering.

Two independent readings are produced for every document:

  * the embedded text layer, re-ordered by ``pdf_text`` -- accurate spacing and
    punctuation, but worthless when the PDF ships a corrupt ToUnicode CMap,
    which several files in this corpus do (one decodes "الاستئناف" as
    "الاستتننا", another maps every digit glyph to the wrong number);
  * Tesseract OCR of the rendered pages, which cannot be fooled by a bad CMap
    but is slightly noisier on punctuation and spacing.

The two are compared, on words and on numbers separately, and the text layer is
kept only where it agrees with what the page actually renders.  Anything else
falls back to OCR.  On long documents the comparison runs on a sample of pages,
since re-OCRing a 592-page annual report to validate it is not worth the hour.

Court decisions land in decisions/, everything else the court publishes
(annual reports, colloquium programmes, hearing schedules) lands in
publications/.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import pymupdf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pdf_text  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOWNLOADS = os.path.join(ROOT, "downloads")
SOURCES = os.path.join(ROOT, "data", "sources.json")
REPORT = os.path.join(ROOT, "data", "extraction.json")
# OCR is the slow part of the pipeline; cache it so the text-reconstruction and
# coding rules can be iterated on without re-reading every page.
CACHE = os.path.join(ROOT, ".ocr-cache")

# Tesseract's automatic page segmentation.  "--psm 6" (one uniform block) is
# tempting for a judgment, but it silently drops the odd line -- in 88085.pdf
# the entire bench of the deciding chamber -- so the default wins.
# Tesseract silently drops whole lines, and which pages it drops them on
# depends on both the segmentation mode and the rendering resolution:
# "--psm 6" loses the entire bench of the deciding chamber in 88085.pdf,
# "--psm 3" loses it in 87942.pdf, and 87942 only comes back at 400 dpi -- while
# 13844 reads better at 300.  No single setting wins, so each page is read under
# all four and the richest reading kept.  OCR omits text, it does not invent it,
# so "recovered the most words" is a safe way to choose.
OCR_PSM_MODES = ("3", "6")
OCR_DPIS = (300, 400)
# Below this token overlap the embedded text layer is treated as unusable.
# Measured over this corpus the score is sharply bimodal: intact files land at
# 0.89-0.94, and every file below 0.70 turns out to have a damaged font -- the
# worst of them decode the panel's presiding judge "شلغوم" as "ولغوم".  There is
# nothing in between, so the cut sits in the gap.
AGREEMENT_FLOOR = 0.80
# Case numbers and dates are the point of the exercise, so numbers are held to
# a stricter standard than prose.
DIGIT_FLOOR = 0.70
# Pages to OCR when spot-checking a long document.
SAMPLE_PAGES = 12

_STRIP = re.compile(r"[ً-ْٰٟـ]")  # harakat + tatweel


def canonical(text):
    """Fold spelling variants so OCR and the text layer can be compared."""
    text = _STRIP.sub("", text)
    text = re.sub(r"[أإآٱ]", "ا", text)
    text = text.replace("ى", "ي").replace("ة", "ه")
    return re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)


def tokens(text):
    return {t for t in canonical(text).split() if len(t) > 2}


def agreement(a, b):
    """Fraction of the smaller vocabulary that the two readings share."""
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def digit_agreement(a, b):
    """The same measure restricted to numbers.

    A PDF can decode its letters perfectly and still map every digit glyph to
    the wrong character -- 20918-18.pdf reads its own case number as "81902" --
    which barely dents the word score but would corrupt every case number and
    date we extract.
    """
    na = set(re.findall(r"\d{2,}", a))
    nb = set(re.findall(r"\d{2,}", b))
    if not na or not nb:
        return 1.0  # nothing to disagree about
    return len(na & nb) / min(len(na), len(nb))


ARABIC_WORD = re.compile(r"[ء-ي]{3,}")


def _richness(text):
    """How much of the page a reading actually recovered.

    Distinct words, not total words and not characters.  A dropped line costs a
    reading most of that line's vocabulary, while the re-tokenisation noise
    between two readings of the same page shuffles words without adding new
    ones -- on page 3 of 90873.pdf the reading that loses the whole bench still
    has *more* word tokens than the one that keeps it, and 10% fewer distinct.
    """
    return (len(set(ARABIC_WORD.findall(text))), len(text))


def ocr_pages(path, indices, lang="ara", thorough=True):
    """Render the given pages and read them with Tesseract.

    ``thorough`` reads every page under all four render/segmentation settings.
    That is worth the four-fold cost on a judgment, where a dropped line can
    cost the whole bench, and not worth it on a 44-page report.
    """
    os.makedirs(CACHE, exist_ok=True)
    dpis = OCR_DPIS if thorough else OCR_DPIS[:1]
    modes = OCR_PSM_MODES if thorough else OCR_PSM_MODES[:1]
    key = hashlib.sha1(
        f"{os.path.basename(path)}|{lang}|{dpis}|"
        f"{'+'.join(modes)}".encode()).hexdigest()[:16]
    cache_file = os.path.join(CACHE, key + ".json")
    cached = {}
    if os.path.exists(cache_file):
        cached = json.load(open(cache_file, encoding="utf-8"))

    todo = [i for i in indices if str(i) not in cached]
    if todo:
        doc = pymupdf.open(path)
        tmp = tempfile.mkdtemp(prefix="ocr-")
        try:
            for index in todo:
                readings = []
                for dpi in dpis:
                    png = os.path.join(tmp, f"p{index}-{dpi}.png")
                    doc[index].get_pixmap(dpi=dpi).save(png)
                    for psm in modes:
                        proc = subprocess.run(
                            ["tesseract", png, "stdout", "-l", lang,
                             "--psm", psm],
                            capture_output=True, text=True, check=False,
                        )
                        readings.append(pdf_text.normalise(proc.stdout))
                # Every reading is kept, so the choice between them can be
                # revisited without paying for the OCR again.
                cached[str(index)] = readings
                # Written page by page so an interrupted run keeps its work.
                with open(cache_file, "w", encoding="utf-8") as fh:
                    json.dump(cached, fh, ensure_ascii=False)
        finally:
            doc.close()
            shutil.rmtree(tmp, ignore_errors=True)

    return [max(cached[str(i)], key=_richness) for i in indices]


def sample_indices(page_count):
    if page_count <= SAMPLE_PAGES * 2:
        return list(range(page_count))
    step = page_count / SAMPLE_PAGES
    return sorted({min(page_count - 1, int(i * step)) for i in range(SAMPLE_PAGES)})


DECISION_MARKERS = ("محكمة التعقيب", "قرار تعقيبي", "قضية عدد", "القضية عدد",
                    "مطلب التعقيب", "لهذه الاسباب", "قررت المحكمة",
                    "اصدرت محكمة التعقيب", "الحق العام", "المعقب ضده",
                    "الحكم المطعون فيه", "محكمة الاستئناف")


def is_decision(text, page_count):
    """A single judgment, as opposed to a report, programme or schedule.

    Markers are matched on the canonical form because the files are inconsistent
    about hamza ("أصدرت" / "اصدرت") and OCR drops it more often still.  The
    annual reports quote all the same phrases, so length does the real
    separating: no individual decision in this corpus runs past ~40 pages.
    """
    folded = canonical(text)
    return (sum(canonical(m) in folded for m in DECISION_MARKERS) >= 3
            and page_count <= 40)


def arabic_ratio(text):
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return sum("؀" <= c <= "ۿ" for c in letters) / len(letters)


VOWELS = set("aeiouyàâäéèêëîïôöùûüAEIOUY")


def latin_looks_like_words(text):
    """Cheap sanity check on a Latin-script text layer.

    Some scanned pages carry a text layer that is pure noise -- "f.1guu n,.n4\\"
    -- and it has to be told apart from real French without a French OCR model
    to compare against.  Genuine prose is nearly all vowel-bearing words.
    """
    words = [w for w in re.findall(r"[^\W\d_]{3,}", text, re.UNICODE)
             if not any("؀" <= c <= "ۿ" for c in w)]
    if len(words) < 20:
        return False
    return sum(any(c in VOWELS for c in w) for w in words) / len(words) > 0.75


def process(entry, do_ocr=True):
    path = os.path.join(ROOT, entry["file"])
    doc = pymupdf.open(path)
    page_count = doc.page_count
    doc.close()

    embedded_pages = pdf_text.extract_pages(path)
    embedded = pdf_text.normalise("\n".join(embedded_pages))

    record = {
        "stem": os.path.splitext(os.path.basename(entry["file"]))[0],
        "url": entry["url"],
        "sha256": entry.get("sha256"),
        "pages": page_count,
        "title": entry["links"][0] if entry.get("links") else "",
        "embedded_chars": len(embedded),
    }

    record["arabic_ratio"] = round(arabic_ratio(embedded), 3)
    latin = record["arabic_ratio"] < 0.3

    # The corpus has no French OCR model, so a French text layer cannot be
    # scored against a re-reading of the page.  It does not need to be: the
    # broken CMaps are an Arabic-font problem, and a Latin text layer that
    # reads as real words is trustworthy on its face.
    if not do_ocr or (latin and latin_looks_like_words(embedded)):
        record.update(method="text-layer", agreement=None, digit_agreement=None)
        return record, embedded

    lang = "ara+eng" if latin else "ara"
    indices = sample_indices(page_count)
    # A judgment in this corpus never runs past 40 pages; anything longer is
    # a report, and does not need the expensive reading.
    thorough = page_count <= 40
    scanned = ocr_pages(path, indices, lang=lang, thorough=thorough)
    sampled_embedded = pdf_text.normalise(
        "\n".join(embedded_pages[i] for i in indices))
    sampled_ocr = "\n".join(scanned)

    record["sampled_pages"] = len(indices)
    record["agreement"] = round(agreement(sampled_embedded, sampled_ocr), 3)
    record["digit_agreement"] = round(
        digit_agreement(sampled_embedded, sampled_ocr), 3)

    # Numbers only have to match on documents short enough to be a judgment.
    # Long reports are full of statistical tables whose figures OCR unreliably,
    # and re-reading 500 pages over a page-number disagreement helps nobody.
    digits_ok = (record["digit_agreement"] >= DIGIT_FLOOR or page_count > 40)
    usable = (record["agreement"] >= AGREEMENT_FLOOR
              and digits_ok
              and len(embedded) > 200)
    if usable:
        record["method"] = "text-layer"
        return record, embedded

    # The embedded encoding disagrees with what the page renders: trust pixels.
    record["method"] = "ocr"
    if len(indices) == page_count:
        text = "\n".join(scanned)
    else:
        text = "\n".join(ocr_pages(path, range(page_count), lang=lang,
                                   thorough=thorough))
    return record, pdf_text.normalise(text)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-ocr", action="store_true",
                    help="skip the OCR cross-check (text layer taken as-is)")
    ap.add_argument("--only", help="process only files whose name contains this")
    args = ap.parse_args()

    sources = json.load(open(SOURCES, encoding="utf-8"))
    for kind in ("decisions", "publications"):
        for sub in ("pdf", "txt"):
            os.makedirs(os.path.join(ROOT, kind, sub), exist_ok=True)

    report = []
    for entry in sources:
        if not entry.get("file"):
            continue
        if args.only and args.only not in entry["file"]:
            continue

        record, text = process(entry, do_ocr=not args.no_ocr)
        kind = "decisions" if is_decision(text, record["pages"]) else "publications"
        record["kind"] = kind
        record["chars"] = len(text)

        stem = record["stem"]
        shutil.copyfile(os.path.join(ROOT, entry["file"]),
                        os.path.join(ROOT, kind, "pdf", stem + ".pdf"))
        with open(os.path.join(ROOT, kind, "txt", stem + ".txt"),
                  "w", encoding="utf-8") as fh:
            fh.write(text + "\n")

        record["pdf"] = f"{kind}/pdf/{stem}.pdf"
        record["txt"] = f"{kind}/txt/{stem}.txt"
        report.append(record)
        print(f"{stem:<34} {kind:<12} {record['method']:<10} "
              f"words={record['agreement']} digits={record['digit_agreement']}",
              flush=True)

    report.sort(key=lambda r: (r["kind"], r["stem"]))
    with open(REPORT, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)

    decisions = [r for r in report if r["kind"] == "decisions"]
    ocred = sum(r["method"] == "ocr" for r in report)
    print(f"\n{len(decisions)} decisions and {len(report) - len(decisions)} other "
          f"publications; {ocred} needed OCR")


if __name__ == "__main__":
    main()
