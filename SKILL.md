---
name: biblical-greek-translation
description: Translate Biblical (Koine) Greek to English. Use when asked to translate Greek NT passages, provide interlinear glosses, parse Greek morphology, look up NT verses in Greek, or produce word-by-word analysis. Triggers on "translate Greek", "Biblical Greek", "Koine Greek", "interlinear", "gloss", "parse morphology", "NT verse", passage references like "John 1:1", "Romans 8:28", or any request involving Greek New Testament text.
---

# Biblical Greek → English Translation

Translate Koine Greek New Testament text into English using a balanced (literal + readable) style. Produce structured Markdown reports with token analysis, translation, and notes.

## Corpus: OpenGNT

The Greek source text is the Open Greek New Testament (OGNT), a free NA-equivalent text licensed CC BY-SA 4.0.

- Location: look for the OpenGNT directory adjacent to the sciclaw workspace, or under `corpora/opengnt/`.
- The indexer script at `scripts/index_opengnt.py` parses the base text and builds a JSON verse index.
- Book numbers 40–66 map to Matthew–Revelation. See `references/book_numbers.json` for the full mapping.

### Setup (first time)

If the verse index does not exist yet, run:

```bash
python skills/biblical-greek-translation/scripts/index_opengnt.py \
  --input <path-to-OpenGNT>/OpenGNT_BASE_TEXT_unzipped/OpenGNT_version3_3.csv \
  --output skills/biblical-greek-translation/references/verse_index.json
```

## Workflow

### 1. Accept Input

Accept either:
- **(A) A passage reference** like `John 1:1-5` or `Rom 8:28` — look it up in the verse index.
- **(B) Pasted Greek text** — use it directly.

For passage references, resolve the book name to its number using `references/book_numbers.json`, then load the matching verses from `references/verse_index.json`.

### 2. Token Analysis

For each verse, build a token table from the indexed data (or by whitespace-splitting pasted text):

| # | Token | Lemma | Morphology | Gloss |
|---|-------|-------|------------|-------|
| 1 | Βίβλος | βίβλος | N-NSF | book |

- Use the `OGNTa` (accented) field as the display token.
- Use `lexeme` for the lemma column.
- Use `rmac` (Robinson's Morphological Analysis Code) for morphology.
- Use `TBESG` (Tyndale House open gloss) for the context-insensitive gloss. This is open data.
- Do NOT use the IT/LT/ST columns (Berean-derived, copyrighted).

### 3. Draft Translation (Balanced Style)

Produce a single English rendering that is:
- **Literal enough** to reflect Greek word order and structure where natural in English.
- **Readable enough** that a non-specialist can follow it without a grammar guide.
- Preserve tense/aspect distinctions (aorist vs present vs perfect).
- Render articles faithfully but allow natural English omission where Greek uses them generically.
- Transliterate proper names consistently (prefer standard English forms: Jesus, Christ, Abraham, David).

### 4. Translator Notes

After the translation, add brief notes on:
- Ambiguous words or constructions with more than one defensible rendering.
- Significant textual variants (if noted in the OpenGNT `Note` column).
- Theological key terms where the chosen gloss carries interpretive weight.
- Tense/aspect choices and why.

### 5. Glossary Consistency

Consult `references/glossary.json` for preferred renderings of high-frequency terms. If you introduce a new preferred rendering for a key term, note it so the glossary can be updated.

Key principle: the same Greek lemma should map to the same English word across passages unless context demands otherwise. When deviating, explain why in the notes.

## Output Format

Save each translation as a Markdown file in the workspace under `translations/` named by passage (e.g., `translations/John_1_1-5.md`). Use this template:

```markdown
# [Passage Reference]

## Greek Text

[Full Greek text of the passage, one verse per line, with verse numbers]

## Token Analysis

[One table per verse]

### Verse N

| # | Token | Lemma | Morphology | Gloss |
|---|-------|-------|------------|-------|
| 1 | ... | ... | ... | ... |

## Translation

[The balanced English translation, with verse numbers inline]

## Notes

- [Note 1]
- [Note 2]

## Glossary Updates

| Lemma | Preferred Rendering | Context Note |
|-------|-------------------|--------------|
| ... | ... | ... |

---

*Greek source: Open Greek New Testament (OGNT) by Eliran Wong, CC BY-SA 4.0.*
*Based on: https://github.com/eliranwong/OpenGNT*
```

## Constraints

- Do NOT quote copyrighted English translations (NIV, ESV, NASB, etc.) unless the user explicitly provides text and asks for comparison.
- Do NOT use the Berean IT/LT/ST columns from OpenGNT — those are copyrighted.
- The TBESG glosses (Tyndale House) are open data and safe to use.
- Always include the CC BY-SA 4.0 attribution block at the bottom of each output.
- Produced translations inherit CC BY-SA 4.0 from the OGNT source text.

## Tools Available

- `exec` — run the indexer/normalizer scripts
- `read_file` / `write_file` — read verse index, write output Markdown
- `web_search` — look up lexical or contextual information via DuckDuckGo (free, no API key)
- `web_fetch` — fetch a specific URL for reference material
