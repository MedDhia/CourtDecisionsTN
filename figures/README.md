# Figures

Built by `python3 scripts/make_figures.py` from `data/all_decisions.json` and
`data/extraction.json`. Each is written as **PDF** (vector, for a LaTeX paper)
and **PNG** (for reading on screen). Re-run the script after any change to the
data and they regenerate.

| Figure | What it shows |
|---|---|
| `extraction-quality` | Why 16 of the 27 judgments are read by OCR rather than from their own text layer. Each judgment is a point: agreement with OCR on words against agreement on numbers, with both thresholds drawn. The four named files are the reason numbers are scored separately — they decode every letter correctly and every digit wrong. |
| `corpus-coverage` | What share of each variable the two sources actually state. The honest map of what the dataset can answer: the reports name no bench for a plenary sitting, and their extracts stop before the disposition. |
| `decisions-by-year` | The 536 distinct decisions by year of decision, split by formation. Reads as a warning, not a trend: coverage tracks which annual reports exist. |
| `subject-matter` | Areas of law, split by formation. `subject_matter` is inferred from legal vocabulary, not stated by the court. |
| `chambers` | Which of the court's chambers appear, among the 395 decisions that name one. |

## Conventions

Drawn to the reference palette and rules of the `dataviz` skill:

- **Two categorical hues** — blue for an ordinary chamber, orange for the joined
  chambers — plus a neutral grey for *not stated*, which is an absence rather
  than a series. That set clears the all-pairs colourblind gates with room to
  spare; it was validated with the skill's script, not by eye.
- **Colour never carries identity alone.** Every chart with more than one series
  has a legend, and every bar is directly labelled with its value.
- **Sequential means one hue.** The coverage heatmap is a single blue ramp,
  light to dark. Nominal categories (chamber numbers) get one colour for every
  bar — never a ramp by size, which would double-encode length as hue.
- **Text never wears a series colour**; labels stay in ink tones beside the
  coloured mark.
- Marks are thin and capped, gridlines are hairline and recessive, and stacked
  segments are separated by a gap in the surface colour rather than by a stroke.

**Light mode only.** These are print figures; a dark surface has no meaning on
paper. The table view every chart is supposed to have is the CSV it was built
from — `data/all_decisions.csv`, documented in `data/codebook.md`.

## Arabic in the labels

Category labels give the English term with the court's own Arabic beside it.
Matplotlib shapes and orders Arabic itself, so the strings are passed through
raw — pre-shaping them with `arabic_reshaper` and `python-bidi` applies the
transform a second time and every word comes out mirrored, which is how the
first version of these figures was wrong.

The typefaces are **Noto Sans** with **Noto Sans Arabic** behind it, one
superfamily so the two scripts sit together rather than looking pasted side by
side, and DejaVu Sans last to close the chain for the few maths symbols
(`≥`) neither Noto face carries. On Debian/Ubuntu:
`apt-get install fonts-noto-core`.
