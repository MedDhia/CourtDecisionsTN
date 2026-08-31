# Court decisions of the Tunisian Court of Cassation

An archive of the judgments (قرارات تعقيبية) that the Tunisian Court of
Cassation — محكمة التعقيب — publishes as PDFs on <http://www.cassation.tn>,
with a clean plain-text rendering of each one and a coded dataset describing
them.

Everything here is built by the scripts in `scripts/` and can be rebuilt from
the court's site with three commands. Nothing was transcribed or coded by hand.

```
decisions/pdf/     the 27 judgments published whole, exactly as downloaded
decisions/txt/     one UTF-8 text file per judgment
digests/txt/       the 522 decisions reported in the annual reports, one file each
publications/      the reports themselves, and the court's other PDFs
data/decisions.csv the judgments, coded — one row each
data/digests.csv   the digested decisions, coded — one row each
data/codebook.md   what every variable in both tables means
data/sources.json  every PDF link found on the site, with its checksum
data/extraction.json  how each document's text was obtained, and its quality score
scripts/           the pipeline
```

## What is in the corpus

**549 decisions in two forms.** The court publishes 43 PDFs. 27 are individual
judgments, published whole. Three others are its annual reports, and those
report a further **522 decisions** in digest form — a headnote, a citation, and
the passage of the reasoning the court wanted on the record. The two are coded
into separate tables, because an extract is not the same evidence as a
judgment; see [Splitting the annual reports](#splitting-the-annual-reports).

### The 27 judgments published whole

The judgments run from **March 2016 to October 2020**. 14 were decided by the
joined chambers (الدوائر المجتمعة), the court's plenary formation sitting 40 to
62 judges, and 13 by ordinary chambers of three. 17 are criminal, 8 civil, and
one each land and personal status. The appeals come from eight governorates,
led by Tunis (11) and Monastir (6). The parties are anonymised by the court
itself (`"م.ب"`, `"ص.ع"`); the judges are named in full, and this dataset codes
them.

This is the court's *selection* of its own decisions, not a docket: it publishes
the judgments it considers significant. Treat the corpus as a curated sample,
not a population.

### Splitting the annual reports

The reports for 2017, 2019 and 2020 run to 1,556 pages between them and report
522 decisions, from **October 2009 to November 2020**.

Searching their text for decision boundaries finds nothing, which is misleading:
the boundaries are typographic, not lexical. Each decision is introduced by a
citation line — always bold, always opening with `قرار`, always carrying a case
number and a date — under a bold headnote, above the extract set in the body
face. That line is the seam, and `scripts/split_reports.py` cuts on it.

For decisions of an ordinary chamber the citation also names the chamber, the
presiding judge, the counsellors, the prosecutor and the clerk, so those rows
code as fully as the standalone judgments do (president on 442 of 451). For the
56 plenary decisions the reports name no bench at all, and those fields stay
empty.

Seven of the 27 standalone judgments are also digested in a report, which gives
the two pipelines an independent check against each other: **case number, date,
formation and chamber agree on all seven**. `full_text_id` links them.

Two things are deliberately weaker in `digests.csv`, and the codebook says so:
`outcome` is left empty on 519 of 522 rows because the extracts quote the
reasoning and stop before the order — filling it from the reasoning would have
produced plausible, wrong values — and 30 rows are marked `repeat_of` where a
report discusses the same decision twice under different headings.

### Missing files

Five decisions are linked from the court's own jurisprudence page but return
404 from its server: `001.pdf`, `003.pdf`, `004.pdf`, `005.pdf`, `006.pdf` —
a set of summary-procedure (استعجالي) rulings. They are not in the Internet
Archive either. Their titles are preserved in `data/sources.json`, with the
download error, in case the court restores them.

## The text extraction problem

This is the part of the work that took the effort, and it is worth explaining,
because the naive approach produces a corpus that looks fine and is wrong.

The court's PDFs are produced by a Word pipeline that lays Arabic glyphs out in
**visual** order. Three separate defects follow from that:

**1. Reversed ligature expansions.** A glyph whose ToUnicode entry expands to
several characters — the lam-alef ligatures, the *lillah* ligature — has that
expansion emitted in logical order and then reversed along with the rest of the
run. `الحمد لله` arrives as `الحمد هلل`, `القرار الآتي` as `القرار اآلتي`,
`محكمة الاستئناف` as `محكمة االستئناف`. These are easy to miss because the text
still *looks* like Arabic.

Such an expansion is identifiable in the raw character stream: only its last
character carries the glyph's real bounding box, the rest are zero-width markers
pinned to its edge. `scripts/pdf_text.py` re-reverses each of those groups.

**2. Runs handed over in the wrong order.** Each directional run of a line comes
back internally correct, but the runs themselves arrive left to right, so a
right-to-left line is inside out. The annual reports' citation line

```
قرار تعقيبي عدد 66968.2018 بتاريخ 12 نوفمبر 2019 صادر عن الدائرة
```

arrives beginning at `صادر عن الدائرة`, with the case number and date shuffled
in between — which is exactly why searching the reports for decision boundaries
came up empty at first. PyMuPDF also splits one printed line into several line
objects, which have to be rejoined the same way. Both are fixed by ordering
right-to-left on an Arabic line, and the spacing between runs is then re-derived
from the gaps on the page: a space written at the right edge of a run ends up on
its wrong side once the run order is reversed.

**3. Corrupt ToUnicode maps.** Some files simply lie about what their glyphs
mean, and no amount of re-ordering fixes that:

- `20918-18.pdf` renders its case number as `20918` and reports it as `81902`.
  Its digit glyphs are mapped to the wrong characters outright — glyph 21 draws
  a `2` and declares itself an `8`.
- `87861.pdf` reports the presiding judge `شلغوم` as `ولغوم`, `الدائرة` as
  `الداةر`, `المتألفة` as `المتألاة`.
- Others map the justification kashida to an alef, sprinkling the text with
  spurious letters.

There is no way to repair these from inside the PDF. The only reliable reading
is what the page actually draws.

### How the pipeline handles it

Every document is read twice — once from its text layer, once by rendering the
pages and running Tesseract's Arabic model over them — and the two readings are
compared, on words and on numbers separately. The text layer is kept only where
it agrees with what the page renders; otherwise the OCR is used.

The word-agreement score turns out to be sharply bimodal over this corpus.
Sorted, the 27 judgments run 0.07, 0.09, 0.44 … 0.62, 0.78, then jump to 0.91,
0.91 … 0.98. The threshold sits in that gap, and every file below it turns out
on inspection to have a damaged font.

Numbers are scored separately and held to a stricter standard, because a file
can decode every letter correctly and still get every digit wrong. Four
judgments do exactly that — `20918-18`, `28620-18`, `47234-18` and `398-18` score
0.88–0.91 on words and **0.05–0.14 on numbers**. Without the second test they
would have passed, and every case number and date taken from them would have
been wrong.

**16 of the 27 judgments fail one test or the other and are read by OCR.** Both
scores are recorded per document in `data/extraction.json`, and the word score
in the `ocr_agreement` column, so any row can be judged on its own evidence.

Two smaller wrinkles, both discovered the hard way:

- Tesseract silently drops whole lines, and *which* pages it drops them on
  depends on both the segmentation mode and the rendering resolution. `--psm 6`
  loses the entire bench of the deciding chamber in `88085.pdf`; `--psm 3`
  loses it in `87942.pdf`; `90873.pdf` only keeps it at 300 dpi. Each page of a
  judgment is therefore read four times — two modes at two resolutions — and
  the richest reading kept. "Richest" is measured in *distinct* words: on the
  last page of `90873.pdf` the reading that loses the whole bench still has
  more word tokens than the one that keeps it, and 10% fewer distinct words.
- The court also publishes French documents. Running the Arabic model over
  those returns noise, so Latin-script text layers are checked for
  plausibility instead — real prose is almost all vowel-bearing words, scanner
  noise is not.

## Rebuilding from source

```bash
pip install pymupdf
apt-get install tesseract-ocr tesseract-ocr-ara

python3 scripts/fetch.py           # crawl cassation.tn, download every PDF
python3 scripts/extract.py         # produce the .txt files, decide text-layer vs OCR
python3 scripts/code_decisions.py  # build data/decisions.csv
python3 scripts/split_reports.py   # split the annual reports, build data/digests.csv
```

`fetch.py` walks the site rather than guessing URLs: there is no sitemap, the
directory listing is forbidden, and the links to the judgments appear only on
the jurisprudence page. It honours the `<base href>` that TYPO3 puts on every
page — without that, relative links resolve against the page path instead and
the same 37 files come back 581 times under directories that do not exist.

`extract.py` caches its OCR under `.ocr-cache/` (gitignored), so the extraction
and coding rules can be changed without re-reading every page.

## Reading the data

`data/decisions.csv` has one row per judgment published whole and
`data/digests.csv` one row per decision reported in an annual report. Both are
documented field by field in [`data/codebook.md`](data/codebook.md) and share
their variable names and conventions. The variables the request asked for:

- **date** — `decision_date`, ISO `YYYY-MM-DD`, taken from the court's own
  sign-off in preference to the header. Three different date formats and two
  different sets of month names (Tunisian `جانفي/فيفري/جوان`, Modern Standard
  `يناير/فبراير/يونيو`) occur across the corpus.
- **location** — `origin_city` and `origin_court`. Note that the Court of
  Cassation is a single national court sitting in Tunis, so `court_seat` is
  constant; the geographic variation in this dataset is in *where the appeal
  came from* (Sousse, Monastir, Sfax, Le Kef, Medenine, Nabeul, Bizerte, …).
- **judges** — `president`, `counselors`, and for plenary decisions
  `chamber_presidents`, plus `prosecutor` and `clerk`.
- and `case_number`, `case_year`, `formation`, `chamber_number`,
  `subject_matter`, `outcome`.

Empty means the document does not state it. Nothing is imputed, and where the
document and the court's own publication title disagree, both are kept and the
disagreement is recorded in `flags` rather than resolved silently.

### Known limits

- `subject_matter` is *derived* from legal vocabulary in the text, not stated
  by the court. It is an indicative classification.
- Four fields are incomplete, and the gaps are visible in the data rather than
  papered over: `case_year` only where the header prints it (7 rows),
  `chamber_number` only for ordinary chambers (13 rows — a plenary bench has no
  chamber number), and the bench of `68182`, whose scan is poor enough that OCR
  recovers the presiding judge but not the two counsellors.
- Names read out of OCR carry OCR's spelling. The same judge may appear as
  `المنجي شلغوم` in one row and `منجي شلغوم` in another. There is no
  authority list to normalise against, so no normalisation is attempted; if
  you need judge-level identifiers, plan to reconcile the strings yourself.
- The digests are extracts the court chose to print, from the decisions it
  chose to report. Both tables are curated samples of the court's own output,
  not dockets, and neither supports counting what the court does.

## Provenance and licence

The PDFs are public documents published by the Tunisian Court of Cassation and
are reproduced here unmodified; `data/sources.json` records the URL, byte size
and SHA-256 of each as downloaded, so any copy can be checked against the
original. The scripts and the coded dataset in this repository are offered for
research use.
