# Codebook — `data/decisions.csv`

One row per decision of the Tunisian Court of Cassation (محكمة التعقيب)
published as a standalone PDF on <http://www.cassation.tn>.

All Arabic values are reproduced as they appear in the judgment, in UTF-8.
Empty means *the document does not state it* — no value is ever imputed. Where
a field could be read two ways, the disagreement is recorded in `flags` instead
of being silently resolved.

## Identification

| Variable | Type | Description |
|---|---|---|
| `decision_id` | string | Stable key. The PDF's file name on the court's server (e.g. `87861`, `80654-80653`). Also the name of the `.pdf` and `.txt` files. |
| `case_number` | string | Case number (عدد القضية) as printed in the judgment. Decisions issued on joined files carry both numbers separated by `/`. |
| `case_year` | integer | Year the case was registered, where the header prints it next to the number (e.g. `عـ68182.2019ـدد القضية` → 2019). Distinct from the year of decision. |

## Date

| Variable | Type | Description |
|---|---|---|
| `decision_date` | ISO date `YYYY-MM-DD` | Date the decision issued. Taken from the court's own sign-off (`وصدر هذا القرار بتاريخ …`) in preference to the header, since the sign-off is the operative statement. |
| `decision_year` | integer | Year component, for convenience. |
| `decision_month` | integer | Month component, for convenience. |

Dates are printed in three different ways across the corpus — `DD/MM/YYYY`,
`YYYY/MM/DD`, and spelled-out months in both Tunisian usage (`جانفي`, `فيفري`,
`جوان`, `جويلية`, `أوت`) and Modern Standard Arabic (`يناير`, `فبراير`,
`يونيو`). All three are parsed; the four-digit component identifies the year, so
field order is never assumed.

## Court and location

| Variable | Type | Description |
|---|---|---|
| `court` | string | Always `محكمة التعقيب` (Court of Cassation). Constant by construction — this corpus contains only its decisions. |
| `court_seat` | string | Always `تونس` (Tunis). The Court of Cassation is a single national court sitting in the capital. |
| `formation` | string | Bench that decided: `الدوائر المجتمعة` (joined chambers, the court's plenary formation, reserved for conflicts of authority and points of principle) or `دائرة` (an ordinary chamber). |
| `chamber_number` | integer | Number of the deciding chamber, where an ordinary chamber is named (`الدائرة السادسة والعشرين` → 26). Empty for joined-chamber decisions, which sit as the whole court. |
| `origin_court` | string | The lower court whose judgment was appealed (`محكمة الاستئناف بسوسة`, `المحكمة الابتدائية بالمنستير`, …). |
| `origin_city` | string | Seat of that lower court, normalised to the governorate name (`سوسة`, `المنستير`, `صفاقس`, `تونس`, …). **This is the meaningful geographic variable in the dataset**: the Court of Cassation itself never moves, so spatial variation comes from where the case originated. |

## Bench

Names are as printed. The court anonymises the *parties* (they appear as
`"م.ب"`, `"ص.ع"`), but names its judges in full.

| Variable | Type | Description |
|---|---|---|
| `president` | string | Presiding judge (`رئيسها` / `برئاسة`). For a plenary sitting this is the First President of the court. |
| `chamber_presidents` | string | For plenary decisions, the presidents of the individual chambers sitting on the bench (`رؤساء الدوائر`), separated by `؛`. Empty for ordinary chambers, which have only one president. |
| `counselors` | string | Associate judges (`المستشارون`), separated by `؛`. An ordinary chamber sits with two; the plenary bench has several dozen. |
| `n_counselors` | integer | Count of the above. |
| `bench_size` | integer | Total judges named: president + `chamber_presidents` + `counselors`. Comparable across rows even where the document does not separate the two lists — an ordinary chamber sits 3, the plenary bench 40–62 in this corpus. |
| `prosecutor` | string | Representative of the public prosecutor's office present at the hearing (`المدعي العام`, or `مساعد وكيل الدولة العام` before the plenary bench). |
| `clerk` | string | Clerk of the hearing (`كاتب/كاتبة الجلسة`). |

## Substance

| Variable | Type | Description |
|---|---|---|
| `subject_matter` | string | Area of law, assigned by the balance of legal-vocabulary markers in the text: `جزائي` (criminal), `مدني` (civil), `تجاري` (commercial), `عقاري` (land/registration), `شغل` (labour), `احوال شخصية` (personal status). Derived, not stated by the court — treat as an indicative classification, not an official docket category. |
| `outcome` | string | Disposition read from the operative part after `لهذه الأسباب`, as one or more of `نقض` (quashed), `إحالة` (remanded), `رفض` (appeal rejected), `قبول` (admitted), `عدم قبول` (inadmissible), separated by `؛`. Multiple labels are normal: a successful appeal is typically `قبول؛نقض؛إحالة`. |
| `title` | string | Descriptive headline given by the court on its publications page — usually the case number, date and the point of law decided. Court-supplied, not derived. |

## Provenance

| Variable | Type | Description |
|---|---|---|
| `n_pages` | integer | Pages in the source PDF. |
| `n_chars` | integer | Characters in the extracted text. |
| `extraction_method` | string | `text-layer` if the PDF's embedded text was used, `ocr` if it was rejected in favour of Tesseract. See the README for why roughly half this corpus needs OCR. |
| `ocr_agreement` | float | Token overlap between the two independent readings of the document, 0–1. A quality score for the row: the retained text-layer files sit at 0.89–0.94. |
| `source_url` | URL | Where the PDF was downloaded from. |
| `sha256` | hex | Checksum of the PDF as downloaded, so the archived copy can be verified against the original. |
| `pdf_path`, `txt_path` | path | Location of the PDF and its text within this repository. |
| `flags` | string | Coding warnings, separated by `؛`. Empty is the normal case. |

### Values `flags` can take

| Flag | Meaning |
|---|---|
| `case_number_from_filename` | No case number could be read from the text; the number in the court's file name was used instead. |
| `case_number_mismatch:file=…` | The number in the text and the number in the file name differ. Both are reported so the discrepancy can be inspected; the text is what `case_number` reports. |
| `date_from_title` | No date in the document body; the date in the court's own publication title was used. |
| `date_mismatch:title=…` | The document and the court's publication title give different dates. `decision_date` reports the document. |
| `bench_not_separated` | A plenary sign-off that runs the chamber presidents and the counsellors together under one heading, so every judge below the president is in `chamber_presidents` and `counselors` is empty. All the names are present; only the split between the two roles is missing. Use `bench_size` for comparisons. |

---

# Codebook — `data/digests.csv`

One row per decision reported in the court's annual reports (`publications/pdf/2019.pdf`,
`2020.pdf`, `rapport-annuel-2017.pdf`), 522 in total.

**These are extracts, not full judgments.** For each decision the report prints
a headnote, a citation line, and the passage of the reasoning the court wanted
on the record — typically one to four pages of a judgment that ran longer. They
are kept apart from `decisions.csv` for that reason. Do not pool the two
without deciding whether an extract is evidence of the same kind as a judgment.

Fields shared with `decisions.csv` — `case_number`, `case_year`,
`decision_date`, `decision_year`, `decision_month`, `court`, `court_seat`,
`formation`, `chamber_number`, `president`, `counselors`, `n_counselors`,
`prosecutor`, `clerk`, `origin_court`, `origin_city`, `subject_matter`,
`outcome` — carry the same meanings and the same conventions, including that
empty means the document does not say.

| Variable | Type | Description |
|---|---|---|
| `digest_id` | string | Stable key, `<report>-<sequence>` in the order the report prints them (e.g. `2019-035`). |
| `headnote` | string | The court's own summary of the point decided, printed above the citation. Court-supplied, not derived. |
| `citation` | string | The citation line verbatim. Everything the report states about the case number, date and bench is in here, so it is kept for checking the coded fields against. |
| `source_report` | `2017` \| `2019` \| `2020` | Which annual report the digest is from. |
| `first_page`, `last_page` | integer | Page range within that report's PDF (1-based), so any row can be checked against the original. |
| `full_text_id` | string | `decision_id` of the same judgment in `decisions.csv`, where the court also publishes it whole. 7 rows. |
| `n_chars`, `txt_path` | | Size and location of the extracted text. |
| `flags` | string | `repeat_of:<digest_id>` where the report discusses the same decision a second time under a different heading, with a different extract. 30 rows. Both are kept; count one. |

## What is weaker here than in `decisions.csv`

- **`outcome` is almost always empty (3 of 522).** The digests quote the
  reasoning, not the order. Only five reach `لهذه الأسباب`, and without the
  operative part a word like `رفض` in the text is usually the court describing
  an argument or the judgment below, not its own disposition. Coding it from
  the reasoning would have filled the column with plausible, wrong values.
- **The bench is only stated for chamber decisions.** The reports name the
  chamber, president, counsellors, prosecutor and clerk for decisions of an
  ordinary chamber (president on 442 of 451 such rows), and name none of them
  for the 56 plenary decisions. That is the source's practice, not a coding
  failure.
- **`origin_court` / `origin_city` are mostly empty (46 of 522).** The extracts
  rarely restate which court was appealed from.
- **`case_year` is only present where the citation prints it** (95 rows), in
  the forms `عدد 80441.2019` or `عـ2016 / 370 ـدد`.
