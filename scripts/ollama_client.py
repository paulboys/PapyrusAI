#!/usr/bin/env python3
"""Thin wrapper around Ollama's /api/chat endpoint.

Uses only stdlib (urllib, json). No pip dependencies required.

Usage:
    from ollama_client import chat
    response_text = chat("qwen2.5", "You are a translator.", "Translate this.")
"""

import json
import urllib.request
import urllib.error

OLLAMA_BASE = "http://localhost:11434"


def chat(model, system_prompt, user_prompt, temperature=0.7, num_ctx=8192,
         num_predict=4096, timeout=3600):
    """Send a chat request to Ollama and return the assistant's response text.

    Uses streaming mode so the socket timeout applies per-chunk rather than
    to the entire generation, avoiding timeouts on slow hardware.

    Args:
        model: Ollama model tag, e.g. "qwen2.5"
        system_prompt: System message content
        user_prompt: User message content
        temperature: Sampling temperature
        num_ctx: Context window size in tokens
        num_predict: Max tokens to generate
        timeout: Per-chunk socket timeout in seconds

    Returns:
        The assistant's response content as a string.

    Raises:
        ConnectionError: If Ollama is not reachable.
        RuntimeError: On HTTP or API errors.
    """
    url = f"{OLLAMA_BASE}/api/chat"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": True,
        "options": {
            "temperature": temperature,
            "num_ctx": num_ctx,
            "num_predict": num_predict,
        },
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                headers={"Content-Type": "application/json"})

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            chunks = []
            for line in resp:
                line = line.strip()
                if not line:
                    continue
                chunk = json.loads(line.decode("utf-8"))
                token = chunk.get("message", {}).get("content", "")
                if token:
                    chunks.append(token)
                if chunk.get("done", False):
                    break
    except urllib.error.URLError as e:
        raise ConnectionError(
            f"Cannot reach Ollama at {OLLAMA_BASE}. Is it running? ({e})"
        ) from e
    except urllib.error.HTTPError as e:
        raise RuntimeError(
            f"Ollama returned HTTP {e.code}: {e.read().decode('utf-8', errors='replace')}"
        ) from e

    content = "".join(chunks)
    if not content:
        raise RuntimeError("Empty response from Ollama.")

    return content


def list_models(timeout=10):
    """Return list of locally available model tags.

    Returns:
        List of model name strings, e.g. ["qwen2.5:latest", "llama3.2:latest"]
    """
    url = f"{OLLAMA_BASE}/api/tags"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError):
        return []
    return [m["name"] for m in body.get("models", [])]
