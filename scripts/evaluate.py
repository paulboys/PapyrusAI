#!/usr/bin/env python3
"""Multi-model evaluation of Biblical Greek → English translations.

Runs translation across all specified Ollama models, produces side-by-side
Markdown comparisons, and computes BLEU scores against reference translations.

Usage:
    python evaluate.py --index verse_index.json --passage "John 1:1-3"
    python evaluate.py --index verse_index.json --passages-file passages.txt
    python evaluate.py --index verse_index.json --passage "Rom 8:28" --models qwen2.5 llama3.2
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time

# Resolve paths relative to this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import ollama_client
import bleu as bleu_mod
from lookup_passage import (
    load_book_map,
    parse_passage_ref,
    lookup_verses,
    generate_report,
    load_skill_md,
    splice_llm_sections,
    build_lexicon_block,
    FEW_SHOT_EXAMPLES,
)

DEFAULT_MODELS = ["qwen2.5", "llama3.2"]
DEFAULT_MAX_VERSES = 10
CACHE_DIR = os.path.join(SCRIPT_DIR, "..", "evaluations", ".cache")



def passage_hash(passage_ref):
    """Short hash of a passage reference for cache keys."""
    return hashlib.sha256(passage_ref.encode("utf-8")).hexdigest()[:12]


def cache_path(model, passage_ref):
    """Return the cache file path for a model + passage combination."""
    tag = model.replace(":", "_").replace("/", "_")
    return os.path.join(CACHE_DIR, f"{tag}_{passage_hash(passage_ref)}.json")


def load_cache(model, passage_ref):
    """Load cached response if it exists. Returns dict or None."""
    path = cache_path(model, passage_ref)
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def save_cache(model, passage_ref, data):
    """Save response data to cache."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = cache_path(model, passage_ref)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def translate_one(model, template, passage_ref, temperature=0.7, use_cache=True,
                  verses=None):
    """Translate a passage with a single model. Returns (completed_report, raw, elapsed)."""
    if use_cache:
        cached = load_cache(model, passage_ref)
        if cached:
            print(f"  [{model}] Using cached response", file=sys.stderr)
            completed = splice_llm_sections(template, cached["raw"])
            if completed == template:
                completed = template.rstrip() + "\n\n## Raw LLM Output\n\n" + cached["raw"] + "\n"
            return completed, cached["raw"], cached["elapsed"]

    system_prompt = load_skill_md()

    # Build enriched prompt with lexicon injection and few-shot examples
    rag_block = ""
    if verses:
        rag_block = build_lexicon_block(verses) + "\n\n"

    user_prompt = (
        f"Below is a structured report template for {passage_ref}. "
        "Fill in the ## Translation section with a balanced (literal + readable) "
        "English translation. Fill in the ## Notes section with translator notes "
        "on ambiguous constructions, tense/aspect choices, and key terms. "
        "Fill in the ## Glossary Updates table with any new preferred renderings. "
        "Return the complete report with all sections filled in.\n\n"
        f"{FEW_SHOT_EXAMPLES}\n\n"
        f"{rag_block}"
        f"{template}"
    )

    print(f"  [{model}] Sending to Ollama...", file=sys.stderr)
    t0 = time.time()
    raw = ollama_client.chat(model, system_prompt, user_prompt,
                             temperature=temperature)
    elapsed = time.time() - t0
    print(f"  [{model}] Response in {elapsed:.1f}s", file=sys.stderr)

    # Cache the raw response
    save_cache(model, passage_ref, {"raw": raw, "elapsed": elapsed})

    completed = splice_llm_sections(template, raw)
    if completed == template:
        completed = template.rstrip() + "\n\n## Raw LLM Output\n\n" + raw + "\n"

    return completed, raw, elapsed





def extract_translation_section(report):
    """Extract the ## Translation and ## Notes sections from a completed report."""
    match = re.search(
        r"(## Translation\s*\n.*?)(?=\n## Glossary|\n---|\Z)",
        report, re.DOTALL
    )
    return match.group(1).strip() if match else report


def extract_translation_text(report):
    """Extract just the translation text (no headers) for BLEU scoring."""
    match = re.search(
        r"## Translation\s*\n(.*?)(?=\n## |\n---|\Z)",
        report, re.DOTALL
    )
    if match:
        text = match.group(1).strip()
        text = re.sub(r"<!--.*?-->", "", text)
        text = text.replace("[translation]", "")
        return text.strip()
    return ""


def generate_eval_report(passage_ref, template, results, bleu_scores=None):
    """Generate the side-by-side evaluation Markdown."""
    if bleu_scores is None:
        bleu_scores = {}
    lines = [f"# Evaluation: {passage_ref}", ""]

    # Shared context: Greek text + token analysis (from template up to ## Translation)
    shared_match = re.search(r"(.*?)(?=## Translation)", template, re.DOTALL)
    if shared_match:
        lines.append(shared_match.group(1).strip())
    lines.append("")

    # Per-model sections
    lines.append("---")
    lines.append("")
    for model, data in results.items():
        lines.append(f"## Model: {model}")
        lines.append("")
        lines.append(f"*Response time: {data['elapsed']:.1f}s*")
        lines.append("")

        # Extract just translation + notes from the completed report
        trans_section = extract_translation_section(data["report"])
        lines.append(trans_section)
        lines.append("")
        lines.append("---")
        lines.append("")

    # Scoring summary table
    lines.append("## Scoring Summary")
    lines.append("")
    lines.append("| Model | BLEU-4 | Time |")
    lines.append("|-------|--------|------|")

    for model in results:
        elapsed = results[model]["elapsed"]
        bleu_val = bleu_scores.get(model, {}).get("bleu", 0)
        lines.append(f"| {model} | {bleu_val:.3f} | {elapsed:.1f}s |")
    lines.append("")

    # BLEU details table
    lines.append("### BLEU Scores")
    lines.append("")
    lines.append("| Model | BLEU-4 | Unigram | Bigram | Trigram | 4-gram | BP | Len Ratio | Refs |")
    lines.append("|-------|--------|---------|--------|---------|--------|-----|-----------|------|")
    for model in results:
        b = bleu_scores.get(model, {})
        p = b.get("precisions", [0, 0, 0, 0])
        lines.append(
            f"| {model} | {b.get('bleu', 0):.3f} "
            f"| {p[0]:.3f} | {p[1]:.3f} | {p[2]:.3f} | {p[3]:.3f} "
            f"| {b.get('bp', 0):.3f} | {b.get('length_ratio', 0):.2f} "
            f"| {b.get('ref_count', 0)} |"
        )
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("*Greek source: Open Greek New Testament (OGNT) by Eliran Wong, CC BY-SA 4.0.*")
    lines.append("")

    return "\n".join(lines)


def compute_bleu_scores(results, verses, reference_files=None):
    """Compute BLEU scores for each model's translation against references."""
    references = []
    gloss_ref = bleu_mod.build_gloss_reference(verses)
    if gloss_ref.strip():
        references.append(gloss_ref)
    if reference_files:
        for ref_path in reference_files:
            if os.path.isfile(ref_path):
                ref_text = bleu_mod.load_reference_file(ref_path)
                if ref_text.strip():
                    references.append(ref_text)
                    print(f"    Loaded reference: {ref_path}", file=sys.stderr)
    if not references:
        return {}
    bleu_scores = {}
    for model, data in results.items():
        candidate = extract_translation_text(data["report"])
        if not candidate or "[translation]" in candidate:
            bleu_scores[model] = {
                "bleu": 0.0, "precisions": [0, 0, 0, 0],
                "bp": 0.0, "length_ratio": 0.0, "ref_count": len(references),
            }
            continue
        result = bleu_mod.sentence_bleu(candidate, references)
        result["ref_count"] = len(references)
        bleu_scores[model] = result
        print(f"    [{model}] BLEU-4: {result['bleu']:.3f}", file=sys.stderr)
    return bleu_scores


def run_evaluation(passage_ref, index, book_map, models, temperature=0.7,
                   use_cache=True, max_verses=DEFAULT_MAX_VERSES,
                   reference_files=None):
    """Run full evaluation for one passage across all models."""
    book_num, chapter, start_v, end_v = parse_passage_ref(passage_ref, book_map)

    verse_count = end_v - start_v + 1
    if max_verses > 0 and verse_count > max_verses:
        print(f"Error: {verse_count} verses in {passage_ref}, max is {max_verses}. "
              f"Use --max-verses 0 to disable.", file=sys.stderr)
        return None

    verses = lookup_verses(index, book_num, chapter, start_v, end_v)
    if not verses:
        print(f"No verses found for {passage_ref}", file=sys.stderr)
        return None

    display_name = passage_ref.rsplit(" ", 1)[0]
    template = generate_report(passage_ref, verses, display_name, chapter, start_v, end_v)

    # Translate with each model
    print(f"\nTranslating {passage_ref} with {len(models)} models...", file=sys.stderr)
    results = {}
    for model in models:
        report, raw, elapsed = translate_one(model, template, passage_ref,
                                             temperature=temperature,
                                             use_cache=use_cache,
                                             verses=verses)
        results[model] = {"report": report, "raw": raw, "elapsed": elapsed}

    # BLEU scoring against references
    print(f"\nComputing BLEU scores...", file=sys.stderr)
    bleu_scores = compute_bleu_scores(results, verses, reference_files)

    eval_report = generate_eval_report(passage_ref, template, results, bleu_scores)
    return eval_report


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate Biblical Greek translations across multiple Ollama models"
    )
    parser.add_argument("--index", required=True, help="Path to verse_index.json")
    parser.add_argument("--passage", help='Single passage, e.g. "John 1:1-3"')
    parser.add_argument("--passages-file", help="File with one passage reference per line")
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS,
                        help=f"Ollama model tags (default: {' '.join(DEFAULT_MODELS)})")
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--max-verses", type=int, default=DEFAULT_MAX_VERSES,
                        help=f"Max verses per passage (default: {DEFAULT_MAX_VERSES}; 0 = no limit)")
    parser.add_argument("--output-dir", default=os.path.join(SCRIPT_DIR, "..", "evaluations"),
                        help="Directory for evaluation output (default: evaluations/)")
    parser.add_argument("--no-cache", action="store_true", help="Skip response cache, force fresh API calls")
    parser.add_argument("--references", nargs="*", default=None,
                        help="Reference translation files for BLEU scoring (e.g., kjv.txt web.txt)")
    parser.add_argument("--books", help="Path to book_numbers.json (default: auto-detect)")
    args = parser.parse_args()

    if not args.passage and not args.passages_file:
        parser.error("Provide --passage or --passages-file")

    # Collect passages
    passages = []
    if args.passage:
        passages.append(args.passage)
    if args.passages_file:
        with open(args.passages_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    passages.append(line)

    book_map = load_book_map(args.books)

    with open(args.index, "r", encoding="utf-8") as f:
        index = json.load(f)

    os.makedirs(args.output_dir, exist_ok=True)

    for passage_ref in passages:
        eval_report = run_evaluation(
            passage_ref, index, book_map, args.models,
            temperature=args.temperature,
            use_cache=not args.no_cache,
            max_verses=args.max_verses,
            reference_files=args.references,
        )
        if eval_report is None:
            continue

        # Write evaluation file
        safe_name = passage_ref.replace(" ", "_").replace(":", "_").replace("-", "_")
        out_path = os.path.join(args.output_dir, f"{safe_name}_eval.md")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(eval_report)
        print(f"\nWrote evaluation to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
