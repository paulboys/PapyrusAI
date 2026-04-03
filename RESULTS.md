# Evaluation Results: Jude 1:12–13

**Passage:** Jude 1:12–13 — a notoriously difficult text featuring rare Greek vocabulary (σπιλάδες, νεφέλαι ἄνυδροι) and dense metaphorical imagery.

**Models:** `qwen2.5` (4.7 GB) vs `llama3.2` (2.0 GB), both running locally via Ollama on CPU-only consumer hardware (8 GB RAM).

**Methodology:** Bidirectional evaluation — forward (Greek→English) and reverse (English→Greek) across three difficulty tiers — to test both translation quality and whether models truly comprehend Greek or are merely pattern-matching from training data.

---

## Forward Evaluation: Greek → English

Both models score BLEU-4 = 0.000, which is expected for a single-reference evaluation of a stylistically free translation (4-gram matching collapses). The sub-score breakdown is more informative:

| Model | BLEU-4 | Unigram | Bigram | Len Ratio | Time |
|-------|--------|---------|--------|-----------|------|
| qwen2.5 | 0.000 | 0.405 | 0.049 | 0.79 | 2714s |
| llama3.2 | 0.000 | 0.239 | 0.000 | 1.34 | 934s |

**Winner: qwen2.5** — nearly double the unigram overlap. Qualitatively the gap is even larger:

- **qwen2.5** stays close to the Greek. It renders σπιλάδες as "reefs" (the correct literal reading), preserves "waterless clouds driven by winds," "autumnal unfruitful trees uprooted twice," and "wandering stars kept in darkness for an age." Compact, accurate, no hallucinations.

- **llama3.2** drifts into paraphrase and fabrication. It adds "unrepentant ones," "have no concern for the holy Spirit," "foaming up to destroy souls," and "kept captive by the chains of darkness" — none of these phrases appear in the Greek. The Notes section also quotes a Greek phrase (ἐγείρουν τὰς ἑαυτῶν αἰσχύνας) that is **not in the actual text** — a hallucinated citation.

---

## Reverse Evaluation: English → Greek

Same 5 non-famous verses across all tiers (seed=99), so scores are directly comparable.

| Tier | Hints Given | qwen2.5 Exact | qwen2.5 Acc-Strip | llama3.2 Exact | llama3.2 Acc-Strip | qwen2.5 Edit | llama3.2 Edit |
|------|-------------|---------------|-------------------|----------------|-------------------|-------------|--------------|
| 1 | gloss + morph + lemma | 20.5% | 38.6% | 20.5% | 39.8% | 2.17 | 2.12 |
| 2 | gloss + morph | 9.6% | 15.7% | 7.2% | 13.3% | 4.11 | 5.04 |
| 3 | gloss only | 13.3% | 16.9% | 0.0% | 1.2% | 4.48 | 5.45 |

### Winner by Tier

- **Tier 1: Dead heat.** Both score 20.5% exact; llama3.2 marginally ahead on accent-stripped and edit distance (39.8% vs 38.6%, 2.12 vs 2.17).
- **Tier 2: qwen2.5 wins.** Edge is modest but consistent across all metrics.
- **Tier 3: qwen2.5 wins decisively.** llama3.2 collapses to 0.0% exact and 1.2% accent-stripped — effectively random noise. qwen2.5 retains 13.3% exact and 16.9% accent-stripped.

---

## Score Degradation: Tier 1 → Tier 3

| Model | T1 Exact | T2 Exact | T3 Exact | Drop T1→T3 | T1 Acc-Strip | T3 Acc-Strip | Drop |
|-------|----------|----------|----------|------------|-------------|-------------|------|
| qwen2.5 | 20.5% | 9.6% | 13.3% | −7.2pp | 38.6% | 16.9% | −21.7pp |
| llama3.2 | 20.5% | 7.2% | 0.0% | −20.5pp | 39.8% | 1.2% | −38.6pp |

qwen2.5 loses ~22pp on accent-stripped as hints are removed. llama3.2 loses ~39pp — a near-total collapse.

The qwen2.5 T3 exact (13.3%) slightly exceeding T2 exact (9.6%) is explained by a specific verse (43.10.11): without morphology codes confusing it, qwen2.5 correctly produced several high-frequency forms (εἰμι, ὁ, καλός) that it had gotten wrong in Tier 2 by second-guessing itself with morphological constraints.

---

## Memorization Analysis

The classical memorization signature is: **strong forward, weak reverse** — the model has memorized translations but cannot reconstruct Greek forms.

| Model | Forward (Unigram BLEU) | Reverse T1 (Acc-Strip) | Asymmetry |
|-------|----------------------|----------------------|-----------|
| qwen2.5 | 40.5% | 38.6% | Moderate — forward slightly better |
| llama3.2 | 23.9% | 39.8% | **Inverted** — reverse T1 exceeds forward |

**qwen2.5** shows a normal gradient: good forward, decent reverse at T1, graceful degradation. No strong memorization signal. The model appears to have internalized some Greek morphological patterns.

**llama3.2** shows an inverted pattern. Its forward translation is poor (23.9% unigram) yet its T1 reverse matches qwen2.5. This suggests llama3.2 is **not** memorizing translations — rather, it exploits the lemma hints in Tier 1 to reconstruct surface forms (lemma → inflection is a mechanical step it can sometimes perform), but when lemmas are removed at Tier 3, it has no independent generation capability. The T3 collapse to 0% exact confirms: **llama3.2 has essentially no retained knowledge of Greek inflected forms independent of structural scaffolding.**

### Evidence of llama3.2 Disorientation at Lower Tiers

- **Tier 2:** outputs "πástωρ" (a Latin/English transliteration) for ποιμήν
- **Tier 3:** outputs "σcribesiς" (mixed Latin/Greek hallucination) for πάντες
- **Tier 3:** repeatedly outputs τὸν/τὸ as a default filler for nearly every token type
- **Tier 3:** produces multiple-choice responses ("ἐν / μεθά / παρὰ") indicating it cannot commit to a form

---

## Overall Verdict

| Dimension | Winner | Notes |
|-----------|--------|-------|
| Forward translation accuracy | **qwen2.5** | 41% vs 24% unigram; no hallucinated content |
| Forward faithfulness | **qwen2.5** | llama3.2 adds fabricated phrases and a false Greek citation |
| Reverse Tier 1 | Tie | Within noise |
| Reverse Tier 2 | **qwen2.5** | Modest margin |
| Reverse Tier 3 | **qwen2.5** | llama3.2 goes to 0% — complete failure |
| Inference speed | **llama3.2** | ~3–5× faster (2 GB vs 4.7 GB model) |
| Memorization risk | **qwen2.5** cleaner | llama3.2 leans on lemma scaffolding, collapses without it |

**qwen2.5 is the better Greek model in both directions.** Its advantages compound: better forward quality, more graceful reverse degradation, and no evidence of lemma-dependency as a crutch. llama3.2's only advantage is speed — which is substantial (3–5×), but irrelevant if the Greek outputs are unreliable at Tier 3.

---

*Evaluation completed in 2h 4m 28s on CPU-only hardware (8 GB RAM). Greek source: Open Greek New Testament (OGNT) by Eliran Wong, CC BY-SA 4.0.*
