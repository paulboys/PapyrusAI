#!/usr/bin/env python3
"""Look up verses from the OpenGNT JSON index and produce Markdown reports.

Usage:
    python lookup_passage.py --index verse_index.json --passage "John 1:1-5" --output translations/John_1_1-5.md
    python lookup_passage.py --index verse_index.json --passage "Rom 8:28"

    # With Ollama LLM translation:
    python lookup_passage.py --index verse_index.json --passage "John 1:1-5" --ollama --model qwen2.5
"""

import argparse
import json
import os
import re
import sys
import time

# Book name → OpenGNT book number mapping
BOOK_NAMES_FILE = os.path.join(os.path.dirname(__file__), "..", "references", "book_numbers.json")


def load_book_map(path=None):
    """Load book name → number mapping."""
    path = path or BOOK_NAMES_FILE
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_passage_ref(ref, book_map):
    """Parse a passage reference like 'John 1:1-5' into (book_num, chapter, start_verse, end_verse)."""
    ref = ref.strip()

    # Split into book name and chapter:verse
    # Handle multi-word book names like "1 John", "1 Corinthians"
    parts = ref.rsplit(" ", 1)
    if len(parts) != 2:
        raise ValueError(f"Cannot parse passage reference: {ref}")

    book_name = parts[0].strip()
    chap_verse = parts[1].strip()

    # Resolve book number
    book_num = None
    book_name_lower = book_name.lower()
    for name, num in book_map.items():
        if name.lower() == book_name_lower:
            book_num = str(num)
            break

    if book_num is None:
        raise ValueError(f"Unknown book name: {book_name}")

    # Parse chapter:verse or chapter:verse1-verse2
    if ":" not in chap_verse:
        raise ValueError(f"Expected chapter:verse format, got: {chap_verse}")

    chapter, verse_range = chap_verse.split(":", 1)

    if "-" in verse_range:
        start_v, end_v = verse_range.split("-", 1)
        return book_num, chapter, int(start_v), int(end_v)
    else:
        v = int(verse_range)
        return book_num, chapter, v, v


def lookup_verses(index, book_num, chapter, start_verse, end_verse):
    """Return list of verse data dicts for the given range."""
    verses = []
    for v in range(start_verse, end_verse + 1):
        key = f"{book_num}.{chapter}.{v}"
        if key in index:
            verses.append(index[key])
    return verses


def verse_greek_text(verse_data):
    """Reconstruct the Greek text of a verse from tokens."""
    parts = []
    for t in verse_data["tokens"]:
        word = ""
        if t.get("pm_pre"):
            word += t["pm_pre"]
        word += t["word"]
        if t.get("pm_post"):
            word += t["pm_post"]
        parts.append(word)
    return " ".join(parts)


def make_token_table(verse_data):
    """Generate a Markdown token table for a verse."""
    lines = ["| # | Token | Lemma | Morphology | Gloss |",
             "|---|-------|-------|------------|-------|"]
    for i, t in enumerate(verse_data["tokens"], 1):
        token = t["word"]
        lemma = t.get("lemma", "")
        morph = t.get("morph", "")
        gloss = t.get("gloss", "")
        lines.append(f"| {i} | {token} | {lemma} | {morph} | {gloss} |")
    return "\n".join(lines)


def generate_report(passage_ref, verses, book_name, chapter, start_v, end_v):
    """Generate a Markdown translation report template."""
    lines = [f"# {passage_ref}", "", "## Greek Text", ""]

    for v in verses:
        vnum = v["verse"]
        greek = verse_greek_text(v)
        lines.append(f"**{vnum}** {greek}")
    lines.append("")

    lines.append("## Token Analysis")
    lines.append("")
    for v in verses:
        vnum = v["verse"]
        lines.append(f"### Verse {vnum}")
        lines.append("")
        lines.append(make_token_table(v))
        lines.append("")

    lines.append("## Translation")
    lines.append("")
    lines.append("<!-- Replace with balanced (literal + readable) English translation -->")
    for v in verses:
        vnum = v["verse"]
        lines.append(f"**{vnum}** [translation]")
    lines.append("")

    lines.append("## Notes")
    lines.append("")
    lines.append("- [Add translator notes here]")
    lines.append("")

    lines.append("## Glossary Updates")
    lines.append("")
    lines.append("| Lemma | Preferred Rendering | Context Note |")
    lines.append("|-------|-------------------|--------------|")
    lines.append("| | | |")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("*Greek source: Open Greek New Testament (OGNT) by Eliran Wong, CC BY-SA 4.0.*")
    lines.append("*Based on: https://github.com/eliranwong/OpenGNT*")
    lines.append("")

    return "\n".join(lines)


SKILL_MD_PATH = os.path.join(os.path.dirname(__file__), "..", "SKILL.md")
DEFAULT_MAX_VERSES = 10

# RMAC morphology code expansion for human-readable parsing
_RMAC_PARTS_OF_SPEECH = {
    "N": "Noun", "V": "Verb", "A": "Adjective", "ADV": "Adverb",
    "PREP": "Preposition", "CONJ": "Conjunction", "PRT": "Particle",
    "T": "Article", "D": "Demonstrative", "P": "Pronoun",
    "R": "Relative Pronoun", "F": "Reflexive Pronoun", "I": "Interrogative",
    "X": "Indefinite", "C": "Reciprocal", "INJ": "Interjection",
}
_RMAC_TENSE = {"P": "Present", "I": "Imperfect", "F": "Future", "A": "Aorist",
               "X": "Perfect", "Y": "Pluperfect"}
_RMAC_VOICE = {"A": "Active", "M": "Middle", "P": "Passive", "N": "Middle/Passive"}
_RMAC_MOOD = {"I": "Indicative", "S": "Subjunctive", "O": "Optative",
              "M": "Imperative", "N": "Infinitive", "P": "Participle"}
_RMAC_CASE = {"N": "Nominative", "G": "Genitive", "D": "Dative", "A": "Accusative", "V": "Vocative"}
_RMAC_NUMBER = {"S": "Singular", "P": "Plural"}
_RMAC_GENDER = {"M": "Masculine", "F": "Feminine", "N": "Neuter"}


def expand_rmac(code):
    """Expand an RMAC code like 'V-PAI-3P' into a readable string."""
    if not code:
        return ""
    parts = code.split("-")
    pos = _RMAC_PARTS_OF_SPEECH.get(parts[0], parts[0])
    if len(parts) < 2:
        return pos
    detail = parts[1]
    if parts[0] == "V" and len(detail) >= 3:
        tense = _RMAC_TENSE.get(detail[0], detail[0])
        voice = _RMAC_VOICE.get(detail[1], detail[1])
        mood = _RMAC_MOOD.get(detail[2], detail[2])
        extra = ""
        if len(parts) >= 3:
            p3 = parts[2]
            if p3 and p3[0].isdigit():
                extra = f" {p3[0]}p" if len(p3) == 1 else f" {p3}"
            elif len(p3) >= 2:
                case = _RMAC_CASE.get(p3[0], p3[0])
                num = _RMAC_NUMBER.get(p3[1], p3[1])
                gen = _RMAC_GENDER.get(p3[2], "") if len(p3) >= 3 else ""
                extra = f" {case} {num} {gen}".rstrip()
        return f"{pos} {tense} {voice} {mood}{extra}"
    # Non-verb: detail is typically Case-Number-Gender
    result = pos
    if len(detail) >= 1:
        result += " " + _RMAC_CASE.get(detail[0], detail[0])
    if len(detail) >= 2:
        result += " " + _RMAC_NUMBER.get(detail[1], detail[1])
    if len(detail) >= 3:
        result += " " + _RMAC_GENDER.get(detail[2], detail[2])
    return result


def build_lexicon_block(verses):
    """Build a lexicon injection block from verse tokens for RAG.

    Produces a compact per-word entry with expanded morphology, all gloss
    alternatives, Strong's number, and transliteration. Deduplicates by lemma.
    """
    seen_lemmas = {}
    entries = []
    for verse_data in verses:
        for t in verse_data["tokens"]:
            lemma = t.get("lemma", "")
            word = t.get("word", "")
            if not lemma:
                continue
            # Track all inflected forms per lemma
            if lemma in seen_lemmas:
                seen_lemmas[lemma]["forms"].add(word)
                continue
            morph_expanded = expand_rmac(t.get("morph", ""))
            gloss = t.get("gloss", "")
            strong = t.get("strong", "")
            translit = t.get("translit", "")
            entry = {
                "lemma": lemma,
                "forms": {word},
                "morph_raw": t.get("morph", ""),
                "morph_expanded": morph_expanded,
                "gloss": gloss,
                "strong": strong,
                "translit": translit,
            }
            seen_lemmas[lemma] = entry
            entries.append(entry)

    lines = ["## Lexicon (per-word dictionary entries)\n"]
    for e in entries:
        forms = ", ".join(sorted(e["forms"]))
        line = (f"- **{e['lemma']}** ({e['translit']}) [{e['strong']}] "
                f"{e['morph_raw']}={e['morph_expanded']} "
                f"— glosses: {e['gloss']}")
        if len(e["forms"]) > 1:
            line += f" | forms in text: {forms}"
        lines.append(line)
    return "\n".join(lines)


FEW_SHOT_EXAMPLES = '''
## Translation Examples

Here are example Greek→English translations demonstrating the expected style:

### Example 1: Romans 12:2 (style demonstration)
**Greek:** καὶ μὴ συσχηματίζεσθε τῷ αἰῶνι τούτῳ, ἀλλὰ μεταμορφοῦσθε τῇ ἀνακαινώσει τοῦ νοὸς ὑμῶν, εἰς τὸ δοκιμάζειν ὑμᾶς τί τὸ θέλημα τοῦ θεοῦ, τὸ ἀγαθὸν καὶ εὐάρεστον καὶ τέλειον.
**Translation:** And do not be conformed to this age, but be transformed by the renewing of your mind, so that you may discern what the will of God is — what is good and pleasing and perfect.
**Key choices:** συσχηματίζεσθε (present passive imperative) → "be conformed" preserves passive voice; μεταμορφοῦσθε → "be transformed" (cognate to metamorphosis); αἰῶνι → "age" not "world" (distinct from κόσμος).

### Example 2: Hebrews 1:3 (complex syntax)
**Greek:** ὃς ὢν ἀπαύγασμα τῆς δόξης καὶ χαρακτὴρ τῆς ὑποστάσεως αὐτοῦ, φέρων τε τὰ πάντα τῷ ῥήματι τῆς δυνάμεως αὐτοῦ
**Translation:** He, being the radiance of his glory and the exact imprint of his nature, and sustaining all things by the word of his power
**Key choices:** ἀπαύγασμα → "radiance" (active outshining, not reflection); χαρακτήρ → "exact imprint" (the stamped image on a coin); ὑπόστασις → "nature" (literally "substance/being"); φέρων (present active participle) → "sustaining" (continuous action, not merely carrying).

### Example 3: 1 Peter 1:7 (participial chain)
**Greek:** ἵνα τὸ δοκίμιον ὑμῶν τῆς πίστεως πολυτιμότερον χρυσίου τοῦ ἀπολλυμένου, διὰ πυρὸς δὲ δοκιμαζομένου
**Translation:** so that the tested genuineness of your faith — more precious than gold that perishes though tested by fire
**Key choices:** δοκίμιον → "tested genuineness" (the proven quality, not the trial itself); ἀπολλυμένου → "that perishes" (present middle participle, ongoing process); δοκιμαζομένου → "tested" (present passive participle, concurrent with perishing).
'''


def load_skill_md(path=None):
    """Read SKILL.md and return the body (strip YAML frontmatter)."""
    path = path or SKILL_MD_PATH
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    # Strip YAML frontmatter (--- ... ---)
    match = re.match(r"^---\s*\n.*?\n---\s*\n", text, re.DOTALL)
    if match:
        text = text[match.end():]
    return text.strip()


def splice_llm_sections(template, llm_output):
    """Replace placeholder sections in the template with LLM-generated content.

    Extracts ## Translation, ## Notes, and ## Glossary Updates from the LLM
    output and splices them into the cold-standard template.
    """
    result = template

    # Extract and splice Translation section
    trans_match = re.search(
        r"(## Translation\s*\n)(.*?)(?=\n## |\n---|\'\Z)",
        llm_output, re.DOTALL
    )
    if trans_match:
        new_translation = trans_match.group(1) + trans_match.group(2).rstrip() + "\n"
        result = re.sub(
            r"## Translation\s*\n.*?(?=\n## |\n---)",
            new_translation, result, count=1, flags=re.DOTALL
        )

    # Extract and splice Notes section
    notes_match = re.search(
        r"(## Notes\s*\n)(.*?)(?=\n## |\n---|\'\Z)",
        llm_output, re.DOTALL
    )
    if notes_match:
        new_notes = notes_match.group(1) + notes_match.group(2).rstrip() + "\n"
        result = re.sub(
            r"## Notes\s*\n.*?(?=\n## |\n---)",
            new_notes, result, count=1, flags=re.DOTALL
        )

    # Extract and splice Glossary Updates section
    gloss_match = re.search(
        r"(## Glossary Updates\s*\n)(.*?)(?=\n---|\'\Z)",
        llm_output, re.DOTALL
    )
    if gloss_match:
        new_gloss = gloss_match.group(1) + gloss_match.group(2).rstrip() + "\n"
        result = re.sub(
            r"## Glossary Updates\s*\n.*?(?=\n---)",
            new_gloss, result, count=1, flags=re.DOTALL
        )

    return result


def translate_with_ollama(template, passage_ref, model="qwen2.5",
                          temperature=0.7, verses=None):
    """Send the cold-standard template to Ollama and return completed report.

    Returns:
        Tuple of (completed_report, raw_llm_response, elapsed_seconds)
    """
    from ollama_client import chat

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

    print(f"  Sending to Ollama ({model})...", file=sys.stderr)
    t0 = time.time()
    raw = chat(model, system_prompt, user_prompt, temperature=temperature)
    elapsed = time.time() - t0
    print(f"  Response received in {elapsed:.1f}s", file=sys.stderr)

    # Splice LLM sections into the template
    completed = splice_llm_sections(template, raw)

    # If splicing didn't change anything, append raw output as fallback
    if completed == template:
        completed = template.rstrip() + "\n\n## Raw LLM Output\n\n" + raw + "\n"

    return completed, raw, elapsed


def main():
    parser = argparse.ArgumentParser(description="Look up Greek NT passages and generate Markdown reports")
    parser.add_argument("--index", required=True, help="Path to verse_index.json")
    parser.add_argument("--passage", required=True, help='Passage reference, e.g. "John 1:1-5"')
    parser.add_argument("--output", help="Output Markdown file (default: stdout)")
    parser.add_argument("--books", help="Path to book_numbers.json (default: auto-detect)")
    parser.add_argument("--ollama", action="store_true", help="Send template to Ollama for LLM translation")
    parser.add_argument("--model", default="qwen2.5", help="Ollama model tag (default: qwen2.5)")
    parser.add_argument("--temperature", type=float, default=0.7, help="Sampling temperature (default: 0.7)")
    parser.add_argument("--max-verses", type=int, default=DEFAULT_MAX_VERSES,
                        help=f"Max verses per request (default: {DEFAULT_MAX_VERSES}; 0 = no limit)")
    args = parser.parse_args()

    book_map = load_book_map(args.books)

    with open(args.index, "r", encoding="utf-8") as f:
        index = json.load(f)

    book_num, chapter, start_v, end_v = parse_passage_ref(args.passage, book_map)

    # Max-verses safeguard
    verse_count = end_v - start_v + 1
    if args.max_verses > 0 and verse_count > args.max_verses:
        print(f"Error: {verse_count} verses requested, but --max-verses is {args.max_verses}.",
              file=sys.stderr)
        print(f"Use --max-verses 0 to disable this limit.", file=sys.stderr)
        sys.exit(1)

    # Reverse-lookup book name for display
    display_name = args.passage.rsplit(" ", 1)[0]

    verses = lookup_verses(index, book_num, chapter, start_v, end_v)
    if not verses:
        print(f"No verses found for {args.passage}", file=sys.stderr)
        sys.exit(1)

    report = generate_report(args.passage, verses, display_name, chapter, start_v, end_v)

    if args.ollama:
        report, _raw, elapsed = translate_with_ollama(
            report, args.passage, model=args.model, temperature=args.temperature,
            verses=verses
        )
        print(f"Translation completed in {elapsed:.1f}s", file=sys.stderr)

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"Wrote report to {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()
