"""
ollama_client.py

Single place that talks to a local Ollama server. Both concept_segmenter.py
and svg_generator.py call through here so they share:

  - one consistent POST shape (/api/generate, non-streaming)
  - one consistent error message when Ollama isn't running (the #1
    support issue: "why did it fail" -> "because Ollama isn't started")
  - a RETRY-WITH-CORRECTION loop: when the model's output fails
    validation (bad JSON, bad SVG), we re-prompt it WITH its bad
    answer and what was wrong with it, up to OLLAMA_MAX_REPAIR_ATTEMPTS
    times. Local models frequently wrap output in markdown fences or
    add chatter despite instructions; a corrective nudge fixes most of
    those cases on the second try, which is far better UX than failing
    the whole dd-block.

No cloud APIs here, ever — Ollama host comes from config.py and defaults
to localhost.
"""

from __future__ import annotations

from typing import Callable

import requests

import config


def generate(
    prompt: str,
    *,
    temperature: float = 0.4,
    model: str | None = None,
) -> str:
    """
    One-shot generation call to Ollama. Returns the raw response text.

    Raises requests.RequestException (subclass, e.g. ConnectionError)
    if Ollama is unreachable — callers decide whether that's fatal.
    """
    response = requests.post(
        f"{config.OLLAMA_HOST}/api/generate",
        json={
            "model": model or config.OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        },
        timeout=config.OLLAMA_REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json().get("response", "")


def generate_validated(
    prompt: str,
    validator: Callable[[str], object],
    *,
    temperature: float = 0.4,
    model: str | None = None,
    repair_instruction: str = (
        "Your previous response was not in the required format. "
        "Respond again with ONLY the requested output — no explanation, "
        "no markdown code fences, no extra text before or after."
    ),
    on_retry: Callable[[int, str], None] | None = None,
) -> object:
    """
    Generate with validation + retry-with-correction.

    validator(raw_text) must either:
      - return the parsed/validated object (any type), or
      - raise ValueError with a short human-readable reason.

    Flow:
      1. Call Ollama with `prompt`.
      2. Run validator. Success -> return the validated object.
      3. On ValueError: re-prompt with the original prompt PLUS the bad
         answer and the validator's reason, up to
         config.OLLAMA_MAX_REPAIR_ATTEMPTS more times.
      4. Still failing -> raise ValueError with the last raw output
         included, so the caller can log something actionable.

    on_retry(attempt_number, reason) is an optional logging hook.

    Why not use Ollama's chat API with multi-turn history? The plain
    generate API is stateless, so we simply re-send everything each
    attempt — one less moving part, identical result.
    """
    current_prompt = prompt
    last_raw = ""
    last_reason = ""

    total_attempts = 1 + max(0, config.OLLAMA_MAX_REPAIR_ATTEMPTS)
    for attempt in range(1, total_attempts + 1):
        raw = generate(current_prompt, temperature=temperature, model=model)
        last_raw = raw
        try:
            return validator(raw)
        except ValueError as exc:
            last_reason = str(exc)
            if attempt >= total_attempts:
                break
            if on_retry is not None:
                on_retry(attempt, last_reason)
            current_prompt = (
                f"{prompt}\n\n"
                f"---\n"
                f"YOUR PREVIOUS ATTEMPT (rejected): {raw[:2000]}\n"
                f"REASON IT WAS REJECTED: {last_reason}\n"
                f"---\n"
                f"{repair_instruction}"
            )

    raise ValueError(
        f"Ollama output failed validation after {total_attempts} attempt(s). "
        f"Last rejection reason: {last_reason}\n"
        f"Last raw output (truncated):\n{last_raw[:2000]}"
    )
