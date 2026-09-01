#!/usr/bin/env python3
"""Draw the corpus figures into figures/.

Each figure is written as PDF (vector, for a LaTeX paper) and PNG (for reading
on screen).  They are light-mode only: the target is print, where a dark surface
has no meaning.

Colours come from the reference palette in the dataviz skill and are used at two
categorical slots (blue, orange) plus a neutral for "not stated", which is an
absence rather than a series -- a combination that clears the all-pairs
colourblind gates with room to spare.  Marks are capped and thin, gridlines are
hairline and recessive, stacked segments are separated by a gap in the surface
colour rather than by a stroke, and no text ever wears a series colour.
"""

import argparse
import collections
import json
import os

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "figures")

# --- palette (light mode) ----------------------------------------------------
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
BLUE = "#2a78d6"      # categorical slot 1
ORANGE = "#eb6834"    # categorical slot 2
NEUTRAL = "#b5b3ab"   # "not stated" -- an absence, not an identity
# Sequential blue, steps 100..700 of the same hue.
SEQUENTIAL = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7",
              "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281",
              "#0d366b"]


def setup_fonts():
    # Noto Sans for Latin and Noto Sans Arabic for the Arabic that falls through
    # to it: one superfamily, so the two scripts sit together instead of
    # looking pasted side by side.  Matplotlib shapes and orders the Arabic
    # itself -- pre-shaping it with arabic_reshaper/bidi applies the transform
    # a second time and comes out mirrored.
    plt.rcParams.update({
        # DejaVu closes the chain for the few maths symbols ("≥") that
        # neither Noto face carries.
        "font.family": ["Noto Sans", "Noto Sans Arabic", "DejaVu Sans"],
        "font.size": 9,
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "axes.edgecolor": AXIS,
        "axes.labelcolor": INK_2,
        "axes.titlecolor": INK,
        "text.color": INK,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "xtick.labelcolor": INK_2,
        "ytick.labelcolor": INK_2,
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "grid.linestyle": "-",
        "axes.grid": False,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "legend.frameon": False,
        "figure.dpi": 110,
        "pdf.fonttype": 42,
    })


SUBHEAD_LINE = 12.5  # rendered height of one 8.5pt subhead line in Noto Sans


def title(ax, headline, subhead=None):
    """Headline above subhead above the plot, measured so they never collide."""
    lines = subhead.count("\n") + 1 if subhead else 0
    if subhead:
        ax.annotate(subhead, xy=(0, 1), xycoords="axes fraction",
                    xytext=(0, 7), textcoords="offset points",
                    fontsize=8.5, color=INK_2, va="bottom", ha="left",
                    linespacing=1.15)
    ax.set_title(headline, loc="left",
                 pad=10 + SUBHEAD_LINE * lines + (5 if subhead else 0),
                 fontsize=11.5, fontweight="bold", color=INK)


def stacked(values, gap):
    """Shorten each segment by the surface gap, but never to nothing.

    A gap subtracted flat erases a segment of one or two — which is most of what
    a corpus like this has in its thin years.
    """
    return [v - gap if v > gap * 2.5 else v for v in values]


def save(fig, name):
    os.makedirs(OUT, exist_ok=True)
    for ext, kwargs in (("pdf", {}), ("png", {"dpi": 200})):
        fig.savefig(os.path.join(OUT, f"{name}.{ext}"),
                    bbox_inches="tight", **kwargs)
    plt.close(fig)
    print(f"  figures/{name}.pdf, .png")


def load():
    with open(os.path.join(ROOT, "data", "all_decisions.json"),
              encoding="utf-8") as fh:
        merged = json.load(fh)
    with open(os.path.join(ROOT, "data", "extraction.json"),
              encoding="utf-8") as fh:
        extraction = json.load(fh)
    return merged, [r for r in extraction if r["kind"] == "decisions"]


# --- 1. why the text layer is not trusted ------------------------------------

def figure_extraction(records):
    fig, ax = plt.subplots(figsize=(6.4, 4.4))
    kept = [r for r in records if r["method"] == "text-layer"]
    ocr = [r for r in records if r["method"] == "ocr"]

    for rows, colour, label in ((kept, BLUE, "Text layer kept"),
                                (ocr, ORANGE, "Read by OCR instead")):
        ax.scatter([r["agreement"] for r in rows],
                   [r["digit_agreement"] for r in rows],
                   s=70, c=colour, edgecolors=SURFACE, linewidths=1.6,
                   zorder=3, label=label)

    # The two tests, drawn where they cut.
    ax.axvline(0.80, color=AXIS, lw=0.9, zorder=1)
    ax.axhline(0.70, color=AXIS, lw=0.9, zorder=1)
    ax.text(0.788, 0.44, "words ≥ 0.80", fontsize=8, color=MUTED,
            va="center", ha="right")
    ax.text(0.02, 0.715, "numbers ≥ 0.70", fontsize=8, color=MUTED, va="bottom")

    # The point of the figure: files the word test alone would have passed.
    caught = sorted((r for r in ocr if r["agreement"] >= 0.80),
                    key=lambda r: r["stem"])
    if caught:
        ax.annotate(
            "Letters right, digits wrong:\n" + ", ".join(r["stem"] for r in caught),
            xy=(min(r["agreement"] for r in caught) - 0.005,
                sum(r["digit_agreement"] for r in caught) / len(caught)),
            xytext=(0.40, 0.20), fontsize=8.5, color=INK_2,
            ha="left", va="center", linespacing=1.2,
            arrowprops=dict(arrowstyle="-", color=AXIS, lw=0.9,
                            shrinkA=2, shrinkB=8))

    ax.set_xlim(-0.02, 1.06)
    ax.set_ylim(-0.09, 1.08)
    ax.set_xlabel("Agreement on words")
    ax.set_ylabel("Agreement on numbers")
    ax.xaxis.grid(True, zorder=0)
    ax.yaxis.grid(True, zorder=0)
    ax.set_axisbelow(True)
    ax.legend(loc="upper left", bbox_to_anchor=(0, -0.13), ncol=2,
              handletextpad=0.4, columnspacing=1.8, fontsize=9)
    title(ax, "The text layer is only trusted where it matches the page",
          "Each of the 27 judgments read twice — once from the PDF's text layer, once by OCR — "
          "and\nthe two compared. The four named files decode every letter correctly and every digit wrong.")
    save(fig, "extraction-quality")


# --- 2. what is actually coded, and where -----------------------------------

FIELDS = [
    ("case_number", "Case number"),
    ("decision_date", "Decision date"),
    ("formation", "Formation"),
    ("chamber_number", "Chamber number"),
    ("president", "Presiding judge"),
    ("counselors", "Counsellors"),
    ("prosecutor", "Prosecutor"),
    ("clerk", "Clerk"),
    ("subject_matter", "Subject matter"),
    ("case_year", "Year of registration"),
    ("origin_court", "Court appealed from"),
    ("outcome", "Disposition"),
]


def figure_coverage(merged):
    groups = [("full_text", "Published whole"), ("digest", "Digest")]
    counts = {key: [r for r in merged if r["source_type"] == key]
              for key, _ in groups}

    grid = [[sum(1 for r in counts[key] if r[field] not in ("", None))
             / len(counts[key]) for key, _ in groups]
            for field, _ in FIELDS]

    fig, ax = plt.subplots(figsize=(5.2, 5.2))
    for row, values in enumerate(grid):
        for col, value in enumerate(values):
            step = SEQUENTIAL[min(int(value * len(SEQUENTIAL)),
                                  len(SEQUENTIAL) - 1)]
            # A 2px surface gap does the separating; no stroke on the mark.
            ax.add_patch(plt.Rectangle((col + 0.02, row + 0.02), 0.96, 0.96,
                                       facecolor=step, linewidth=0))
            ax.text(col + 0.5, row + 0.5, f"{value * 100:.0f}%",
                    ha="center", va="center", fontsize=8.5,
                    color="#ffffff" if value > 0.55 else INK)

    ax.set_xlim(0, len(groups))
    ax.set_ylim(len(FIELDS), 0)
    ax.set_xticks([i + 0.5 for i in range(len(groups))])
    ax.set_xticklabels([f"{label}\n(n={len(counts[key])})"
                        for key, label in groups], fontsize=9)
    ax.set_yticks([i + 0.5 for i in range(len(FIELDS))])
    ax.set_yticklabels([label for _f, label in FIELDS], fontsize=9)
    ax.xaxis.set_ticks_position("top")
    for side in ("top", "right", "bottom", "left"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0)
    ax.set_title("How much of each record the source actually states",
                 loc="left", pad=40, fontsize=11.5, fontweight="bold", color=INK)
    ax.annotate("Share of rows carrying a value. Empty means the document does not say it —\n"
                "nothing is imputed. The reports name no bench for a plenary sitting, and\n"
                "their extracts stop before the disposition.",
                xy=(0, 0), xycoords="axes fraction",
                xytext=(0, -22), textcoords="offset points",
                fontsize=8.5, color=INK_2, va="top", ha="left", linespacing=1.15)
    save(fig, "corpus-coverage")


# --- 3. when the reported decisions were decided -----------------------------

CHAMBER, PLENARY, UNSTATED = "دائرة", "الدوائر المجتمعة", ""
SERIES = [(CHAMBER, f"Ordinary chamber  {CHAMBER}", BLUE),
          (PLENARY, f"Joined chambers  {PLENARY}", ORANGE),
          (UNSTATED, "Not stated", NEUTRAL)]


def figure_years(merged):
    unique = [r for r in merged if not r["duplicate_of"] and r["decision_year"]]
    years = sorted({r["decision_year"] for r in unique})
    counts = collections.Counter((r["decision_year"], r["formation"])
                                 for r in unique)

    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    bottoms = [0] * len(years)
    gap = 1.8  # surface gap between stacked segments, in decision counts
    for key, label, colour in SERIES:
        values = [counts.get((y, key), 0) for y in years]
        ax.bar(range(len(years)), stacked(values, gap), bottom=bottoms,
               width=0.30, color=colour, linewidth=0, label=label, zorder=3)
        bottoms = [b + v for b, v in zip(bottoms, values)]

    for x, total in enumerate(bottoms):
        ax.text(x, total + 4, f"{total:,}", ha="center", fontsize=8.5,
                color=INK_2)

    ax.set_xticks(range(len(years)))
    ax.set_xticklabels(years)
    ax.set_ylabel("Decisions")
    ax.set_ylim(0, max(bottoms) * 1.14)
    ax.yaxis.grid(True, zorder=0)
    ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False)
    ax.tick_params(length=0)
    ax.legend(loc="upper left", bbox_to_anchor=(0, -0.12), ncol=3,
              handlelength=0.9, handleheight=0.9, handletextpad=0.5,
              columnspacing=1.8, fontsize=9)
    title(ax, "The corpus is three judicial years, not a time series",
          "512 distinct decisions by the year they were decided. Coverage follows which annual\n"
          "reports the court has published — 2017, 2019 and 2020 — not how much it decided.")
    save(fig, "decisions-by-year")


# --- 4. what areas of law they come from -------------------------------------

# (value in the data, English label, the term as the court writes it)
SUBJECTS = [("مدني", "Civil", "مدني"),
            ("جزائي", "Criminal", "جزائي"),
            ("تجاري", "Commercial", "تجاري"),
            ("شغل", "Labour", "شغل"),
            ("احوال شخصية", "Personal status", "أحوال شخصية"),
            ("عقاري", "Land and registration", "عقاري"),
            ("", "Not classified", "")]


def figure_subjects(merged):
    unique = [r for r in merged if not r["duplicate_of"]]
    counts = collections.Counter((r["subject_matter"], r["formation"])
                                 for r in unique)
    totals = {key: sum(counts.get((key, f), 0) for f, _l, _c in SERIES)
              for key, _e, _a in SUBJECTS}
    order = sorted(SUBJECTS, key=lambda s: (s[0] == "", -totals[s[0]]))[::-1]

    fig, ax = plt.subplots(figsize=(7.0, 3.9))
    lefts = [0] * len(order)
    gap = 1.8
    for key, label, colour in SERIES:
        values = [counts.get((s, key), 0) for s, _e, _a in order]
        ax.barh(range(len(order)), stacked(values, gap), left=lefts,
                height=0.38, color=colour, linewidth=0, label=label, zorder=3)
        lefts = [l + v for l, v in zip(lefts, values)]

    for y, total in enumerate(lefts):
        ax.text(total + 3, y, f"{total}", va="center", fontsize=8.5, color=INK_2)

    ax.set_yticks(range(len(order)))
    ax.set_yticklabels([f"{english}  {arabic}".strip()
                        for _key, english, arabic in order], fontsize=9)
    ax.set_xlabel("Decisions")
    ax.set_xlim(0, max(lefts) * 1.10)
    ax.xaxis.grid(True, zorder=0)
    ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False)
    ax.tick_params(length=0)
    ax.legend(loc="upper left", bbox_to_anchor=(0, -0.15), ncol=3,
              handlelength=0.9, handleheight=0.9, handletextpad=0.5,
              columnspacing=1.8, fontsize=9)
    title(ax, "Civil and criminal work dominates the published jurisprudence",
          "512 distinct decisions. Subject matter is inferred from the legal vocabulary of each\n"
          "text, not stated by the court — read it as indicative.")
    save(fig, "subject-matter")


# --- 5. which chambers appear ------------------------------------------------

def figure_chambers(merged):
    unique = [r for r in merged if not r["duplicate_of"] and r["chamber_number"]]
    counts = collections.Counter(int(r["chamber_number"]) for r in unique)
    top = counts.most_common(12)
    tail = sum(v for _k, v in counts.most_common()[12:])
    labels = [f"Chamber {k}" for k, _v in top]
    values = [v for _k, v in top]
    if tail:
        labels.append(f"{len(counts) - 12} other chambers")
        values.append(tail)

    fig, ax = plt.subplots(figsize=(6.0, 4.2))
    positions = range(len(values))[::-1]
    # Nominal categories: one series, one colour. Never a ramp by size.
    ax.barh(list(positions), values, height=0.42, color=BLUE, linewidth=0,
            zorder=3)
    for y, value in zip(positions, values):
        ax.text(value + 1.2, y, str(value), va="center", fontsize=8.5,
                color=INK_2)

    ax.set_yticks(list(positions))
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel("Decisions")
    ax.set_xlim(0, max(values) * 1.10)
    ax.xaxis.grid(True, zorder=0)
    ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False)
    ax.tick_params(length=0)
    title(ax, f"{len(counts)} of the court's chambers appear in the corpus",
          f"{len(unique)} decisions that name the deciding chamber. Chamber numbering is not stable\n"
          "across years, so a number is not a fixed unit over time.")
    save(fig, "chambers")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()
    setup_fonts()
    merged, extraction = load()
    print("writing figures/")
    figure_extraction(extraction)
    figure_coverage(merged)
    figure_years(merged)
    figure_subjects(merged)
    figure_chambers(merged)


if __name__ == "__main__":
    main()
