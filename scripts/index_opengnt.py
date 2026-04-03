#!/usr/bin/env python3
"""Index OpenGNT base text into a JSON verse index.

Reads OpenGNT_version3_3.csv (TAB-separated, UTF-8) and produces a JSON file
keyed by "Book.Chapter.Verse" with token-level data for each verse.

Only extracts Greek + structural fields (no copyrighted English translations).

Usage:
    python index_opengnt.py --input OpenGNT_version3_3.csv --output verse_index.json
"""

import argparse
import json
import os
import sys


def parse_bracketed(field):
    """Parse a 〔field1｜field2｜...〕 delimited value into a list of strings."""
    stripped = field.strip()
    if stripped.startswith("〔") and stripped.endswith("〕"):
        stripped = stripped[1:-1]
    return stripped.split("｜")


def build_index(input_path):
    """Parse OpenGNT base text CSV and return a dict keyed by 'Book.Chapter.Verse'."""
    index = {}

    with open(input_path, "r", encoding="utf-8") as f:
        header_line = f.readline()  # skip header
        if not header_line.startswith("OGNTsort"):
            print(f"Warning: unexpected header: {header_line[:80]}", file=sys.stderr)

        for line_num, line in enumerate(f, start=2):
            line = line.rstrip("\n\r")
            if not line:
                continue
            cols = line.split("\t")
            if len(cols) < 12:
                continue

            # Col 6: 〔Book｜Chapter｜Verse〕
            bcv = parse_bracketed(cols[6])
            if len(bcv) < 3:
                continue
            book, chapter, verse = bcv[0], bcv[1], bcv[2]
            key = f"{book}.{chapter}.{verse}"

            # Col 7: 〔OGNTk｜OGNTu｜OGNTa｜lexeme｜rmac｜sn〕
            greek_parts = parse_bracketed(cols[7])
            ognt_a = greek_parts[2] if len(greek_parts) > 2 else ""
            lexeme = greek_parts[3] if len(greek_parts) > 3 else ""
            rmac = greek_parts[4] if len(greek_parts) > 4 else ""
            sn = greek_parts[5] if len(greek_parts) > 5 else ""

            # Col 9: 〔transSBLcap｜transSBL｜modernGreek｜Fonética〕
            translit_parts = parse_bracketed(cols[9]) if len(cols) > 9 else []
            translit = translit_parts[1] if len(translit_parts) > 1 else ""

            # Col 10: 〔TBESG｜IT｜LT｜ST｜Español〕
            # Only extract TBESG (index 0) — Tyndale House open gloss
            gloss_parts = parse_bracketed(cols[10]) if len(cols) > 10 else []
            tbesg_gloss = gloss_parts[0] if len(gloss_parts) > 0 else ""

            # Col 11: 〔PMpWord｜PMfWord〕
            punct_parts = parse_bracketed(cols[11]) if len(cols) > 11 else []
            pm_pre = punct_parts[0] if len(punct_parts) > 0 else ""
            pm_post = punct_parts[1] if len(punct_parts) > 1 else ""
            # Strip HTML tags from punctuation
            pm_pre = _strip_pm_tags(pm_pre)
            pm_post = _strip_pm_tags(pm_post)

            token = {
                "word": ognt_a,
                "lemma": lexeme,
                "morph": rmac,
                "strong": sn,
                "translit": translit,
                "gloss": tbesg_gloss,
                "pm_pre": pm_pre,
                "pm_post": pm_post,
            }

            if key not in index:
                index[key] = {"book": book, "chapter": chapter, "verse": verse, "tokens": []}
            index[key]["tokens"].append(token)

    return index


def _strip_pm_tags(s):
    """Remove <pm>...</pm> wrapper, keeping inner text."""
    import re
    return re.sub(r"</?pm>", "", s)


def main():
    parser = argparse.ArgumentParser(description="Index OpenGNT base text into JSON")
    parser.add_argument("--input", required=True, help="Path to OpenGNT_version3_3.csv")
    parser.add_argument("--output", required=True, help="Path for output JSON verse index")
    args = parser.parse_args()

    if not os.path.isfile(args.input):
        print(f"Error: input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    print(f"Indexing {args.input} ...")
    index = build_index(args.input)
    print(f"Indexed {len(index)} verses.")

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)

    print(f"Wrote verse index to {args.output}")


if __name__ == "__main__":
    main()
