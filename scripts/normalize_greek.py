#!/usr/bin/env python3
"""Normalize Greek text for consistent processing.

Operations:
  - NFC/NFKC Unicode normalization
  - Standardize punctuation (middle dot, question marks)
  - Optionally strip accents (breathing marks, diacritics)

Usage:
    python normalize_greek.py --input raw.txt --output normalized.txt [--strip-accents]
    echo "Ἐν ἀρχῇ ἦν ὁ λόγος" | python normalize_greek.py
"""

import argparse
import re
import sys
import unicodedata


def normalize_nfc(text):
    """Apply NFC normalization to ensure consistent codepoints."""
    return unicodedata.normalize("NFC", text)


def normalize_nfkc(text):
    """Apply NFKC normalization (compatibility decomposition + canonical composition)."""
    return unicodedata.normalize("NFKC", text)


def standardize_punctuation(text):
    """Standardize common Greek punctuation variants."""
    # Greek question mark (;) is distinct from Latin semicolon
    # Middle dot (·) is the Greek semicolon/colon
    # Leave them as-is but normalize lookalikes
    text = text.replace("\u037e", ";")  # Greek question mark → semicolon
    text = text.replace("\u0387", "\u00b7")  # Greek ano teleia → middle dot
    return text


def strip_accents(text):
    """Remove all combining diacritical marks (accents, breathing marks)."""
    # Decompose to NFD so accents become separate combining characters
    decomposed = unicodedata.normalize("NFD", text)
    # Remove all combining marks (category M)
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch)[0] != "M")
    # Recompose
    return unicodedata.normalize("NFC", stripped)


def normalize_greek(text, do_strip_accents=False):
    """Full normalization pipeline."""
    text = normalize_nfc(text)
    text = standardize_punctuation(text)
    if do_strip_accents:
        text = strip_accents(text)
    return text


def main():
    parser = argparse.ArgumentParser(description="Normalize Greek text")
    parser.add_argument("--input", help="Input file (default: stdin)")
    parser.add_argument("--output", help="Output file (default: stdout)")
    parser.add_argument("--strip-accents", action="store_true",
                        help="Remove accents and breathing marks")
    args = parser.parse_args()

    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    result = normalize_greek(text, do_strip_accents=args.strip_accents)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(result)
    else:
        sys.stdout.write(result)


if __name__ == "__main__":
    main()
