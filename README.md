# PapyrusAI

<p align="center">
  <img src="logo.png" alt="PapyrusAI Logo" width="300">
</p>

Translating the Greek New Testament using local LLMs on consumer hardware — no cloud APIs, no GPU required. Built on OpenGNT (Open Greek New Testament). Features automated BLEU scoring, bidirectional evaluation (Greek→English + English→Greek reverse testing to detect memorization vs. true comprehension), lexicon injection (RAG), and few-shot prompting.

## Quick Start

See [docs/quickstart.md](docs/quickstart.md) for setup and usage instructions.

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com) with at least one model (e.g., `qwen2.5`, `llama3.2`)
- [OpenGNT](https://github.com/eliranwong/OpenGNT) corpus (CC BY-SA 4.0)

## Project Structure

- `scripts/` — Python pipeline (translation, evaluation, BLEU scoring, reverse eval)
- `references/` — Verse index, glossary, book number mappings
- `evaluations/` — Evaluation output reports
- `translations/` — Generated translation reports
- `docs/` — Documentation
- `SKILL.md` — Translation workflow specification

## License

Greek source text: Open Greek New Testament (OGNT) by Eliran Wong, CC BY-SA 4.0.
