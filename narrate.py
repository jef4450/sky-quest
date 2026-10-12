"""Ask a local Ollama model to describe supplied facts and verify its response."""

import json
import re
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


def fallback_text(
    facts: dict,
    sentence_count: int | None = None,
    required_fact: str | None = None,
) -> str:
    """Build narration only from fields present in the supplied facts."""
    sentences = []
    if facts.get("narration_line"):
        sentences.append(str(facts["narration_line"]))
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
    if sentence_count is not None:
        if required_fact:
            matching = [
                sentence for sentence in sentences
                if required_fact.casefold() in sentence.casefold()
            ]
            remainder = [sentence for sentence in sentences if sentence not in matching]
            sentences = matching + remainder
        sentences = sentences[:sentence_count]
    return " ".join(sentences)


def _ask_ollama(
    facts: dict,
    persona: str,
    correction: str = "",
    sentence_count: int | None = None,
    required_fact: str | None = None,
    deterministic: bool = False,
) -> str:
    import ollama

    prompt = (
        (
            f"Write exactly {sentence_count} short, friendly "
            f"{'sentence' if sentence_count == 1 else 'sentences'}"
            if sentence_count is not None
            else "Write 2 or 3 short, friendly sentences"
        )
        + f" in a {PERSONAS[persona]} style. "
        "Use ONLY the given facts. Do not add numbers, celestial objects, weather, "
        "directions, times, or events that are not listed. Do not calculate or "
        "infer sky facts. Keep every direction and time exactly as supplied.\n"
        f"Facts:\n{json.dumps(facts, ensure_ascii=False, indent=2)}"
    )
    if required_fact:
        prompt += f"\nInclude this supplied fact: {required_fact}."
    if correction:
        prompt += (
            f"\nYour previous answer failed this check: {correction}. "
            "Try again using only the facts."
        )

    client = ollama.Client(timeout=OLLAMA_TIMEOUT_SECONDS)
    try:
        generation_options = (
            {"temperature": 0, "seed": 42} if deterministic else None
        )
        if generation_options is not None:
            response = client.generate(
                model=config.MODEL_NAME,
                prompt=prompt,
                options=generation_options,
            )
        else:
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
    sentence_count: int | None,
    required_fact: str | None,
) -> str:
    """Return checked prose, or the original facts as JSON if labels do not validate."""
    fallback = fallback_text(facts, sentence_count, required_fact)
    passed, reason = check_grounding(fallback, facts)
    if passed:
        return fallback

    metadata["failure_reasons"].append(f"Fact-only fallback check failed: {reason}")
    _log_failure(fallback, reason, persona, "fallback_grounding_failure")
    return json.dumps(facts, ensure_ascii=False)


def narrate_with_metadata(
    facts: dict,
    persona: str | None = None,
    *,
    sentence_count: int | None = None,
    validate_sentence_count: bool = False,
    required_fact: str | None = None,
    deterministic: bool = False,
) -> tuple[str, dict[str, Any]]:
    """Return narration and diagnostics while keeping `narrate()` string-compatible."""
    chosen_persona = persona or config.PERSONA
    if chosen_persona not in PERSONAS:
        raise ValueError(f"PERSONA must be one of: {', '.join(PERSONAS)}")
    if sentence_count is not None and sentence_count < 1:
        raise ValueError("sentence_count must be at least one.")
    if validate_sentence_count and sentence_count is None:
        raise ValueError("sentence_count is required when validating sentence count.")

    metadata: dict[str, Any] = {
        "attempts_used": 0,
        "passed": False,
        "fell_back": False,
        "failure_reasons": [],
    }

    for attempt in range(2):
        metadata["attempts_used"] += 1
        try:
            correction = metadata["failure_reasons"][-1] if attempt else ""
            if (
                sentence_count is None
                and required_fact is None
                and not deterministic
            ):
                text = _ask_ollama(facts, chosen_persona, correction)
            else:
                request_options = {}
                if sentence_count is not None:
                    request_options["sentence_count"] = sentence_count
                if required_fact is not None:
                    request_options["required_fact"] = required_fact
                if deterministic:
                    request_options["deterministic"] = True
                text = _ask_ollama(
                    facts, chosen_persona, correction, **request_options
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
            return _fact_only_fallback(
                facts,
                chosen_persona,
                metadata,
                sentence_count if validate_sentence_count else None,
                required_fact,
            ), metadata

        passed, reason = check_grounding(text, facts)
        if passed and required_fact and required_fact.casefold() not in text.casefold():
            passed = False
            reason = f"Narration did not include the supplied fact: {required_fact}."
        if passed and validate_sentence_count:
            sentence_total = len(
                [
                    item
                    for item in re.split(r"(?<=[.!?])\s+", text.strip())
                    if item.strip()
                ]
            )
            if sentence_total != sentence_count:
                passed = False
                reason = (
                    f"Narration has {sentence_total} sentences; "
                    f"the card needs exactly {sentence_count}."
                )
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
    return _fact_only_fallback(
        facts,
        chosen_persona,
        metadata,
        sentence_count if validate_sentence_count else None,
        required_fact,
    ), metadata


def narrate(
    facts: dict,
    persona: str | None = None,
    *,
    sentence_count: int | None = None,
    validate_sentence_count: bool = False,
    required_fact: str | None = None,
    deterministic: bool = False,
) -> str:
    """Return narration as a string for compatibility with existing callers."""
    text, _ = narrate_with_metadata(
        facts,
        persona,
        sentence_count=sentence_count,
        validate_sentence_count=validate_sentence_count,
        required_fact=required_fact,
        deterministic=deterministic,
    )
    return text
