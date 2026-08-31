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

The second problem is that PyMuPDF splits one printed line into a fragment per
change of font or run direction, so "تاريخ الحكم 14/02/2019" arrives in five
pieces.  Those have to be rejoined right-to-left on an Arabic line; joining
them in reading order for a Latin script puts the year first.

What this module cannot fix is a PDF that misreports its own glyphs -- several
files here ship a corrupt ToUnicode CMap, and one maps every digit to the wrong
character.  ``extract.py`` catches those by comparing against OCR.
"""

import re
import unicodedata

import pymupdf

ARABIC_LETTER = re.compile(r"[ؠ-يٱ-ۓﭐ-﻿]")


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


def _page_lines(page):
    raw = page.get_text("rawdict")
    fragments = []
    for block in raw["blocks"]:
        for line in block.get("lines", []):
            chars = [c for span in line["spans"] for c in span["chars"]]
            text = _fix_ligatures(chars).strip()
            if text:
                fragments.append((line["bbox"][1], line["bbox"][0], text))

    fragments.sort(key=lambda f: (round(f[0], 1), f[1]))

    # PyMuPDF splits one printed line into several fragments wherever the font
    # or the run direction changes, so a date breaks into "14", "/", "02",
    # "/", "2019".  Group them back by baseline and read the group in the
    # line's own direction: left to right would put the year first.
    groups, prev_y = [], None
    for y, x, text in fragments:
        if prev_y is not None and abs(y - prev_y) < 3.0:
            groups[-1].append((x, text))
        else:
            groups.append([(x, text)])
            prev_y = y

    lines = []
    for group in groups:
        joined = " ".join(t for _x, t in group)
        if len(group) > 1 and ARABIC_LETTER.search(joined):
            group = sorted(group, key=lambda p: -p[0])
        lines.append(" ".join(t for _x, t in group))
    return lines


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
