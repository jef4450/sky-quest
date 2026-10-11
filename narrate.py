"""Ask a local Ollama model to describe supplied facts and verify its response."""

import json
from typing import Any

import config
from grounding_check import append_slip, check_grounding


OLLAMA_TIMEOUT_SECONDS = 60.0
PERSONAS = {
    "calm": "calm and reassuring",
    "coach": "encouraging, like a friendly outdoor coach",
    "precise": "clear and precise",
    "quiet": "quiet, gentle, and minimal",
}


def fallback_text(facts: dict) -> str:
    """Build narration only from fields present in the supplied facts."""
    sentences = []
    best = facts.get("best_window")
    if best and best.get("start") and best.get("end"):
        sentences.append(f"Best window: {best['start']} to {best['end']}.")

    for name, position in facts.get("positions", {}).items():
        details = [
            value for value in (
                position.get("height"),
                position.get("direction"),
                "above the horizon" if position.get("above_horizon") else "below the horizon",
            ) if value
        ]
        if details:
            sentences.append(f"{name}: {', '.join(details)}.")

    if facts.get("moon_phase"):
        sentences.append(f"Moon phase: {facts['moon_phase']}.")
    for key, label in (
        ("moonrise", "Moonrise"),
        ("moonset", "Moonset"),
        ("sunset", "Sunset"),
        ("dark_time", "Dark time"),
    ):
        if facts.get(key):
            sentences.append(f"{label}: {facts[key]}.")

    for iss_pass in facts.get("iss_passes", []):
        pass_details = [
            str(iss_pass[key])
            for key in (
                "start", "appears_from", "disappears_toward",
                "duration_minutes", "peak_altitude_degrees",
            )
            if iss_pass.get(key) is not None
        ]
        if pass_details:
            sentences.append("ISS pass: " + ", ".join(pass_details) + ".")

    if not sentences:
        return "No supplied sky facts are available."
    return " ".join(sentences)


def _ask_ollama(facts: dict, persona: str, correction: str = "") -> str:
    import ollama

    prompt = (
        f"Write 2 or 3 short, friendly sentences in a {PERSONAS[persona]} style. "
        "Use ONLY the given facts. Do not add numbers, celestial objects, weather, "
        "directions, times, or events that are not listed. Do not calculate or "
        "infer sky facts. Keep every direction and time exactly as supplied.\n"
        f"Facts:\n{json.dumps(facts, ensure_ascii=False, indent=2)}"
    )
    if correction:
        prompt += (
            f"\nYour previous answer failed this check: {correction}. "
            "Try again using only the facts."
        )

    client = ollama.Client(timeout=OLLAMA_TIMEOUT_SECONDS)
    try:
        response = client.generate(model=config.MODEL_NAME, prompt=prompt)
    finally:
        client.close()
    if isinstance(response, dict):
        return str(response.get("response", "")).strip()
    return str(response.response).strip()


def _model_error_details(error: Exception) -> tuple[str, str]:
    """Classify common Ollama connection, timeout, and missing-model failures."""
    if isinstance(error, ImportError):
        return (
            "dependency_unavailable",
            "The Ollama Python package is not installed. Install project requirements.",
        )

    try:
        import ollama
        import httpx
    except ImportError:
        return "model_error", str(error)

    if isinstance(error, ollama.ResponseError):
        message = str(getattr(error, "error", error))
        if getattr(error, "status_code", None) == 404 or "model" in message.lower() and "not found" in message.lower():
            return (
                "model_unavailable",
                f"Model '{config.MODEL_NAME}' is not available. Download it with: ollama pull {config.MODEL_NAME}",
            )
        return "ollama_response_error", message
    if isinstance(error, httpx.ConnectError):
        return (
            "ollama_not_running",
            "Could not connect to Ollama. Start the Ollama app or service, then try again.",
        )
    if isinstance(error, httpx.TimeoutException):
        return (
            "ollama_timeout",
            f"Ollama did not respond within {OLLAMA_TIMEOUT_SECONDS:g} seconds. Try again when the model is ready.",
        )
    return "narration_error", str(error)


def _log_failure(
    text: str,
    reason: str,
    persona: str,
    failure_type: str,
) -> None:
    append_slip(
        text,
        reason,
        persona=persona,
        failure_type=failure_type,
    )


def _fact_only_fallback(
    facts: dict,
    persona: str,
    metadata: dict[str, Any],
) -> str:
    """Return checked prose, or the original facts as JSON if labels do not validate."""
    fallback = fallback_text(facts)
    passed, reason = check_grounding(fallback, facts)
    if passed:
        return fallback

    metadata["failure_reasons"].append(f"Fact-only fallback check failed: {reason}")
    _log_failure(fallback, reason, persona, "fallback_grounding_failure")
    return json.dumps(facts, ensure_ascii=False)


def narrate_with_metadata(
    facts: dict,
    persona: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Return narration and diagnostics while keeping `narrate()` string-compatible."""
    chosen_persona = persona or config.PERSONA
    if chosen_persona not in PERSONAS:
        raise ValueError(f"PERSONA must be one of: {', '.join(PERSONAS)}")

    metadata: dict[str, Any] = {
        "attempts_used": 0,
        "passed": False,
        "fell_back": False,
        "failure_reasons": [],
    }

    for attempt in range(2):
        metadata["attempts_used"] += 1
        try:
            text = _ask_ollama(
                facts,
                chosen_persona,
                metadata["failure_reasons"][-1] if attempt else "",
            )
        except Exception as error:
            failure_type, reason = _model_error_details(error)
            metadata["failure_reasons"].append(reason)
            metadata["fell_back"] = True
            _log_failure(str(error), reason, chosen_persona, failure_type)
            if failure_type == "model_unavailable":
                print(f"Sky Quest cannot find the local model. {reason}")
            elif failure_type == "ollama_not_running":
                print(f"Sky Quest cannot reach Ollama. {reason}")
            elif failure_type == "ollama_timeout":
                print(f"Sky Quest's Ollama request timed out. {reason}")
            elif failure_type == "dependency_unavailable":
                print(f"Sky Quest cannot load Ollama. {reason}")
            else:
                print(f"Sky Quest narration error: {reason}")
            return _fact_only_fallback(facts, chosen_persona, metadata), metadata

        passed, reason = check_grounding(text, facts)
        if passed:
            metadata["passed"] = True
            return text, metadata

        metadata["failure_reasons"].append(reason)
        _log_failure(text, reason, chosen_persona, "grounding_failure")
        if attempt == 0:
            print(f"Gemma's first answer failed the grounding check: {reason}. Retrying once.")
        else:
            print(f"Gemma's retry failed the grounding check: {reason}. Using a fact-only template.")

    metadata["fell_back"] = True
    return _fact_only_fallback(facts, chosen_persona, metadata), metadata


def narrate(facts: dict, persona: str | None = None) -> str:
    """Return narration as a string for compatibility with existing callers."""
    text, _ = narrate_with_metadata(facts, persona)
    return text
