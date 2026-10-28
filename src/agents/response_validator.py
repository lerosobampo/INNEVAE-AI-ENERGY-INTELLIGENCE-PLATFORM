
"""
INNEVA.E - AI RESPONSE VALIDATOR

Checkpoint 17.9B
Validates AI-generated energy reports against deterministic tool results.

This validator is designed for historical data, not live market data.
Passing validation does not guarantee complete factual accuracy.
"""

import re
import math
from collections import Counter
from datetime import datetime, timezone


REQUIRED_TOOLS = {
    "get_energy_overview",
    "get_data_quality",
    "forecast_next_hour",
}


def detect_repetition(text, threshold=3):
    segments = re.split(r"[.!?]\s+|\n+", text)
    normalized = []

    for segment in segments:
        sentence = segment.strip().lower()
        sentence = re.sub(r"^[-*]\s+", "", sentence)

        if len(sentence) >= 40:
            normalized.append(sentence)

    counts = Counter(normalized)

    return [
        {"sentence": sentence, "count": count}
        for sentence, count in counts.items()
        if count > threshold
    ]


def parse_timestamp(value):
    if not value:
        return None

    try:
        timestamp = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )

        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        return timestamp.astimezone(timezone.utc)

    except (ValueError, TypeError, AttributeError):
        return None


def split_sentences(text):
    return re.split(r"(?<=[.!?])\s+|\n+", text)


def validate_response(response_text, tool_results):
    checks = {}
    errors = []

    if not isinstance(response_text, str):
        response_text = ""

    if not isinstance(tool_results, dict):
        tool_results = {}

    overview = tool_results.get("get_energy_overview", {})
    quality = tool_results.get("get_data_quality", {})
    forecast = tool_results.get("forecast_next_hour", {})

    for name, value in (
        ("get_energy_overview", overview),
        ("get_data_quality", quality),
        ("forecast_next_hour", forecast),
    ):
        if not isinstance(value, dict):
            errors.append(f"Invalid tool result: {name}")

    overview = overview if isinstance(overview, dict) else {}
    quality = quality if isinstance(quality, dict) else {}
    forecast = forecast if isinstance(forecast, dict) else {}

    text = response_text.lower()

    # --------------------------------------------------
    # 1. Required tools and execution statuses
    # --------------------------------------------------

    missing_tools = REQUIRED_TOOLS - set(tool_results)

    checks["required_tools_executed"] = not missing_tools

    if missing_tools:
        errors.append(
            "Missing required tools: "
            + ", ".join(sorted(missing_tools))
        )

    statuses_valid = (
        overview.get("status") == "success"
        and quality.get("status") in (
            "pass",
            "pass_with_warnings",
        )
        and forecast.get("status") == "success"
    )

    checks["tool_statuses_valid"] = statuses_valid

    if not statuses_valid:
        errors.append(
            "One or more required tools did not succeed."
        )

    # --------------------------------------------------
    # 2. Narrative presence
    # --------------------------------------------------

    checks["narrative_present"] = bool(
        response_text.strip()
    )

    if not checks["narrative_present"]:
        errors.append("AI narrative is empty.")

    # --------------------------------------------------
    # 3. Known incorrect statements
    # --------------------------------------------------

    known_errors = {
        "imputed_prices_described_as_missing": (
            r"\b\d+\s+imputed\s+prices\s+were\s+missing\b"
        ),
        "forecast_uses_imputed_prices": (
            r"(?:forecast|prediction)"
            r".{0,100}?"
            r"(?:uses|includes|based on|relies on)"
            r".{0,60}?"
            r"imputed\s+(?:wholesale\s+)?prices"
        ),
        "historical_data_guaranteed_current": (
            r"historical\s+snapshot.{0,40}"
            r"(?:ensur(?:es|ing)|guarantees)"
            r".{0,20}up.to.date"
        ),
    }

    for name, pattern in known_errors.items():
        detected = bool(re.search(pattern, text))
        checks[f"no_{name}"] = not detected

        if detected:
            errors.append(
                f"Known incorrect statement detected: {name}"
            )

    # --------------------------------------------------
    # 4. Excessive repetition
    # --------------------------------------------------

    repetitions = detect_repetition(response_text)

    checks["no_excessive_repetition"] = not repetitions

    if repetitions:
        errors.append(
            "AI narrative contains excessive repetition."
        )

    # --------------------------------------------------
    # 5. Forecast timestamps
    # --------------------------------------------------

    target = parse_timestamp(
        forecast.get("forecast_timestamp_utc")
    )

    latest_observation = parse_timestamp(
        forecast.get("latest_observation_utc")
    )

    generated_at = parse_timestamp(
        forecast.get("generated_at_utc")
    )

    timestamp_data_valid = (
        target is not None
        and latest_observation is not None
        and target > latest_observation
    )

    checks["forecast_timestamps_valid"] = (
        timestamp_data_valid
    )

    if not timestamp_data_valid:
        errors.append(
            "Forecast timestamp data is invalid."
        )

    generation_confusion = False

    if generated_at is not None:
        generation_date = (
            generated_at.strftime("%B %d, %Y").lower()
        )

        patterns = [
            r"latest observed demand.{0,100}"
            + re.escape(generation_date),

            r"latest observation.{0,100}"
            + re.escape(generation_date),
        ]

        generation_confusion = any(
            re.search(pattern, text, re.DOTALL)
            for pattern in patterns
        )

    checks["no_generation_time_confusion"] = (
        not generation_confusion
    )

    if generation_confusion:
        errors.append(
            "Forecast generation date was confused "
            "with the latest historical observation."
        )

    # --------------------------------------------------
    # 6. Dataset consistency
    # --------------------------------------------------

    modes = [
        overview.get("dataset_mode"),
        quality.get("dataset_mode"),
        forecast.get("dataset_mode"),
    ]

    mode_consistent = (
        bool(modes[0])
        and len(set(modes)) == 1
    )

    checks["dataset_modes_consistent"] = mode_consistent

    if not mode_consistent:
        errors.append(
            "Energy tools used inconsistent dataset modes."
        )

    count_consistent = (
        overview.get("observation_count")
        == quality.get("total_hours")
        == forecast.get("observation_count")
        and type(overview.get("observation_count")) is int
    )

    checks["observation_counts_consistent"] = (
        count_consistent
    )

    if not count_consistent:
        errors.append(
            "Energy tools reported inconsistent "
            "observation counts."
        )

    overview_latest = parse_timestamp(
        overview.get("last_timestamp_utc")
    )

    latest_consistent = (
        overview_latest is not None
        and overview_latest == latest_observation
    )

    checks["latest_observation_consistent"] = (
        latest_consistent
    )

    if not latest_consistent:
        errors.append(
            "Forecast latest observation differs "
            "from energy overview."
        )

    # --------------------------------------------------
    # 7. Price imputation consistency
    # --------------------------------------------------

    no_imputation = (
        overview.get("imputed_price_count") == 0
        and quality.get("imputed_price_count") == 0
        and quality.get("imputation_method") == "none"
    )

    checks["no_price_imputation"] = no_imputation

    if not no_imputation:
        errors.append(
            "Unexpected price imputation in canonical dataset."
        )

    # --------------------------------------------------
    # 8. Unsupported live-data and imputation claims
    # --------------------------------------------------

    historical_claims = (
        r"\b(?:all|every)\s+(?:wholesale\s+)?prices?"
        r"\s+(?:were|was|are|is)\s+imputed\b",

        r"\b(?:prices?|missing\s+prices?)"
        r"\s+(?:were|was|are|is)"
        r"\s+(?:filled|imputed|estimated)\b",

        r"\b(?:live|real.time)\s+"
        r"(?:market\s+)?(?:data|feed|forecast)\b",
    )

    negation_before = re.compile(
        r"\b(?:not|never|no|without|isn't|aren't|"
        r"wasn't|weren't|doesn't|don't|cannot|can't|"
        r"rather than|instead of)\b"
    )

    negation_after = re.compile(
        r"\b(?:not\s+(?:performed|used|applied|"
        r"available|live)|is\s+not\s+performed|"
        r"are\s+not\s+performed)\b"
    )

    unsupported_claim = False

    for sentence in split_sentences(text):
        for pattern in historical_claims:
            for match in re.finditer(pattern, sentence):
                prefix = sentence[
                    max(0, match.start() - 45):match.start()
                ]

                suffix = sentence[
                    match.end():match.end() + 35
                ]

                if (
                    negation_before.search(prefix)
                    or negation_after.search(suffix)
                ):
                    continue

                unsupported_claim = True
                break

            if unsupported_claim:
                break

        if unsupported_claim:
            break

    checks["no_unsupported_live_or_imputation_claims"] = (
        not unsupported_claim
    )

    if unsupported_claim:
        errors.append(
            "AI narrative claims live data or price imputation."
        )

    # --------------------------------------------------
    # 9. Offshore wind completeness
    # --------------------------------------------------

    missing_offshore = quality.get(
        "missing_offshore_wind", 0
    )

    offshore_terms = (
        r"(?:off[ -]?shore(?:\s+wind)?|"
        r"wind[ -]?off[ -]?shore)"
    )

    offshore_patterns = [
        rf"\bno\s+missing\s+"
        rf"(?:values?|observations?|data)"
        rf"\s+(?:in|for|of)\s+"
        rf"[^.\n]{{0,100}}{offshore_terms}",

        rf"{offshore_terms}[^.\n]{{0,70}}"
        rf"\b(?:no\s+missing|zero\s+missing|"
        rf"without\s+missing)\b",

        rf"\b(?:all|every)\s+[^.\n]{{0,80}}"
        rf"{offshore_terms}[^.\n]{{0,50}}"
        rf"\b(?:complete|available|present)\b",
    ]

    offshore_contradiction = (
        bool(missing_offshore)
        and any(
            re.search(pattern, text)
            for pattern in offshore_patterns
        )
    )

    if missing_offshore and re.search(
        r"\bno\s+(?:issues?|problems?)\s+with\s+"
        r"missing\s+(?:values?|data|observations?)\b",
        text,
    ):
        offshore_contradiction = True

    checks["no_offshore_completeness_contradiction"] = (
        not offshore_contradiction
    )

    if offshore_contradiction:
        errors.append(
            "Narrative incorrectly claims offshore wind "
            "has no missing observations."
        )

    # --------------------------------------------------
    # 10. Unsupported accuracy assurances
    # --------------------------------------------------

    accuracy_terms = (
        r"(?:accurate|accuracy|reliable|reliability|"
        r"trustworthy|validity)"
    )

    assurance_terms = (
        r"(?:ensur(?:e|es|ed|ing)|confirm(?:s|ed)?|"
        r"guarantee(?:s|d)?|prov(?:e|es|ed)|"
        r"establish(?:es|ed)?|verify|verified)"
    )

    quality_terms = (
        r"(?:completeness|continuity|"
        r"quality\s+checks?|data\s+checks?)"
    )

    assurance_patterns = (
        rf"{quality_terms}[^.\n]{{0,110}}"
        rf"{assurance_terms}[^.\n]{{0,85}}"
        rf"{accuracy_terms}",

        rf"{quality_terms}[^.\n]{{0,110}}"
        rf"{assurance_terms}[^.\n]{{0,85}}"
        rf"(?:data\s+is\s+)?reliable",

        r"\bdata\s+(?:is|are|was|were)\s+"
        r"(?:historical\s+and\s+)?reliable\b",
    )

    unsupported_accuracy = False

    for sentence in split_sentences(text):
        has_assurance = any(
            re.search(pattern, sentence)
            for pattern in assurance_patterns
        )

        has_negation = bool(re.search(
            r"\b(?:do(?:es)?\s+not|cannot|can't|"
            r"never|not|doesn't|don't)\b",
            sentence,
        ))

        if has_assurance and not has_negation:
            unsupported_accuracy = True
            break

    checks["no_unsupported_accuracy_assurance"] = (
        not unsupported_accuracy
    )

    if unsupported_accuracy:
        errors.append(
            "Narrative incorrectly treats completeness "
            "checks or historical data as proof of "
            "accuracy/reliability."
        )

    # --------------------------------------------------
    # 11. Numerical fidelity
    # --------------------------------------------------

    metric_specs = [
        (
            "average_demand_mw",
            overview.get("average_demand_mw"),
            [
                r"\baverage\s+(?:electricity\s+)?"
                r"(?:demand|load)\b",

                r"\b(?:demand|load)\s+"
                r"averag(?:e|ed|es)\b",
            ],
        ),
        (
            "peak_demand_mw",
            overview.get("peak_demand_mw"),
            [
                r"\bpeak\s+(?:electricity\s+)?"
                r"(?:demand|load)\b",

                r"\b(?:demand|load)\s+peak\b",

                r"\bpeak\s+of\b",
            ],
        ),
        (
            "average_renewable_generation_mw",
            overview.get("average_renewable_generation_mw"),
            [
                r"\b(?:renewable\s+(?:energy\s+)?"
                r"(?:generation|sources?)|renewables?)"
                r"\s+(?:averag(?:e|ed|es)|"
                r"provided|produced|contributed)\b",

                r"\baverage\s+(?:total\s+)?"
                r"renewable\s+generation\b",
            ],
        ),
        (
            "predicted_demand_mw",
            forecast.get("predicted_demand_mw"),
            [
                r"\b(?:demand\s+)?forecast\s+"
                r"(?:for\s+the\s+next\s+hour\s+)?"
                r"(?:is|of|predicts|projects)\b",

                r"\b(?:predicted|forecast(?:ed)?)"
                r"\s+demand\s+(?:is|of|at)\b",

                r"\b(?:forecast|prediction)\s+"
                r"for\s+the\s+next\s+hour\s+is\b",
            ],
        ),
    ]

    numeric_errors = []

    mw_number = re.compile(
        r"(?<![\w.])(-?\d[\d,]*(?:\.\d+)?)\s*MW\b",
        re.I,
    )

    for metric_name, expected, anchors in metric_specs:
        if (
            not isinstance(expected, (int, float))
            or not math.isfinite(expected)
        ):
            numeric_errors.append(
                f"Missing trusted value for {metric_name}."
            )
            continue

        for sentence in split_sentences(response_text):
            for anchor in anchors:
                for match in re.finditer(
                    anchor, sentence, re.I
                ):
                    snippet = sentence[
                        match.end():match.end() + 125
                    ]

                    value_match = mw_number.search(snippet)

                    if value_match is None:
                        continue

                    observed = float(
                        value_match.group(1).replace(",", "")
                    )

                    if not math.isclose(
                        observed,
                        float(expected),
                        abs_tol=0.02,
                        rel_tol=0,
                    ):
                        numeric_errors.append(
                            f"AI numeric mismatch for {metric_name}: "
                            f"narrative {observed:,.2f} MW; "
                            f"verified {expected:,.2f} MW."
                        )

    checks["narrative_numeric_values_match_tools"] = (
        not numeric_errors
    )

    errors.extend(dict.fromkeys(numeric_errors))

    # --------------------------------------------------
    # 12. Thousands separator validation
    # --------------------------------------------------

    malformed = []

    number_tokens = re.finditer(
        r"(?<![\w.,])[-+]?\d+(?:,\d+)+(?:\.\d+)?"
        r"(?![\w.,])",
        response_text,
    )

    for token in number_tokens:
        raw = token.group(0)

        integer_part = raw.lstrip("+-").split(".")[0]
        groups = integer_part.split(",")

        valid_grouping = (
            1 <= len(groups[0]) <= 3
            and all(len(group) == 3 for group in groups[1:])
        )

        if not valid_grouping:
            malformed.append(raw)

    checks["valid_numeric_grouping"] = not malformed

    if malformed:
        errors.append(
            "Malformed thousands separators in AI narrative: "
            + ", ".join(dict.fromkeys(malformed))
        )

    # --------------------------------------------------
    # 13. Observed-hour count validation
    #
    # CHECKPOINT 17.9B FIX
    #
    # Correctly detects:
    # "100 hours with observed wholesale prices"
    #
    # The number is immediately before the word
    # "hours", which is part of the matched anchor.
    # --------------------------------------------------

    count_specs = [
        (
            "renewable_complete_hours",
            overview.get("renewable_complete_hours"),
            [
                r"hours?\s+(?:of|with)\s+complete\s+"
                r"(?:renewable|generation|data)",

                r"complete\s+(?:renewable|generation|data)"
                r"\s+hours?",
            ],
        ),
        (
            "observed_price_hours",
            overview.get("observed_price_hours"),
            [
                r"hours?\s+(?:of|with)\s+observed\s+"
                r"(?:wholesale\s+)?prices?",

                r"observed\s+(?:wholesale\s+)?prices?"
                r"\s+(?:for\s+)?hours?",
            ],
        ),
    ]

    count_errors = []

    for name, expected, anchors in count_specs:
        if not isinstance(expected, int):
            continue

        for sentence in split_sentences(response_text):
            for anchor in anchors:
                for match in re.finditer(
                    anchor, sentence, re.I
                ):
                    before = sentence[
                        max(0, match.start() - 55):
                        match.start()
                    ]

                    after = sentence[
                        match.end():
                        match.end() + 55
                    ]

                    nearby = None

                    # Fix: detect a number directly before
                    # the anchor "hours with observed prices".
                    if re.match(
                        r"hours?\b",
                        match.group(0),
                        re.I,
                    ):
                        nearby = re.search(
                            r"\b(\d[\d,]*)\s+$",
                            before,
                        )

                    # Also support:
                    # "2,156 hours ... observed prices"
                    if nearby is None:
                        prior_counts = list(re.finditer(
                            r"\b(\d[\d,]*)\s+hours?\b",
                            before,
                            re.I,
                        ))

                        if prior_counts:
                            nearby = prior_counts[-1]

                    # Also support numbers following the anchor.
                    if nearby is None:
                        nearby = re.search(
                            r"\b(\d[\d,]*)\s+hours?\b",
                            after,
                            re.I,
                        )

                    if nearby is not None:
                        observed = int(
                            nearby.group(1).replace(",", "")
                        )

                        if observed != expected:
                            count_errors.append(
                                f"AI count mismatch for {name}: "
                                f"narrative {observed}; "
                                f"verified {expected}."
                            )

    checks["observed_hour_counts_match_tools"] = (
        not count_errors
    )

    errors.extend(dict.fromkeys(count_errors))

    # --------------------------------------------------
    # 14. Demand calculation methodology
    # --------------------------------------------------

    demand_price_confusion = bool(
        re.search(
            r"\b(?:average|mean)\s+"
            r"(?:electricity\s+)?(?:demand|load)\b"
            r"[^.\n;]{0,110}"
            r"\b(?:calculat(?:ed|ion)|"
            r"comput(?:ed|ation)|based)\b"
            r"[^.\n;]{0,100}"
            r"\b(?:wholesale\s+)?prices?\b",
            response_text,
            re.I,
        )
        or re.search(
            r"\b(?:average|mean)\s+"
            r"(?:electricity\s+)?(?:demand|load)\b"
            r"[^.\n;]{0,110}"
            r"\busing\b"
            r"[^.\n;]{0,100}"
            r"\b(?:wholesale\s+)?prices?\b",
            response_text,
            re.I,
        )
    )

    checks["demand_not_calculated_from_prices"] = (
        not demand_price_confusion
    )

    if demand_price_confusion:
        errors.append(
            "AI methodology error: average demand is "
            "derived from actual_load_mw, not wholesale prices."
        )

    # --------------------------------------------------
    # 15. Data quality does not prove source accuracy
    # --------------------------------------------------

    quality_accuracy_pattern = re.compile(
        r"\b(?:completeness|continuity|"
        r"missing\s+values?|data\s+quality)\b"
        r"[^.\n]{0,120}"
        r"\b(?:ensur(?:e|es|ed|ing)|"
        r"guarantee(?:s|d)?|prov(?:e|es|ed)|"
        r"establish(?:es|ed)?|confirm(?:s|ed)?)\b"
        r"[^.\n]{0,80}"
        r"\b(?:accuracy|accurate|"
        r"reliability|reliable)\b",
        re.I,
    )

    quality_accuracy_confusion = False

    for sentence in split_sentences(response_text):
        has_overclaim = bool(
            quality_accuracy_pattern.search(sentence)
        )

        has_negation = bool(re.search(
            r"\b(?:not|never|cannot|can't|"
            r"doesn't|don't|do not|does not)\b",
            sentence,
            re.I,
        ))

        if has_overclaim and not has_negation:
            quality_accuracy_confusion = True
            break

    checks["no_quality_accuracy_overclaim_extended"] = (
        not quality_accuracy_confusion
    )

    if quality_accuracy_confusion:
        errors.append(
            "AI methodology error: completeness/continuity "
            "cannot prove source accuracy."
        )

    # --------------------------------------------------
    # 16. Final result
    # --------------------------------------------------

    return {
        "status": "pass" if not errors else "fail",
        "checks": checks,
        "errors": errors,
        "repeated_sentences": repetitions,
        "warning": (
            "This validator checks selected errors and "
            "timestamp consistency. Passing does not "
            "guarantee complete factual accuracy."
        ),
    }
