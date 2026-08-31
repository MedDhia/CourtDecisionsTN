#!/usr/bin/env python3
"""Code each decision into a structured record.

Every field is read out of the decision text itself.  Where the court's own
publication list carries the same fact -- case number and date appear in most
link titles -- the two are compared and any disagreement is written to
``flags`` rather than silently resolved, so a coding error shows up in the data
instead of hiding in it.

Fields left empty are genuinely absent from the document; nothing is inferred.
"""

import argparse
import csv
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

EXTRACTION = os.path.join(ROOT, "data", "extraction.json")
OUT_CSV = os.path.join(ROOT, "data", "decisions.csv")
OUT_JSON = os.path.join(ROOT, "data", "decisions.json")

# ---------------------------------------------------------------- normalising

HAMZA = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا"})
DIACRITICS = re.compile(r"[ً-ْٰٟـ]")


def fold(text):
    """Spelling-insensitive form used for matching, never for output."""
    return DIACRITICS.sub("", text).translate(HAMZA)


def tidy(name):
    """Clean a captured personal name."""
    name = DIACRITICS.sub("", name)
    name = re.sub(r"(?<=[ء-ي])\.(?=[ء-ي])", "", name)  # stray intra-word dot
    name = re.sub(r"[\"'«»\[\]()،.:؛]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    name = re.sub(r"\bال\s+(?=[ا-ي])", "ال", name)  # OCR splits the article
    name = re.sub(r"\s*\d+\s*$", "", name)  # trailing page number
    # Honorifics that regularly get swept up with the name.
    name = re.sub(r"^(?:السيد(?:ة|ين|ات)?|السادة|الاستاذ(?:ة)?|الأستاذ(?:ة)?)\s+",
                  "", name)
    return name.strip(" ،-")


# --------------------------------------------------------------------- dates

MONTHS = {
    # Tunisian usage (from the French) and Modern Standard Arabic side by side.
    "جانفي": 1, "يناير": 1,
    "فيفري": 2, "فبراير": 2,
    "مارس": 3,
    "افريل": 4, "ابريل": 4,
    "ماي": 5, "مايو": 5,
    "جوان": 6, "يونيو": 6, "يونية": 6,
    "جويلية": 7, "يوليو": 7, "يولية": 7,
    "اوت": 8, "اغسطس": 8,
    "سبتمبر": 9, "شتنبر": 9,
    "اكتوبر": 10, "تشرين الاول": 10,
    "نوفمبر": 11, "تشرين الثاني": 11,
    "ديسمبر": 12, "كانون الاول": 12,
}
MONTH_RE = "|".join(sorted(map(re.escape, MONTHS), key=len, reverse=True))


def _iso(day, month, year):
    if not (1 <= month <= 12 and 1 <= day <= 31 and 1950 <= year <= 2100):
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def _numeric_date(a, b, c):
    """Read a three-part numeric date without assuming the field order.

    The corpus mixes DD/MM/YYYY and YYYY/MM/DD, so the four-digit component
    identifies the year and the remaining two are assigned by which one can
    still be a month.
    """
    a, b, c = int(a), int(b), int(c)
    if a > 31:  # YYYY/MM/DD
        year, month, day = a, b, c
    else:  # DD/MM/YYYY
        day, month, year = a, b, c
    if month > 12 and day <= 12:
        day, month = month, day
    return _iso(day, month, year)


# Where the sign-off begins.  The wording varies -- "وصدر هذا القرار",
# "وقد صدر هذا القرار عن الدائرة عدد 29" -- but it always opens this way.
SIGNOFF_RE = re.compile(r"(?:وقد\s+)?و?صدر\s+ه?ذا\s+القرار")

_DAY_MONTH_YEAR = r"(\d{1,2})\s*(" + MONTH_RE + r")\s*(\d{4})"
_NUMERIC = r"(\d{1,4})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{1,4})"


def _dates_in(fragment):
    """Every date in a fragment of folded text, in the order they appear."""
    out = []
    # Tunisian usage writes the first of the month as "غرة أكتوبر 2019".
    for m in re.finditer(r"غرة\s*(" + MONTH_RE + r")\s*(\d{4})", fragment):
        iso = _iso(1, MONTHS[m.group(1)], int(m.group(2)))
        if iso:
            out.append((m.start(), iso))
    for m in re.finditer(_DAY_MONTH_YEAR, fragment):
        iso = _iso(int(m.group(1)), MONTHS[m.group(2)], int(m.group(3)))
        if iso:
            out.append((m.start(), iso))
    for m in re.finditer(_NUMERIC, fragment):
        iso = _numeric_date(*m.groups())
        if iso:
            out.append((m.start(), iso))
    return [iso for _pos, iso in sorted(out)]


def find_dates(text):
    """Decision dates asserted in the document, most authoritative first.

    The sign-off ("وصدر هذا القرار … بتاريخ 6 أكتوبر 2020") is the court's own
    statement of when it ruled, so it outranks the header field, which in a
    handful of files records the date the case was filed instead.
    """
    folded = fold(text)
    found = []

    m = SIGNOFF_RE.search(folded)
    if m:
        for iso in _dates_in(folded[m.start():m.start() + 400]):
            found.append((iso, "sign-off"))

    # Header fields: "تاريخ الحكم 14/02/2019", "تاريخه: 10-03-2016".
    for m in re.finditer(r"تاريخ\s*(?:الحكم|ه)\s*:?\s*" + _NUMERIC, folded):
        iso = _numeric_date(*m.groups())
        if iso:
            found.append((iso, "header"))

    # Header with a spelled-out month:
    # "قرار تعقيبي عدد 2335 بتاريخ 6 أكتوبر 2020".
    for m in re.finditer(
            r"قرار(?:ا)?\s*تعقيبي\s*عدد\s*[\d\s.-]{1,20}?بتاريخ\s*" +
            _DAY_MONTH_YEAR, folded):
        iso = _iso(int(m.group(1)), MONTHS[m.group(2)], int(m.group(3)))
        if iso:
            found.append((iso, "header"))

    return found


def date_from_title(title):
    folded = fold(title or "")
    m = re.search(r"بتاريخ\s*(\d{1,2})\s*[-/.]\s*(\d{1,2})\s*[-/.]\s*(\d{4})", folded)
    if m:
        return _iso(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r"بتاريخ\s*(\d{1,2})\s*(" + MONTH_RE + r")\s*(\d{4})", folded)
    if m:
        return _iso(int(m.group(1)), MONTHS[m.group(2)], int(m.group(3)))
    return None


# ------------------------------------------------------------- case numbers

# Everything before these opens the judgment proper; the case number is above.
BODY_OPENERS = ("بعد الاطلاع", "بعد الاطلاع على", "الحمد لله", "الحمدلله",
                "اصدرت محكمة", "في حق", "وبعد الاطلاع")

# "القضية" picks up stray spaces from kashida justification and from OCR
# ("القض ية"), and the word for "number" around it gets shredded the same way:
# "عـدد" can arrive as "ع د", "عدد ع" or "ع … دد", sometimes with the digits
# sitting in the middle of it.  Matching a short run of ع/د letters absorbs
# every variant in the corpus without having to enumerate them.
CASE_WORD = r"(?:ال)?\s*ق\s*ض\s*ي\s*ة"
ADAD = r"(?:[عد]\s*){1,5}[:.\s]*"
YEAR = r"((?:19|20)\d{2})"


def header_of(text):
    """The block above the body, where the case number and date are printed."""
    folded = fold(text)
    cuts = [folded.find(fold(o), 150) for o in BODY_OPENERS]
    cuts = [c for c in cuts if c > 0]
    return folded[:min(cuts)] if cuts else folded[:900]


def find_case_numbers(text):
    """Case number(s) and, when printed alongside, the year of registration.

    Only the header is searched: the body cites other case numbers constantly
    -- the judgment under appeal, earlier authority -- and every one of them
    matches the same patterns the real one does.
    """
    header = header_of(text)

    patterns = [
        # "عدد القضية: 13844"
        (r"عدد\s*" + CASE_WORD + r"\s*:?\s*(\d{2,6})(?!\d)", "plain"),
        # "القض ية عدد 80653 / 80654" -- files joined for a single decision.
        (CASE_WORD + r"\s*" + ADAD + r"(\d{2,6})\s*[-/]\s*(\d{2,6})(?!\d)", "joined"),
        # "قضية عدد 20918. 2015" -- number then year of registration.
        (CASE_WORD + r"\s*" + ADAD + r"(\d{2,6})\s*[.,]\s*" + YEAR, "with_year"),
        # "عـ68182.2019ـدد القضيـة" -- the same, printed the other way round.
        (r"ع\s*(\d{1,6})\s*[.,]\s*" + YEAR + r"\s*[^\d\n]{0,3}د{1,2}\s*" + CASE_WORD,
         "with_year"),
        # "القضية عدد39843", "القضية عـ42050 ـدد"
        (CASE_WORD + r"\s*" + ADAD + r"(\d{2,6})(?!\d)", "plain"),
        # Cover sheet: "قرار تعقيبي جزائي عدد 54385 بتاريخ …"
        (r"قرار(?:ا)?\s*تعقيبي\s*(?:\S+\s+)?عدد\s*\.?\s*(\d{2,6})(?!\d)", "plain"),
    ]

    for pattern, kind in patterns:
        m = re.search(pattern, header)
        if not m:
            continue
        if kind == "joined":
            return [m.group(1), m.group(2)], None
        if kind == "with_year":
            return [m.group(1)], m.group(2)
        return [m.group(1)], None
    return [], None


def numbers_from_name(stem):
    parts = re.findall(r"\d+", stem)
    if not parts:
        return [], None
    year = None
    if len(parts) > 1 and len(parts[-1]) == 2:
        year = "20" + parts[-1]
        parts = parts[:-1]
    return parts, year


# ------------------------------------------------------------ court, panel

TENS = {"العشرين": 20, "العشرون": 20, "الثلاثين": 30, "الثلاثون": 30,
        "الاربعين": 40, "الاربعون": 40, "عشرة": 10, "عشر": 10}
UNITS = {"الاولى": 1, "الحادية": 1, "الثانية": 2, "الثالثة": 3, "الرابعة": 4,
         "الخامسة": 5, "السادسة": 6, "السابعة": 7, "الثامنة": 8,
         "التاسعة": 9, "العاشرة": 10}


def chamber_number(text, block=None):
    """Number of the deciding chamber, read from the sign-off.

    Spelled out ("الدائرة السادسة والعشرين" -> 26) or in figures ("الدائرة
    الجزائية عدد 28").  Only the sign-off counts: chambers get cited by number
    throughout the reasoning, and those are other courts' chambers.  Callers
    holding the relevant passage already -- the annual reports state the bench
    in a single citation line -- pass it in as ``block``.
    """
    block = fold(block) if block is not None else signoff_block(text)
    if "الدوائر المجتمعة" in block:
        return None  # sat as the full court, not as a numbered chamber

    m = re.search(r"دائرة\s+\S*\s*عدد\s*(\d{1,2})", block)
    if m:
        return int(m.group(1))

    m = re.search(r"الدائرة\s+(?:\S+\s+)?(" + "|".join(map(re.escape, UNITS)) +
                  r")(?:\s+(?:و)?(" + "|".join(map(re.escape, TENS)) + r"))?",
                  block)
    if not m:
        return None
    value = UNITS[m.group(1)]
    if m.group(2):
        value += TENS[m.group(2)]
    return value


def formation(text):
    """Whether the court sat in plenary or as an ordinary chamber.

    Judged from the header and the sign-off only.  Ordinary chambers discuss
    the plenary formation's authority in their reasoning all the time, so
    searching the whole judgment promotes half the corpus to plenary.
    """
    where = fold(text[:1500]) + "\n" + signoff_block(text)
    if "الدوائر المجتمعة" in where or "بدوائرها المجتمعة" in where:
        return "الدوائر المجتمعة"
    if "دائرة" in where or "الدائرة" in where:
        return "دائرة"
    return ""


GOVERNORATES = [
    "تونس", "اريانة", "بن عروس", "منوبة", "نابل", "زغوان", "بنزرت", "باجة",
    "جندوبة", "الكاف", "سليانة", "القيروان", "القصرين", "سيدي بوزيد", "سوسة",
    "المنستير", "المهدية", "صفاقس", "قفصة", "توزر", "قبلي", "قابس", "مدنين",
    "تطاوين", "قرمبالية", "قرقنة",
]


def _place(token):
    """Turn "بالمنستير" / "بتونس" into the bare place name."""
    token = fold(token).strip(" .,:؛\"'")
    for name in sorted(GOVERNORATES, key=len, reverse=True):
        if token.endswith(name) or name in token:
            return name
    return ""


COURT_LABELS = (
    ("محكمة الاستئناف", r"محكمة\s+الاستئناف\s+(ب\S+)"),
    ("المحكمة الابتدائية", r"ال?محكمة\s+الابتدائية\s+(ب\S+)"),
    ("محكمة الناحية", r"محكمة\s+الناحية\s+(ب\S+)"),
    ("المحكمة العقارية", r"المحكمة\s+العقارية\s+(ب\S+)"),
)

# The clause that introduces the judgment under appeal.
APPEAL_CLAUSE = re.compile(r"طعنا\s+في|الحكم\s+المطعون\s+فيه|القرار\s+المطعون"
                           r"|الصادر\s+عن")


def _first_court(fragment):
    for label, pattern in COURT_LABELS:
        for m in re.finditer(pattern, fragment):
            city = _place(m.group(1))
            if city:
                return f"{label} ب{city}", city
    return "", ""


def origin_court(text):
    """The court whose judgment was appealed, and where it sits.

    Looked for first in the clause that names the judgment under appeal, since
    the reasoning of a judgment cites other courts freely.
    """
    folded = fold(text)
    m = APPEAL_CLAUSE.search(folded)
    if m:
        found = _first_court(folded[m.start():m.start() + 600])
        if found[1]:
            return found
    return _first_court(folded)


# The corpus separates names with commas, Arabic commas, dashes and -- where
# OCR has read an Arabic comma as a guillemet -- "»".  A bare "و" also joins
# the last two names of a pair.
NAME_SPLIT = re.compile(r"\s*[،,»؛]\s*|\s*-\s*|\s+و(?=[ا-ي])")


def _names(blob):
    out = []
    for part in NAME_SPLIT.split(blob):
        name = tidy(part)
        # Judges here are named with two to four words; anything longer is a
        # run-on from the surrounding sentence and would only add noise.
        if 2 <= len(name.split()) <= 4 and not re.search(r"\d", name):
            out.append(name)
    return out


# A judge's name is followed by their office, which must not become part of it.
TITLE_TAIL = re.compile(
    r"\s*(?:وكيل|الرئيس|رئيس(?:ة)?|المستشار(?:ة)?|مساعد|النائب|لدى|بمحكمة"
    r"|المدعي|ممثل)\b.*$", re.S)

# Honorifics, in every gender and number the sign-offs use.  OCR turns "السيد"
# into "السبيد" often enough to be worth spelling out.
HONORIFIC = r"(?:الساد(?:ة|ات)|الس[يبا]{1,3}د(?:ات|تين|ين|ة)?)"


def _one_name(blob, multiline=False):
    """Trim a captured span down to the personal name it contains."""
    blob = TITLE_TAIL.sub("", blob)
    blob = re.split(r"[،,»؛]" + ("" if multiline else r"|\n"), blob)[0]
    name = tidy(blob)
    # Tunisian judges are named with up to five words ("عبد الرحمان بن الحاج
    # جلول"); past that the capture has run into the surrounding sentence.
    return " ".join(name.split()[:5]) if name else ""


def signoff_block(text):
    """The closing paragraph that names the bench.

    Everything the panel fields need is stated here, and only here.  Reading the
    whole judgment instead picks up the prosecutor's submissions and the
    chambers cited in the reasoning, which is how "النيابة العمومية الكتابية
    المؤرخة في 2016/04/12" ends up in a column meant for a person's name.
    """
    folded = fold(text)
    starts = [m.start() for m in SIGNOFF_RE.finditer(folded)]
    if not starts:
        starts = [m.start() for m in re.finditer(r"برئاسة", folded)]
    return folded[starts[-1]:] if starts else folded[-2500:]


def panel(text, block=None):
    """The bench, as named in the sign-off.

    Two formats occur.  An ordinary chamber names a president and two
    counsellors inline.  The joined chambers (الدوائر المجتمعة) name the First
    President, then the presidents of every chamber, then several dozen
    counsellors -- so chamber presidents are recorded separately rather than
    folded in with the counsellors.
    """
    block = fold(block) if block is not None else signoff_block(text)
    out = {"president": "", "chamber_presidents": [], "counselors": [],
           "prosecutor": "", "clerk": ""}

    stop = r"(?:وبمحضر|بمحضر|وبحضور|بحضور|وبمساعدة|ومساعدة|بمساعدة|وحرر)"

    for pattern in (
            r"(?:من\s+)?رئيس(?:ت)?ها\s+" + HONORIFIC + r"?\s*(.{3,60}?)"
            r"(?=\s*و?ب?عضوية)",
            r"برئاسة\s+(?:رئيس(?:ت)?ها\s+)?" + HONORIFIC + r"?\s*(.{3,60}?)"
            r"(?=\s*و?ب?عضوية|\s*والمستشار)",
            r"برئاسة\s+" + HONORIFIC + r"?\s*(.{3,60}?)(?=[\n.،])",
            # Badly scanned files lose the word that would end the capture
            # ("وعضوية" arrives as "وعص وية"), so fall back to the line.
            r"(?:من\s+)?رئيس(?:ت)?ها\s+" + HONORIFIC + r"?\s*([^\n]{3,45})",
    ):
        m = re.search(pattern, block, re.S)
        if m:
            out["president"] = _one_name(m.group(1), multiline=True)
            break

    m = re.search(r"عضوية\s*:?\s*رؤساء\s*:?\s*الدوائر\s*:?\s*" + HONORIFIC + r"?\s*:?\s*"
                  r"(.{10,2500}?)(?=\s*(?:و?المستشار(?:ين|ون|ات)|" + stop + r"))",
                  block, re.S)
    if m:
        out["chamber_presidents"] = _names(m.group(1))

    for pattern in (
            # "وعضوية مستشاريها السيدين عبد القادر غزال وحمادي الرحماني"
            r"و?عضوية\s+(?:المستشار(?:ت)?ين|مستشاري?ه?ا)\s+" + HONORIFIC +
            r"?\s*(.{3,300}?)(?=\s*(?:" + stop + r"|\.))",
            # The joined-chamber roll, which runs to several dozen names.
            r"و?المستشار(?:ين|ون|ات)\s+" + HONORIFIC + r"?\s*:?\s*(.{10,4000}?)"
            r"(?=\s*(?:" + stop + r"))",
    ):
        m = re.search(pattern, block, re.S)
        if m:
            out["counselors"] = _names(m.group(1))
            break

    for pattern in (
            r"(?:ممثل\s+الادعاء\s+العام|المدعي\s+العام(?:ي)?|المدعي\s+العمومي)"
            r"\s+" + HONORIFIC + r"?\s*(.{3,45}?)(?=\s*(?:" + stop + r"|[.،»\n]))",
            r"بمح[ضص]ر\s+" + HONORIFIC + r"?\s*(.{3,45}?)\s+مساعد\s+وكيل\s+الدولة",
            r"وكيل\s+الدولة\s+العام\s+" + HONORIFIC + r"\s*(.{3,45}?)"
            r"(?=\s*(?:" + stop + r"|[.،»\n]))",
    ):
        m = re.search(pattern, block)
        if m:
            out["prosecutor"] = _one_name(m.group(1), multiline=True)
            break

    for pattern in (
            r"كاتب(?:ة)?\s+ا?\s*لجلسة\s+" + HONORIFIC + r"?\s*(.{3,45}?)"
            r"(?=\s*(?:وحرر|$)|[.،»]\s)",
            # Some sign-offs name the clerk before the office:
            # "وبمساعدة السيدة نسرين الطرشاني كاتبة الجلسة."
            r"و?بمساعدة\s+" + HONORIFIC + r"\s*(.{3,45}?)\s+كاتب(?:ة)?\s+ا?\s*لجلسة",
    ):
        m = re.search(pattern, block, re.S)
        if m:
            out["clerk"] = _one_name(m.group(1), multiline=True)
            break
    return out


# --------------------------------------------------------- matter & outcome

MATTER_RULES = [
    ("جزائي", ["م ا ج", "الحق العام", "المظنون فيه", "جريمة", "جزائي",
               "النيابة العمومية", "المتهم", "عقوبة"]),
    ("عقاري", ["السجل العقاري", "الرسم العقاري", "المحكمة العقارية",
               "الترسيم", "التسجيل العقاري"]),
    ("تجاري", ["تجاري", "الشركة", "الكراء التجاري", "الافلاس", "التسوية القضائية"]),
    ("شغل", ["الشغل", "الطرد التعسفي", "مجلة الشغل", "الاجير"]),
    ("احوال شخصية", ["النفقة", "الطلاق", "الحضانة", "مجلة الاحوال الشخصية",
                     "الزوجية"]),
    ("مدني", ["م م م ت", "مدني", "الالتزامات والعقود", "م ا ع"]),
]


def subject_matter(text):
    folded = fold(text)
    scores = {label: sum(folded.count(fold(k)) for k in keys)
              for label, keys in MATTER_RULES}
    best = max(scores, key=scores.get)
    return best if scores[best] else ""


def outcome(text):
    """What the court actually ordered, read from the operative part."""
    folded = fold(text)
    cut = max(folded.rfind("لهذه الاسباب"), folded.rfind("ولهذه الاسباب"))
    tail = folded[cut:] if cut != -1 else folded[-1500:]

    labels = []
    if re.search(r"نقض|بنقض|ونقض", tail):
        labels.append("نقض")
    if re.search(r"احالة|الاحالة", tail):
        labels.append("إحالة")
    if re.search(r"رفض", tail):
        labels.append("رفض")
    if re.search(r"عدم\s+قبول|بعدم\s+القبول", tail):
        labels.append("عدم قبول")
    if re.search(r"قبول", tail) and "قبول" not in "".join(labels):
        labels.append("قبول")
    return "؛".join(dict.fromkeys(labels))


# ------------------------------------------------------------------- driver

def code(record):
    path = os.path.join(ROOT, record["txt"])
    text = open(path, encoding="utf-8").read()
    title = record.get("title", "")

    numbers, year = find_case_numbers(text)
    name_numbers, name_year = numbers_from_name(record["stem"])
    flags = []
    if not numbers:
        numbers, flags = name_numbers, flags + ["case_number_from_filename"]
    elif name_numbers and set(numbers) != set(name_numbers):
        flags.append(f"case_number_mismatch:file={'/'.join(name_numbers)}")
    year = year or name_year

    dates = find_dates(text)
    title_date = date_from_title(title)
    date = dates[0][0] if dates else title_date
    if dates and title_date and title_date != dates[0][0]:
        flags.append(f"date_mismatch:title={title_date}")
    if not dates and title_date:
        flags.append("date_from_title")

    court_name, city = origin_court(text)
    people = panel(text)

    # A plenary sign-off lists the chamber presidents and then the counsellors,
    # but a few files lose the second heading and run the two together.  The
    # names are all there; only the split between them is missing.
    if people["chamber_presidents"] and not people["counselors"]:
        flags.append("bench_not_separated")

    row = {
        "decision_id": record["stem"],
        "case_number": "/".join(numbers),
        "case_year": year or "",
        "decision_date": date or "",
        "decision_year": date[:4] if date else "",
        "decision_month": date[5:7] if date else "",
        "court": "محكمة التعقيب",
        "court_seat": "تونس",
        "formation": formation(text),
        "chamber_number": chamber_number(text) or "",
        "president": people["president"],
        "chamber_presidents": "؛".join(people["chamber_presidents"]),
        "counselors": "؛".join(people["counselors"]),
        "n_counselors": len(people["counselors"]),
        "bench_size": (bool(people["president"]) + len(people["chamber_presidents"])
                       + len(people["counselors"])),
        "prosecutor": people["prosecutor"],
        "clerk": people["clerk"],
        "origin_court": court_name,
        "origin_city": city,
        "subject_matter": subject_matter(text),
        "outcome": outcome(text),
        "title": title,
        "n_pages": record["pages"],
        "n_chars": record["chars"],
        "extraction_method": record["method"],
        "ocr_agreement": record.get("agreement") or "",
        "source_url": record["url"],
        "sha256": record.get("sha256") or "",
        "pdf_path": record["pdf"],
        "txt_path": record["txt"],
        "flags": "؛".join(flags),
    }
    return row


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--show", action="store_true", help="print each coded row")
    args = ap.parse_args()

    records = [r for r in json.load(open(EXTRACTION, encoding="utf-8"))
               if r["kind"] == "decisions"]
    rows = [code(r) for r in records]
    rows.sort(key=lambda r: (r["decision_date"] or "9999", r["decision_id"]))

    with open(OUT_CSV, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=1)

    filled = {k: sum(1 for r in rows if str(r[k]).strip()) for k in rows[0]}
    print(f"coded {len(rows)} decisions -> data/decisions.csv\n")
    print(f"{'field':<20} {'filled':>6}")
    for key, count in filled.items():
        print(f"{key:<20} {count:>6}/{len(rows)}")
    flagged = [r for r in rows if r["flags"]]
    if flagged:
        print(f"\n{len(flagged)} rows carry flags:")
        for r in flagged:
            print(f"  {r['decision_id']:<16} {r['flags']}")
    if args.show:
        for r in rows:
            print(json.dumps(r, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
