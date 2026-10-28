
"""
INNEVA.E - CONFIGURABLE LOCAL ENERGY REPORT AGENT
Checkpoint 17.9D

Workflow:
1. Execute three required Python tools.
2. Generate verified numerical facts.
3. Ask the selected local Ollama model to interpret results.
4. Validate the AI interpretation, with one corrective retry.
5. Release the combined report only if checks pass.

Supported local models:
- qwen2.5:1.5b
- qwen2.5:3b

This remains a fixed three-tool workflow.
Dynamic tool selection will be developed later.
"""

import argparse
import json

from ollama import Client

from energy_tools import execute_tool
from response_validator import validate_response
from verified_facts import build_verified_facts


# ============================================================
# 1. MODEL CONFIGURATION
# ============================================================

MODEL = "qwen2.5:3b"

SUPPORTED_MODELS = (
    "qwen2.5:1.5b",
    "qwen2.5:3b",
)

SUPPORTED_MODES = (
    "development_90d",
    "full_history",
)

MAX_GENERATION_TOKENS = 420
MAX_ATTEMPTS = 2

REQUIRED_TOOLS = (
    "get_energy_overview",
    "get_data_quality",
    "forecast_next_hour",
)

client = Client()


# ============================================================
# 2. FORMAT VERIFIED TOOL VALUES
# ============================================================

def format_tool_values_for_model(value):
    """
    Keep decimal dots without thousands separators
    in the model's input.
    """

    if isinstance(value, dict):
        return {
            key: format_tool_values_for_model(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [
            format_tool_values_for_model(item)
            for item in value
        ]

    if isinstance(value, float):
        return format(value, ".2f")

    return value


# ============================================================
# 3. SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """
You are an analyst writing a short interpretation of VERIFIED PYTHON RESULTS.
Only the Python results are facts. Never explain away missing data.

NUMBER FORMATTING IS CRITICAL:
- All numeric values in the supplied JSON use a DOT (.) as the decimal separator.
- Never use commas as thousands separators. For example, write 13307.08,
  NOT 13,307.08 and NOT 1330.70.
- Copy numeric values EXACTLY from the corresponding Python tool field.
- Do not move decimal points, divide or multiply values, round values,
  change units, or substitute visually similar numbers.
- If you cannot reproduce a number exactly, OMIT that number rather than guess.
- The one-hour forecast is the precise value of predicted_demand_mw.

OUTPUT EXACTLY FOUR SECTIONS with headings on separate lines:
Historical Market Conditions
Data Quality
Demand Forecast
Limitations

Maximum 135 words TOTAL. Each section must be 1-2 sentences.
Do not repeat sentences or make broad statements about dataset completeness.

REQUIRED DATA QUALITY SENTENCE (copy this structure and fill counts from the
get_data_quality tool):
"There are X missing offshore wind observations and Y missing wholesale
prices; no wholesale prices were imputed."
X MUST equal missing_offshore_wind and Y MUST equal originally_missing_prices.

FORBIDDEN STATEMENTS (including paraphrases):
- "no missing values", "no issues with missing values", "no data gaps"
- "the dataset is complete", "all generation variables are complete"
- "missing values are not actual data gaps"
- "the data is accurate", "the data is reliable"
- "completeness or continuity ensures accuracy or reliability"
- "the forecast is live", "prices were imputed"

Distinguish uninterrupted hourly timestamps from missing measurements:
continuous timestamps DO NOT imply all measurements are present.
The renewable mean covers only hours where all three components are observed.
Price mean excludes missing observations. No imputation was performed.
Use actual dataset period and observation count from tool results.
The forecast is a historical previous-hour persistence scenario, NOT live.
The execution timestamp is not the latest measurement timestamp.
Avoid speculation about market causes, trends, and accuracy.
"""


# ============================================================
# 4. RUN THE AI AGENT
# ============================================================

def run_agent(
    user_request,
    mode="development_90d",
    model=None,
):
    """
    Execute the complete local energy report agent.

    Args:
        user_request:
            User's natural-language request.

        mode:
            development_90d or full_history.

        model:
            Optional Ollama model name.
            Defaults to the existing MODEL constant.

    Returns:
        Dictionary containing the report, validation,
        executed tools, attempt count and selected model.

    Backward compatibility:
        run_agent(request, mode=mode)
        continues to work unchanged.
    """

    selected_model = MODEL if model is None else model

    if mode not in SUPPORTED_MODES:
        raise ValueError(
            f"Unsupported dataset mode: {mode}"
        )

    if selected_model not in SUPPORTED_MODELS:
        raise ValueError(
            f"Unsupported local model: {selected_model}. "
            f"Supported models: {SUPPORTED_MODELS}"
        )

    print("=" * 65)
    print("INNEVA.E - RELIABLE ENERGY REPORT AGENT")
    print("=" * 65)
    print(f"MODEL: {selected_model}")
    print(f"DATASET MODE: {mode}")
    print(f"USER: {user_request}")

    tool_results = {}
    executed_tools = []

    # --------------------------------------------------------
    # STEP 1 - EXECUTE REQUIRED PYTHON TOOLS
    # --------------------------------------------------------

    print("\nEXECUTING REQUIRED PYTHON TOOLS")
    print("-" * 65)

    for tool_name in REQUIRED_TOOLS:

        print(f"\nRUNNING: {tool_name}")

        try:
            result = execute_tool(
                tool_name,
                mode=mode,
            )

        except Exception as error:

            print(f"TOOL ERROR: {error}")

            return {
                "status": "rejected",
                "error": str(error),
                "model": selected_model,
                "executed_tools": executed_tools,
            }

        tool_results[tool_name] = result
        executed_tools.append(tool_name)

        print(json.dumps(result, indent=2))

    # --------------------------------------------------------
    # STEP 2 - BUILD VERIFIED FACTS
    # --------------------------------------------------------

    try:

        verified_facts = build_verified_facts(
            tool_results
        )

    except Exception as error:

        print(f"\nVERIFIED FACTS ERROR: {error}")

        return {
            "status": "rejected",
            "error": str(error),
            "model": selected_model,
            "executed_tools": executed_tools,
        }

    # --------------------------------------------------------
    # STEP 3 - PREPARE AI INTERPRETATION
    # --------------------------------------------------------

    print("\nGENERATING AI INTERPRETATION")
    print("-" * 65)

    user_message = (
        f"Original user request:\n{user_request}\n\n"
        "Verified Python tool results:\n"
        f"{json.dumps(format_tool_values_for_model(tool_results), indent=2)}\n\n"
        "Write exactly four brief sections using only verified values. "
        "Use the required missing-values sentence. "
        "Do not claim the dataset has no missing values. "
        "Write numeric values with decimal dots and NO thousands separators. "
        "Copy values exactly from the JSON fields; do not move decimal points."
    )

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": user_message,
        },
    ]

    narrative = ""
    validation = None

    # --------------------------------------------------------
    # STEP 4 - GENERATE AND VALIDATE
    # --------------------------------------------------------

    for attempt in range(
        1,
        MAX_ATTEMPTS + 1,
    ):

        print(
            f"\nAI GENERATION ATTEMPT "
            f"{attempt}/{MAX_ATTEMPTS}"
        )

        try:

            response = client.chat(
                model=selected_model,
                messages=messages,
                stream=False,
                options={
                    "temperature": 0,
                    "num_ctx": 4096,
                    "num_predict": MAX_GENERATION_TOKENS,
                },
            )

        except Exception as error:

            print(f"OLLAMA ERROR: {error}")

            return {
                "status": "rejected",
                "error": str(error),
                "model": selected_model,
                "executed_tools": executed_tools,
                "attempts": attempt,
            }

        narrative = response.message.content or ""

        print("\nRESPONSE VALIDATION")
        print("-" * 65)

        validation = validate_response(
            narrative,
            tool_results,
        )

        print(json.dumps(validation, indent=2))

        if validation["status"] == "pass":
            break

        # ----------------------------------------------------
        # CORRECTIVE RETRY
        # ----------------------------------------------------

        if attempt < MAX_ATTEMPTS:

            print(
                "\nVALIDATION FAILED — "
                "REQUESTING ONE CORRECTION"
            )

            messages.append({
                "role": "assistant",
                "content": narrative,
            })

            correction = (
                "Your previous interpretation failed validation. "
                "Rewrite the ENTIRE interpretation, not just the faulty sentence. "
                "Correct these issues:\n- "
                + "\n- ".join(
                    validation.get("errors", [])
                )
                + "\nVerified missing offshore wind observations: "
                + str(
                    tool_results["get_data_quality"][
                        "missing_offshore_wind"
                    ]
                )
                + "\nVerified missing wholesale prices: "
                + str(
                    tool_results["get_data_quality"][
                        "originally_missing_prices"
                    ]
                )
                + "\nThere ARE missing values; never claim none. "
                "Do not call the dataset complete, accurate, or reliable "
                "based on continuity checks. Do not claim imputation. "
                "Preserve the four required headings, avoid repetition, "
                "and use only verified tool results. "
                "Numeric formatting: dot for decimals, no thousands separators. "
                "Copy each number exactly; never shift the decimal point. "
                "If uncertain about a number, omit it."
            )

            messages.append({
                "role": "user",
                "content": correction,
            })

    # --------------------------------------------------------
    # STEP 5 - REJECT FAILED REPORTS
    # --------------------------------------------------------

    if validation["status"] != "pass":

        print(
            "\nREPORT REJECTED AFTER MAXIMUM ATTEMPTS"
        )

        print(
            "\nAI NARRATIVE:\n" + narrative
        )

        print("\nDETECTED ISSUES:")

        for error in validation.get(
            "errors",
            [],
        ):
            print(f"- {error}")

        return {
            "status": "rejected",
            "model": selected_model,
            "validation": validation,
            "executed_tools": executed_tools,
            "attempts": MAX_ATTEMPTS,
        }

    # --------------------------------------------------------
    # STEP 6 - BUILD VERIFIED REPORT
    # --------------------------------------------------------

    final_report = (
        verified_facts
        + "\n\n"
        + "AI ANALYSIS AND INTERPRETATION\n"
        + "==============================\n"
        + narrative
    )

    print("\nFINAL REPORT")
    print("=" * 65)
    print(final_report)

    print("\nREPORT STATUS: CHECKS PASSED")

    print(
        "Verified facts are sourced from Python tools. "
        "AI interpretation has limited automated checks."
    )

    return {
        "status": "checks_passed",
        "model": selected_model,
        "report": final_report,
        "validation": validation,
        "executed_tools": executed_tools,
        "attempts": attempt,
    }


# ============================================================
# 5. COMMAND LINE INTERFACE
# ============================================================

def main():

    request = (
        "Analyze the historical electricity market, "
        "check the data quality, and generate a "
        "one-hour-ahead demand forecast. "
        "Explain the most important findings "
        "and limitations."
    )

    parser = argparse.ArgumentParser(
        description="Run local energy report agent"
    )

    parser.add_argument(
        "--mode",
        choices=SUPPORTED_MODES,
        default="development_90d",
        help="Canonical dataset coverage",
    )

    parser.add_argument(
        "--model",
        choices=SUPPORTED_MODELS,
        default=MODEL,
        help="Local Ollama model",
    )

    args = parser.parse_args()

    result = run_agent(
        request,
        mode=args.mode,
        model=args.model,
    )

    if result.get("status") != "checks_passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
