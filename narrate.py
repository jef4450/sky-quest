"""Ask a local Ollama model to describe supplied facts, then ground-check its text."""

import json

import config
from grounding_check import append_slip, check_grounding


PERSONAS = {
    "calm": "calm and reassuring",
    "coach": "encouraging, like a friendly outdoor coach",
    "precise": "clear and precise",
    "quiet": "quiet, gentle, and minimal",
}


def fallback_text(facts: dict) -> str:
    """Build a short, factual card sentence without asking a language model."""
    best = facts.get("best_window")
    if best:
        window = f"{best['start']} to {best['end']}"
    else:
        window = "the available observing window"

    positions = facts.get("positions", {})
    targets = [
        f"{name} ({position['direction']})"
        for name, position in positions.items()
        if position.get("above_horizon")
    ]
    if targets:
        return f"Your best window is {window}. Look for " + ", ".join(targets) + "."
    return f"Your best window is {window}. Step outside and look for the objects listed on your sky card."


def _ask_ollama(facts: dict, persona: str, correction: str = "") -> str:
    import ollama

    prompt = (
        f"Write 2 or 3 short, friendly sentences in a {PERSONAS[persona]} style. "
        "Use ONLY the given facts. Do not add numbers, planets, stars, or events "
        "that are not listed. Do not calculate or infer sky facts. Keep every "
        "direction and time exactly as supplied.\n"
        f"Facts:\n{json.dumps(facts, ensure_ascii=False, indent=2)}"
    )
    if correction:
        prompt += f"\nYour previous answer failed this check: {correction}. Try again using only the facts."
    response = ollama.generate(model=config.MODEL_NAME, prompt=prompt)
    return response["response"].strip()


def narrate(facts: dict, persona: str | None = None) -> str:
    """Generate, check, and if needed retry Gemma narration; otherwise use a template."""
    chosen_persona = persona or config.PERSONA
    if chosen_persona not in PERSONAS:
        raise ValueError(f"PERSONA must be one of: {', '.join(PERSONAS)}")

    try:
        text = _ask_ollama(facts, chosen_persona)
    except (ImportError, OSError, ConnectionError, TimeoutError, KeyError, ValueError) as error:
        print(f"Could not reach local Ollama ({error}). Start Ollama and check MODEL_NAME.")
        return fallback_text(facts)
    except Exception as error:
        # Ollama's SDK can surface several transport/API exception types.
        print(f"Local Ollama could not generate narration ({error}). Check Ollama and MODEL_NAME.")
        return fallback_text(facts)

    valid, reason = check_grounding(text, facts)
    if valid:
        return text

    append_slip(text, reason)
    print(f"Gemma's first answer failed the grounding check: {reason}. Retrying once.")
    try:
        retry_text = _ask_ollama(facts, chosen_persona, reason)
    except Exception as error:
        print(f"Local Ollama retry failed ({error}). Using a fact-only template.")
        return fallback_text(facts)

    valid, reason = check_grounding(retry_text, facts)
    if valid:
        return retry_text
    append_slip(retry_text, reason)
    print(f"Gemma's retry failed the grounding check: {reason}. Using a fact-only template.")
    return fallback_text(facts)
