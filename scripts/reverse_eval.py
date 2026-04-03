#!/usr/bin/env python3
"""Reverse-direction evaluation: English glosses → Greek reconstruction.

Tests whether a model actually knows Biblical Greek rather than just
pattern-matching English Bible verses from training data.

Three difficulty tiers:
  Tier 1: Gloss + Morphology + Lemma → produce inflected Greek form
  Tier 2: Gloss + Morphology → produce inflected Greek word
  Tier 3: Gloss sequence only → produce complete Greek sentence

Usage:
    python reverse_eval.py --index verse_index.json --model qwen2.5 --tier 2 --n 20
    python reverse_eval.py --index verse_index.json --models qwen2.5 llama3.2 --tier 1 --n 10
    python reverse_eval.py --index verse_index.json --model qwen2.5 --tier 3 --output evaluations/reverse_tier3.md
"""

import argparse
import hashlib
import json
import os
import random
import re
import sys
import time
import unicodedata

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import ollama_client

INDEX_PATH = os.path.join(SCRIPT_DIR, "..", "references", "verse_index.json")
CACHE_DIR = os.path.join(SCRIPT_DIR, "..", "evaluations", ".cache")

# Famous verses to exclude — these are heavily memorized in training data.
# Listed as "book.chapter.verse" keys.
FAMOUS_VERSES = {
    "40.5.3", "40.5.4", "40.5.5", "40.5.6", "40.5.7", "40.5.8", "40.5.9",  # Beatitudes
    "40.6.9", "40.6.10", "40.6.11", "40.6.12", "40.6.13",  # Lord's Prayer
    "40.28.19", "40.28.20",  # Great Commission
    "41.1.1",  # Mark 1:1
    "42.1.1", "42.1.2", "42.1.3", "42.1.4",  # Luke prologue
    "42.2.10", "42.2.11",  # Good tidings
    "43.1.1", "43.1.2", "43.1.3", "43.1.14",  # John prologue
    "43.3.16", "43.3.17",  # John 3:16-17
    "43.11.35",  # Jesus wept
    "43.14.6",  # Way truth life
    "44.1.8",  # Acts 1:8
    "45.1.16", "45.1.17",  # Romans 1:16-17
    "45.3.23",  # All have sinned
    "45.5.8",  # God demonstrates love
    "45.6.23",  # Wages of sin
    "45.8.1",  # No condemnation
    "45.8.28",  # All things work together
    "45.10.9", "45.10.10",  # Confess with mouth
    "45.12.1", "45.12.2",  # Living sacrifice
    "46.13.4", "46.13.5", "46.13.6", "46.13.7", "46.13.8",  # Love is patient
    "46.13.13",  # Faith hope love
    "47.5.17",  # New creation
    "47.5.21",  # Made sin for us
    "48.2.8", "48.2.9",  # By grace through faith
    "48.5.22", "48.5.23",  # Fruit of the spirit
    "50.4.6", "50.4.7",  # Be anxious for nothing
    "50.4.13",  # I can do all things
    "55.3.16", "55.3.17",  # All scripture
    "58.11.1",  # Faith is substance
    "58.11.6",  # Without faith impossible
    "59.1.2", "59.1.3",  # Count it all joy
    "60.5.7",  # Cast all anxiety
    "62.4.8",  # God is love
    "66.3.20",  # Behold I stand at door
    "66.21.4",  # Wipe away tears
}


def load_index(path=None):
    """Load the verse index JSON."""
    path = path or INDEX_PATH
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def sample_verses(index, n, seed, exclude_famous=True):
    """Sample n random verses from the index, excluding famous ones."""
    keys = list(index.keys())
    if exclude_famous:
        keys = [k for k in keys if k not in FAMOUS_VERSES]
    rng = random.Random(seed)
    if n > len(keys):
        n = len(keys)
    selected = rng.sample(keys, n)
    return selected


def strip_accents(text):
    """Remove combining diacritical marks from Greek text."""
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch)[0] != "M")
    return unicodedata.normalize("NFC", stripped)


def levenshtein(s1, s2):
    """Compute Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            cost = 0 if c1 == c2 else 1
            curr.append(min(curr[j] + 1, prev[j + 1] + 1, prev[j] + cost))
        prev = curr
    return prev[-1]


def build_tier1_prompt(verse_data):
    """Tier 1: Give gloss + morph + lemma, ask for inflected form."""
    lines = [
        "You are given a list of Greek New Testament tokens with their English gloss, "
        "morphology code (Robinson's RMAC), and dictionary lemma. "
        "For each token, produce the correctly inflected Koine Greek form.",
        "",
        "Return ONLY a numbered list with the inflected Greek word for each position. "
        "No explanations, no transliterations, no English — just the Greek forms.",
        "",
        "Tokens:",
    ]
    for i, t in enumerate(verse_data["tokens"], 1):
        lines.append(
            f"  {i}. Gloss: {t['gloss']} | Morph: {t['morph']} | Lemma: {t['lemma']}"
        )
    return "\n".join(lines)


def build_tier2_prompt(verse_data):
    """Tier 2: Give gloss + morph only, ask for inflected Greek word."""
    lines = [
        "You are given a list of English glosses and morphology codes (Robinson's RMAC) "
        "from a Koine Greek New Testament verse. "
        "For each position, produce the correct inflected Koine Greek word.",
        "",
        "Return ONLY a numbered list with the inflected Greek word for each position. "
        "No explanations, no transliterations, no English — just the Greek forms.",
        "",
        "Tokens:",
    ]
    for i, t in enumerate(verse_data["tokens"], 1):
        lines.append(f"  {i}. Gloss: {t['gloss']} | Morph: {t['morph']}")
    return "\n".join(lines)


def build_tier3_prompt(verse_data):
    """Tier 3: Give gloss sequence only, ask for Greek sentence."""
    glosses = [t["gloss"] for t in verse_data["tokens"]]
    gloss_str = " | ".join(glosses)
    lines = [
        "You are given an ordered sequence of English word-level glosses from a "
        "Koine Greek New Testament verse. Produce the complete Greek sentence "
        "with correctly inflected forms and proper word order.",
        "",
        "Return ONLY the Greek text — one line, no explanations, no English, "
        "no transliterations.",
        "",
        f"Gloss sequence: {gloss_str}",
    ]
    return "\n".join(lines)


def build_prompt(verse_data, tier):
    """Build the appropriate prompt for the given tier."""
    if tier == 1:
        return build_tier1_prompt(verse_data)
    elif tier == 2:
        return build_tier2_prompt(verse_data)
    elif tier == 3:
        return build_tier3_prompt(verse_data)
    else:
        raise ValueError(f"Unknown tier: {tier}")


SYSTEM_PROMPT = (
    "You are a Koine Greek language expert specializing in New Testament Greek. "
    "You produce accurate, correctly-accented Greek text. "
    "Follow the instructions exactly and return only what is asked for."
)


def parse_numbered_response(text, expected_count):
    """Parse a numbered list response into individual Greek tokens.

    Handles formats like:
        1. Βίβλος
        1) Βίβλος
        1: Βίβλος
    """
    tokens = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        # Match numbered patterns: "1. word", "1) word", "1: word"
        m = re.match(r"^\d+[\.\)\:]\s*(.+)$", line)
        if m:
            token = m.group(1).strip()
            # Remove any trailing explanation after dash, comma, or parenthesis
            token = re.split(r"\s*[-—(,]", token)[0].strip()
            # Remove surrounding quotes if present
            token = token.strip("\"'""''`")
            tokens.append(token)
    return tokens


def parse_sentence_response(text):
    """Parse a single-sentence Greek response into tokens."""
    text = text.strip()
    # Take only the first non-empty line
    for line in text.split("\n"):
        line = line.strip()
        if line and any(unicodedata.category(ch).startswith("L") for ch in line):
            # Remove punctuation at word boundaries for comparison
            words = line.split()
            tokens = []
            for w in words:
                # Strip leading/trailing punctuation but keep Greek chars
                cleaned = re.sub(r"^[^\w]+|[^\w]+$", "", w, flags=re.UNICODE)
                if cleaned:
                    tokens.append(cleaned)
            return tokens
    return []


def score_token(predicted, ground_truth):
    """Score a single predicted token against ground truth.

    Returns dict with scoring metrics.
    """
    gt_norm = unicodedata.normalize("NFC", ground_truth)
    pred_norm = unicodedata.normalize("NFC", predicted) if predicted else ""

    exact = (pred_norm == gt_norm)
    accent_stripped = (strip_accents(pred_norm).lower() == strip_accents(gt_norm).lower())
    edit_dist = levenshtein(pred_norm, gt_norm)

    return {
        "predicted": predicted or "",
        "ground_truth": ground_truth,
        "exact_match": exact,
        "accent_stripped_match": accent_stripped,
        "edit_distance": edit_dist,
    }


def score_verse(predicted_tokens, verse_data, tier):
    """Score all predicted tokens for a verse against ground truth."""
    gt_tokens = verse_data["tokens"]
    scores = []

    for i, gt in enumerate(gt_tokens):
        pred = predicted_tokens[i] if i < len(predicted_tokens) else ""
        s = score_token(pred, gt["word"])

        # Lemma match (for tiers 2 and 3 where lemma isn't given)
        if tier >= 2 and pred:
            pred_stripped = strip_accents(pred).lower()
            gt_lemma_stripped = strip_accents(gt["lemma"]).lower()
            # Rough lemma check: does the predicted word share the same root?
            s["lemma_match"] = pred_stripped.startswith(gt_lemma_stripped[:3]) if len(gt_lemma_stripped) >= 3 else (pred_stripped == gt_lemma_stripped)
        else:
            s["lemma_match"] = None

        scores.append(s)

    return {
        "token_scores": scores,
        "total_tokens": len(gt_tokens),
        "predicted_count": len(predicted_tokens),
        "exact_matches": sum(1 for s in scores if s["exact_match"]),
        "accent_stripped_matches": sum(1 for s in scores if s["accent_stripped_match"]),
        "mean_edit_distance": (
            sum(s["edit_distance"] for s in scores) / len(scores) if scores else 0
        ),
    }


def cache_key(model, verse_key, tier):
    """Generate a cache key for a specific model/verse/tier combination."""
    raw = f"{model}_{verse_key}_tier{tier}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def get_cached(model, verse_key, tier):
    """Return cached LLM response if available."""
    key = cache_key(model, verse_key, tier)
    path = os.path.join(CACHE_DIR, f"{key}.json")
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def save_cache(model, verse_key, tier, response, elapsed):
    """Cache an LLM response."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    key = cache_key(model, verse_key, tier)
    path = os.path.join(CACHE_DIR, f"{key}.json")
    data = {
        "model": model,
        "verse_key": verse_key,
        "tier": tier,
        "response": response,
        "elapsed": elapsed,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def run_verse(model, verse_key, verse_data, tier, no_cache=False):
    """Run a single verse through the model. Returns (response, elapsed, cache_hit)."""
    if not no_cache:
        cached = get_cached(model, verse_key, tier)
        if cached:
            return cached["response"], cached["elapsed"], True

    prompt = build_prompt(verse_data, tier)
    t0 = time.time()
    response = ollama_client.chat(model, SYSTEM_PROMPT, prompt, temperature=0.3)
    elapsed = time.time() - t0
    save_cache(model, verse_key, tier, response, elapsed)
    return response, elapsed, False


def format_verse_report(verse_key, verse_data, model_results, tier):
    """Format a single verse's evaluation results as Markdown."""
    lines = [f"### Verse {verse_key}", ""]

    # Show ground truth
    gt_tokens = verse_data["tokens"]
    gt_greek = " ".join(t["word"] for t in gt_tokens)
    lines.append(f"**Ground truth:** {gt_greek}")
    lines.append("")

    # Show what was given to the model
    if tier == 1:
        lines.append("**Given (Tier 1 — gloss + morph + lemma):**")
        for i, t in enumerate(gt_tokens, 1):
            lines.append(f"  {i}. {t['gloss']} | {t['morph']} | {t['lemma']}")
    elif tier == 2:
        lines.append("**Given (Tier 2 — gloss + morph):**")
        for i, t in enumerate(gt_tokens, 1):
            lines.append(f"  {i}. {t['gloss']} | {t['morph']}")
    else:
        glosses = " | ".join(t["gloss"] for t in gt_tokens)
        lines.append(f"**Given (Tier 3 — glosses only):** {glosses}")
    lines.append("")

    # Results per model
    for model, (response, score_data, elapsed, cache_hit) in model_results.items():
        cached_str = " (cached)" if cache_hit else ""
        lines.append(f"#### {model}{cached_str} — {elapsed:.1f}s")
        lines.append("")

        # Token comparison table
        lines.append("| # | Ground Truth | Predicted | Exact | Accent Match | Edit Dist |")
        lines.append("|---|-------------|-----------|-------|-------------|-----------|")
        for i, ts in enumerate(score_data["token_scores"]):
            exact_sym = "+" if ts["exact_match"] else "-"
            accent_sym = "+" if ts["accent_stripped_match"] else "-"
            lines.append(
                f"| {i+1} | {ts['ground_truth']} | {ts['predicted']} "
                f"| {exact_sym} | {accent_sym} | {ts['edit_distance']} |"
            )
        lines.append("")
        lines.append(
            f"**Exact: {score_data['exact_matches']}/{score_data['total_tokens']} "
            f"({100*score_data['exact_matches']/max(score_data['total_tokens'],1):.0f}%) "
            f"| Accent-stripped: {score_data['accent_stripped_matches']}/{score_data['total_tokens']} "
            f"({100*score_data['accent_stripped_matches']/max(score_data['total_tokens'],1):.0f}%) "
            f"| Mean edit dist: {score_data['mean_edit_distance']:.1f}**"
        )
        lines.append("")

    return "\n".join(lines)


def format_summary_table(all_scores, models, tier):
    """Format aggregate summary table across all verses."""
    lines = [
        "## Summary",
        "",
        f"**Tier {tier}** | {len(all_scores)} verses evaluated",
        "",
        "| Model | Exact Match % | Accent-Stripped % | Mean Edit Dist | Total Time |",
        "|-------|--------------|-------------------|----------------|------------|",
    ]

    for model in models:
        total_tokens = 0
        total_exact = 0
        total_accent = 0
        total_edit = 0
        total_time = 0.0
        verse_count = 0

        for verse_key, model_results in all_scores.items():
            if model in model_results:
                _, score_data, elapsed, _ = model_results[model]
                total_tokens += score_data["total_tokens"]
                total_exact += score_data["exact_matches"]
                total_accent += score_data["accent_stripped_matches"]
                total_edit += score_data["mean_edit_distance"] * score_data["total_tokens"]
                total_time += elapsed
                verse_count += 1

        if total_tokens > 0:
            exact_pct = 100 * total_exact / total_tokens
            accent_pct = 100 * total_accent / total_tokens
            mean_edit = total_edit / total_tokens
        else:
            exact_pct = accent_pct = mean_edit = 0

        lines.append(
            f"| {model} | {exact_pct:.1f}% ({total_exact}/{total_tokens}) "
            f"| {accent_pct:.1f}% ({total_accent}/{total_tokens}) "
            f"| {mean_edit:.2f} | {total_time:.1f}s |"
        )

    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Reverse evaluation: English glosses → Greek reconstruction"
    )
    parser.add_argument("--index", default=INDEX_PATH, help="Path to verse_index.json")
    parser.add_argument("--model", help="Single Ollama model tag")
    parser.add_argument("--models", nargs="+", help="Multiple model tags for comparison")
    parser.add_argument("--tier", type=int, choices=[1, 2, 3], default=2,
                        help="Difficulty tier (1=easiest, 3=hardest; default: 2)")
    parser.add_argument("--n", type=int, default=20,
                        help="Number of random verses to test (default: 20)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for reproducible verse selection (default: 42)")
    parser.add_argument("--output", help="Output Markdown file (default: stdout)")
    parser.add_argument("--no-cache", action="store_true",
                        help="Skip cache, force fresh LLM calls")
    parser.add_argument("--include-famous", action="store_true",
                        help="Include famous/memorized verses (default: excluded)")
    args = parser.parse_args()

    models = args.models or ([args.model] if args.model else ["qwen2.5"])

    print(f"Loading verse index from {args.index}...", file=sys.stderr)
    index = load_index(args.index)
    print(f"  {len(index)} verses loaded.", file=sys.stderr)

    verse_keys = sample_verses(
        index, args.n, args.seed,
        exclude_famous=not args.include_famous
    )
    print(
        f"  Sampled {len(verse_keys)} verses (seed={args.seed}, "
        f"exclude_famous={not args.include_famous})",
        file=sys.stderr
    )

    # Run evaluation
    all_scores = {}  # verse_key → {model → (response, score_data, elapsed, cache_hit)}

    for vi, vk in enumerate(verse_keys, 1):
        verse_data = index[vk]
        model_results = {}

        for model in models:
            print(
                f"  [{vi}/{len(verse_keys)}] {vk} — {model} (tier {args.tier})...",
                file=sys.stderr, end=" "
            )
            try:
                response, elapsed, cache_hit = run_verse(
                    model, vk, verse_data, args.tier, no_cache=args.no_cache
                )
                # Parse response
                if args.tier in (1, 2):
                    predicted = parse_numbered_response(
                        response, len(verse_data["tokens"])
                    )
                else:
                    predicted = parse_sentence_response(response)

                score_data = score_verse(predicted, verse_data, args.tier)
                model_results[model] = (response, score_data, elapsed, cache_hit)
                status = "cached" if cache_hit else f"{elapsed:.1f}s"
                exact_pct = 100 * score_data["exact_matches"] / max(score_data["total_tokens"], 1)
                print(f"{status} — {exact_pct:.0f}% exact", file=sys.stderr)

            except Exception as e:
                print(f"ERROR: {e}", file=sys.stderr)
                empty_score = {
                    "token_scores": [],
                    "total_tokens": len(verse_data["tokens"]),
                    "predicted_count": 0,
                    "exact_matches": 0,
                    "accent_stripped_matches": 0,
                    "mean_edit_distance": 99,
                }
                model_results[model] = (str(e), empty_score, 0, False)

        all_scores[vk] = model_results

    # Build report
    report_lines = [
        f"# Reverse Evaluation: English → Greek (Tier {args.tier})",
        "",
        f"**Date:** {time.strftime('%Y-%m-%d %H:%M')}",
        f"**Models:** {', '.join(models)}",
        f"**Verses:** {len(verse_keys)} (seed={args.seed})",
        f"**Famous verses excluded:** {not args.include_famous}",
        "",
    ]

    # Summary table first
    report_lines.append(format_summary_table(all_scores, models, args.tier))

    # Per-verse details
    report_lines.append("## Per-Verse Results")
    report_lines.append("")
    for vk in verse_keys:
        report_lines.append(
            format_verse_report(vk, index[vk], all_scores[vk], args.tier)
        )

    report_lines.append("---")
    report_lines.append("")
    report_lines.append(
        "*Ground truth: Open Greek New Testament (OGNT) by Eliran Wong, CC BY-SA 4.0.*"
    )

    report = "\n".join(report_lines)

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\nWrote report to {args.output}", file=sys.stderr)
    else:
        sys.stdout.buffer.write(report.encode("utf-8"))


if __name__ == "__main__":
    main()
