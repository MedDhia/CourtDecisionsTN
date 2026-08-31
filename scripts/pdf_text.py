"""Reconstruct clean, logical-order Arabic text from the court's decision PDFs.

The decisions on cassation.tn come out of a Word pipeline that lays glyphs out
in visual (right-to-left) order.  PyMuPDF re-orders those runs correctly, but a
glyph whose ToUnicode entry expands to *several* characters -- the lam-alef
ligatures, the "lillah" ligature -- has its expansion emitted in logical order
and then reversed along with everything else, so "الآتي" arrives as "اآلتي" and
"لله" as "هلل".

Such an expansion is easy to spot in the raw character stream: only the last
character of the group carries the glyph's real bbox, the rest are zero-width
markers pinned to its edge.  Re-reversing each of those groups restores the
text.

The second problem is ordering, at two levels.  Within a line, each directional
run comes back internally correct but the runs themselves are handed over left
to right, so the annual report's

    قرار تعقيبي عدد 66968.2018 بتاريخ 12 نوفمبر 2019 صادر عن الدائرة

arrives inside out, beginning at "صادر عن الدائرة".  And PyMuPDF often splits
one printed line into several line objects, which have to be rejoined the same
way.  Both are fixed by ordering right-to-left on an Arabic line.  Whitespace is
then re-derived from the gaps between runs, because a space written at the right
edge of a run ends up on its wrong side once the run order is reversed.

What this module cannot fix is a PDF that misreports its own glyphs -- several
files here ship a corrupt ToUnicode CMap, and one maps every digit to the wrong
character.  ``extract.py`` catches those by comparing against OCR.
"""

import re
import unicodedata

import pymupdf

ARABIC_LETTER = re.compile(r"[ؠ-يٱ-ۓﭐ-﻿]")

# Largest horizontal gap, in points, still counted as "same run".
GLYPH_GAP = 3.0


def _fix_ligatures(chars):
    """Undo the reversal applied to multi-character ToUnicode expansions.

    `chars` is PyMuPDF's raw character list for one line, already in logical
    order except for those groups.  A group is a run of zero-width characters
    followed by the one character that carries the glyph's real width.
    """
    out = []
    pending = []
    for ch in chars:
        c = ch["c"]
        zero_width = abs(ch["bbox"][2] - ch["bbox"][0]) < 0.01
        if zero_width and ARABIC_LETTER.match(c):
            pending.append(c)
        elif pending:
            if ARABIC_LETTER.match(c):
                # Complete group: [markers..., real] -> reverse to logical order.
                out.extend(reversed(pending + [c]))
            else:
                out.extend(pending)
                out.append(c)
            pending = []
        else:
            out.append(c)
    out.extend(pending)
    return "".join(out)


def _runs(chars):
    """Split a line's characters into directional runs.

    Glyphs within a run are written continuously in one direction, each box
    against the last.  A run ends where the pen jumps to a box that does not
    touch the previous one, or where the direction of travel reverses -- which
    is what separates an Arabic phrase from the number printed beside it.
    """
    runs = []
    prev = None
    direction = 0
    for ch in chars:
        x0, x1 = ch["bbox"][0], ch["bbox"][2]

        # A ligature's zero-width markers are pinned to the right edge of the
        # glyph they belong to, which can sit to the right of the character
        # before them and look like the line changing direction.  They are part
        # of whatever run is open, and never evidence about its direction.
        if runs and abs(x1 - x0) < 0.01:
            runs[-1][2].append(ch)
            continue

        start_new = True
        if prev is not None:
            px0, px1 = prev["bbox"][0], prev["bbox"][2]
            # Glyphs of one word can sit a point or two apart; a pen jump
            # between runs is tens of points, so the tolerance is generous.
            touching = min(px1, x1) >= max(px0, x0) - GLYPH_GAP
            step = (x0 > px0) - (x0 < px0)
            reversed_direction = step and direction and step != direction
            start_new = not touching or reversed_direction
            if not start_new and step:
                direction = step
        if start_new:
            runs.append([x0, x1, [ch]])
            direction = 0
        else:
            run = runs[-1]
            run[0], run[1] = min(run[0], x0), max(run[1], x1)
            run[2].append(ch)
        prev = ch
    return runs


def _line_text(chars):
    """Reassemble one printed line in logical order.

    Each run comes back internally correct, but the runs themselves are handed
    over left to right, so a right-to-left line arrives inside out: the report's
    "قرار تعقيبي عدد 66968.2018 بتاريخ 12 نوفمبر 2019 صادر عن الدائرة" reads as
    "صادر عن الدائرة 2019 نوفمبر 12 بتاريخ 66968.2018 قرار تعقيبي عدد".
    Ordering the runs by descending x puts them back.
    """
    runs = _runs(chars)
    if len(runs) < 2:
        return "".join(_fix_ligatures(r[2]) for r in runs)

    # Measure each run by its visible glyphs.  A space belongs to whichever
    # side of the run it was written on, which reversal would put on the wrong
    # side, so spacing is re-derived from the gaps between runs instead.
    measured = []
    for run in runs:
        inked = [c for c in run[2] if c["c"].strip()]
        if not inked:
            continue
        measured.append((min(c["bbox"][0] for c in inked),
                         max(c["bbox"][2] for c in inked),
                         _fix_ligatures(run[2]).strip()))
    if not measured:
        return ""

    if ARABIC_LETTER.search(_fix_ligatures(chars)):
        measured.sort(key=lambda r: -r[0])

    out = [measured[0][2]]
    for (ax0, ax1, _), (bx0, bx1, text) in zip(measured, measured[1:]):
        gap = max(ax0, bx0) - min(ax1, bx1)  # negative where they overlap
        out.append((" " if gap > 1.0 else "") + text)
    return "".join(out)


def page_items(page):
    """The page's printed lines, each with the styling it was set in.

    Returns dicts of ``text``, ``bold``, ``size`` and ``y``.  The styling is
    what tells a decision's headnote and citation apart from the body of the
    digest around it, which is how the annual reports get split up.
    """
    raw = page.get_text("rawdict")
    fragments = []
    for block in raw["blocks"]:
        for line in block.get("lines", []):
            chars = [c for span in line["spans"] for c in span["chars"]]
            text = _line_text(chars).strip()
            if not text:
                continue
            fonts = [span["font"] for span in line["spans"]]
            fragments.append({
                "y": line["bbox"][1],
                "x": line["bbox"][0],
                "text": text,
                "bold": any("Bold" in f or "Shafigh" in f for f in fonts),
                "size": max(span["size"] for span in line["spans"]),
            })

    fragments.sort(key=lambda f: (round(f["y"], 1), f["x"]))

    # PyMuPDF splits one printed line into several fragments wherever the font
    # or the run direction changes, so a date breaks into "14", "/", "02",
    # "/", "2019".  Group them back by baseline and read the group in the
    # line's own direction: left to right would put the year first.
    groups, prev_y = [], None
    for frag in fragments:
        if prev_y is not None and abs(frag["y"] - prev_y) < 3.0:
            groups[-1].append(frag)
        else:
            groups.append([frag])
            prev_y = frag["y"]

    items = []
    for group in groups:
        ordered = group
        if len(group) > 1 and ARABIC_LETTER.search(" ".join(f["text"] for f in group)):
            ordered = sorted(group, key=lambda f: -f["x"])
        items.append({
            "text": " ".join(f["text"] for f in ordered),
            "bold": any(f["bold"] for f in group),
            "size": max(f["size"] for f in group),
            "y": group[0]["y"],
        })
    return items


def _page_lines(page):
    return [item["text"] for item in page_items(page)]


_DIGIT_MAP = {}
for _base in (0x0660, 0x06F0):  # Arabic-Indic and Eastern Arabic-Indic
    _DIGIT_MAP.update({_base + i: str(i) for i in range(10)})


def normalise(text):
    """Tidy the reconstructed text without changing what it says."""
    text = unicodedata.normalize("NFKC", text)
    for junk in ("‏", "‎", "﻿", "​", "­"):
        text = text.replace(junk, "")
    text = text.replace(" ", " ")
    text = text.translate(_DIGIT_MAP)
    text = re.sub(r"ـ{2,}", "ـ", text)  # collapse kashida runs
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # A colon or full stop that closes an Arabic line is drawn at its left
    # edge, so it arrives at the front of the line: ":أصدرت محكمة التعقيب".
    # Put it back where it belongs.
    text = re.sub(r"^([:.؛،])\s*(?=.*[ء-ي])(.+)$", r"\2\1", text, flags=re.M)
    return text.strip()


def extract_pages(path):
    doc = pymupdf.open(path)
    try:
        return ["\n".join(_page_lines(p)) for p in doc]
    finally:
        doc.close()


def extract(path):
    return normalise("\n".join(extract_pages(path)))


if __name__ == "__main__":
    import sys

    for arg in sys.argv[1:]:
        print(f"===== {arg}")
        print(extract(arg))
