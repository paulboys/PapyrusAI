#!/usr/bin/env python3
"""BLEU score computation for translation evaluation.

Implements multi-reference BLEU (Papineni et al., 2002) using only stdlib.
Supports sentence-level and corpus-level scoring.

Usage as module:
    from bleu import sentence_bleu, corpus_bleu
    score = sentence_bleu(candidate, [reference1, reference2])
"""

import math
import re
from collections import Counter


def tokenize(text):
    """Tokenize text into lowercase words for BLEU comparison.

    Strips Markdown formatting, verse numbers, punctuation, and normalizes
    whitespace before splitting into words.
    """
    # Remove HTML comments
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    # Remove Markdown bold/italic markers and verse numbers like **12** or **1:12**
    text = re.sub(r"\*{1,3}", "", text)
    # Remove Markdown headers
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Remove Markdown links [text](url)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    # Remove Markdown list markers
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    # Remove verse-number patterns like "12 " at start of line or "1:12"
    text = re.sub(r"^\d+[:.]?\d*\s+", "", text, flags=re.MULTILINE)
    # Strip remaining punctuation (keep apostrophes for contractions)
    text = re.sub(r"[^\w\s']", " ", text)
    # Collapse whitespace and lowercase
    return text.lower().split()


def ngrams(tokens, n):
    return [tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)]


def modified_precision(candidate_tokens, reference_token_lists, n):
    candidate_ngrams = ngrams(candidate_tokens, n)
    if not candidate_ngrams:
        return 0, 0
    candidate_counts = Counter(candidate_ngrams)
    max_ref_counts = Counter()
    for ref_tokens in reference_token_lists:
        ref_counts = Counter(ngrams(ref_tokens, n))
        for ng, count in ref_counts.items():
            max_ref_counts[ng] = max(max_ref_counts[ng], count)
    clipped = 0
    for ng, count in candidate_counts.items():
        clipped += min(count, max_ref_counts.get(ng, 0))
    total = sum(candidate_counts.values())
    return clipped, total


def brevity_penalty(candidate_len, reference_lengths):
    if candidate_len == 0:
        return 0
    r = min(reference_lengths, key=lambda ref_len: (abs(ref_len - candidate_len), ref_len))
    if candidate_len >= r:
        return 1.0
    return math.exp(1 - r / candidate_len)


def sentence_bleu(candidate, references, max_n=4, weights=None):
    """Compute sentence-level BLEU score.

    Args:
        candidate: String - the translation to evaluate.
        references: List of strings - one or more reference translations.
        max_n: Maximum n-gram order (default: 4 for BLEU-4).
        weights: Tuple of n-gram weights (default: uniform).

    Returns:
        Dict with 'bleu', 'precisions', 'bp', 'length_ratio', 'candidate_len'.
    """
    if weights is None:
        weights = tuple(1.0 / max_n for _ in range(max_n))
    cand_tokens = tokenize(candidate)
    ref_token_lists = [tokenize(ref) for ref in references]
    if not cand_tokens:
        return {"bleu": 0.0, "precisions": [0.0] * max_n, "bp": 0.0,
                "length_ratio": 0.0, "candidate_len": 0}
    precisions = []
    log_avg = 0.0
    all_positive = True
    for n in range(1, max_n + 1):
        clipped, total = modified_precision(cand_tokens, ref_token_lists, n)
        p = clipped / total if total else 0.0
        precisions.append(p)
        if p == 0:
            all_positive = False
        else:
            log_avg += weights[n - 1] * math.log(p)
    ref_lengths = [len(rt) for rt in ref_token_lists]
    bp = brevity_penalty(len(cand_tokens), ref_lengths)
    bleu = bp * math.exp(log_avg) if all_positive else 0.0
    closest_ref_len = min(ref_lengths, key=lambda rl: (abs(rl - len(cand_tokens)), rl))
    ratio = len(cand_tokens) / closest_ref_len if closest_ref_len > 0 else 0
    return {"bleu": bleu, "precisions": precisions, "bp": bp,
            "length_ratio": ratio, "candidate_len": len(cand_tokens)}


def corpus_bleu(candidates, references_list, max_n=4, weights=None):
    """Compute corpus-level BLEU over multiple segments."""
    if weights is None:
        weights = tuple(1.0 / max_n for _ in range(max_n))
    total_clipped = [0] * max_n
    total_count = [0] * max_n
    total_cand_len = 0
    total_ref_len = 0
    for candidate, references in zip(candidates, references_list):
        cand_tokens = tokenize(candidate)
        ref_token_lists = [tokenize(ref) for ref in references]
        total_cand_len += len(cand_tokens)
        ref_lengths = [len(rt) for rt in ref_token_lists]
        if ref_lengths:
            total_ref_len += min(ref_lengths, key=lambda rl: (abs(rl - len(cand_tokens)), rl))
        for n in range(1, max_n + 1):
            clipped, count = modified_precision(cand_tokens, ref_token_lists, n)
            total_clipped[n - 1] += clipped
            total_count[n - 1] += count
    precisions = []
    log_avg = 0.0
    all_positive = True
    for n in range(max_n):
        p = total_clipped[n] / total_count[n] if total_count[n] else 0.0
        precisions.append(p)
        if p == 0:
            all_positive = False
        else:
            log_avg += weights[n] * math.log(p)
    if total_cand_len == 0 or total_ref_len == 0:
        bp = 0.0
    elif total_cand_len >= total_ref_len:
        bp = 1.0
    else:
        bp = math.exp(1 - total_ref_len / total_cand_len)
    bleu = bp * math.exp(log_avg) if all_positive else 0.0
    return {"bleu": bleu, "precisions": precisions, "bp": bp,
            "length_ratio": total_cand_len / total_ref_len if total_ref_len > 0 else 0}


def build_gloss_reference(verse_data_list):
    """Build a reference 'translation' from TBESG glosses.

    Takes first option from multi-value glosses: 'in/on/among' -> 'in'.
    Skips pure-punctuation and empty glosses.
    """
    words = []
    for verse_data in verse_data_list:
        for t in verse_data["tokens"]:
            gloss = t.get("gloss", "").strip()
            if not gloss or gloss in (".", ",", ";", "·"):
                continue
            # Take first alternative from multi-value glosses
            first = gloss.split("/")[0].strip()
            # Also handle "word (note)" patterns — take just the word
            paren = first.find("(")
            if paren > 0:
                first = first[:paren].strip()
            if first:
                words.append(first.lower())
    return " ".join(words)


def load_reference_file(path):
    """Load a reference translation file. Lines starting with # are comments."""
    with open(path, "r", encoding="utf-8") as f:
        lines = []
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                lines.append(line)
    return " ".join(lines)
