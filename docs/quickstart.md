# Biblical Greek Translation — Quick Start Guide

Translate Koine Greek New Testament passages to English using a local LLM (Ollama) and the OpenGNT corpus. No paid APIs required.

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| **Python 3.8+** | For the helper scripts |
| **Ollama** | Running locally with at least one model pulled (e.g. `qwen2.5`, `llama3.2`) |
| **OpenGNT** | Cloned from https://github.com/eliranwong/OpenGNT |
| **sciClaw** | Configured in PHI mode to use Ollama |

## 1. Clone the Greek Corpus (one-time)

```bash
cd <your-workspace>
git clone https://github.com/eliranwong/OpenGNT
```

Unzip the base text if not already extracted:

```bash
cd OpenGNT
unzip OpenGNT_BASE_TEXT.zip -d OpenGNT_BASE_TEXT_unzipped
```

## 2. Build the Verse Index (one-time)

From the `sciclaw` directory:

```bash
python skills/biblical-greek-translation/scripts/index_opengnt.py \
  --input ../OpenGNT/OpenGNT_BASE_TEXT_unzipped/OpenGNT_version3_3.csv \
  --output skills/biblical-greek-translation/references/verse_index.json
```

Expected output: **7,941 verses / 138,013 tokens** covering the entire New Testament (Matthew–Revelation).

## 3. Look Up a Passage

Generate a Markdown translation template for any NT passage:

```bash
python skills/biblical-greek-translation/scripts/lookup_passage.py \
  --index skills/biblical-greek-translation/references/verse_index.json \
  --passage "John 1:1-5" \
  --output translations/John_1_1-5.md
```

This produces a structured report with:
- Full Greek text (accented, verse-numbered)
- Token analysis table (lemma, morphology code, open-license TBESG gloss)
- Translation placeholder sections
- Notes and glossary update sections
- CC BY-SA 4.0 attribution

### Passage reference formats

| Format | Example |
|--------|---------|
| Single verse | `"John 3:16"` |
| Verse range | `"Romans 8:28-30"` |
| Abbreviated book | `"Rom 8:28"`, `"1Cor 13:1-3"` |

Book names and abbreviations are defined in `skills/biblical-greek-translation/references/book_numbers.json`.

## 4. Translate with the Agent

When using sciClaw in PHI mode, ask the agent to translate a passage. The skill triggers on phrases like:

- *"Translate John 1:1-5 from Greek"*
- *"Give me an interlinear gloss of Romans 8:28"*
- *"Parse the morphology of Philippians 2:5-11"*

The agent will:
1. Look up the passage from the verse index
2. Display the Greek text with token analysis
3. Draft a balanced (literal + readable) English translation
4. Add translator notes on ambiguous constructions, textual variants, and key terms
5. Check `references/glossary.json` for rendering consistency

Output is saved as Markdown in the `translations/` directory.

## 5. Helper Scripts Reference

| Script | Purpose |
|--------|---------|
| `scripts/index_opengnt.py` | Parse OpenGNT CSV → JSON verse index |
| `scripts/lookup_passage.py` | Look up passages and generate Markdown report templates |
| `scripts/normalize_greek.py` | Unicode normalization (NFC/NFKC), accent stripping |

## 6. Reference Files

| File | Purpose |
|------|---------|
| `references/verse_index.json` | Pre-built index of all 7,941 NT verses with token data |
| `references/book_numbers.json` | Book name/abbreviation → OpenGNT book number (40–66) |
| `references/glossary.json` | Preferred English renderings for high-frequency Greek lemmas |

## License & Attribution

- **Greek source text (OGNT):** CC BY-SA 4.0 — Eliran Wong
- **TBESG glosses:** Open data from Tyndale House, Cambridge
- **Berean translations (IT/LT/ST columns):** Copyrighted — **not used** by this skill

All generated translations must include the attribution line:

> *Greek source: Open Greek New Testament (OGNT) by Eliran Wong, CC BY-SA 4.0.*

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `Unknown book name` error | Check spelling against `book_numbers.json`; use full name or standard abbreviation |
| `No verses found` | Verify chapter/verse numbers exist in the NT book; OpenGNT covers Matthew (40) through Revelation (66) only |
| Greek text garbled in terminal | Set `$env:PYTHONIOENCODING="utf-8"` (PowerShell) or `export PYTHONIOENCODING=utf-8` (bash) before running |
| Verse index missing | Run the indexer script from Step 2 |
