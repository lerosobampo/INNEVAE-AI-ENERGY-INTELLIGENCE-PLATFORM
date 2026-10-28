
import json

from energy_tools import (
    TOOL_DESCRIPTIONS,
    execute_tool
)


# ============================================================
# INNEVA.E - FIRST AGENT LOOP
# MODULE 14 | CHECKPOINT 14.1
# ============================================================


def select_tool(user_request):
    """
    Deterministic tool selection.

    This is a learning prototype.
    A language model will replace these rules later.
    """

    request = user_request.lower()

    if any(
        word in request
        for word in ["forecast", "predict", "prediction"]
    ):
        return "forecast_next_hour"

    if any(
        word in request
        for word in ["quality", "missing", "validation"]
    ):
        return "get_data_quality"

    if any(
        word in request
        for word in [
            "overview",
            "summary",
            "market",
            "statistics",
        ]
    ):
        return "get_energy_overview"

    return None


def run_agent(user_request):
    """
    Basic request -> tool -> observation loop.
    """

    print("\n" + "=" * 65)
    print("INNEVA.E - FIRST ENERGY AGENT")
    print("=" * 65)

    print(f"\nUSER REQUEST: {user_request}")

    print("\nSTEP 1: UNDERSTAND REQUEST")
    print("-" * 65)

    selected_tool = select_tool(user_request)

    if selected_tool is None:
        return {
            "status": "unsupported_request",
            "message": (
                "No matching tool found for this request."
            ),
            "available_tools": list(
                TOOL_DESCRIPTIONS.keys()
            ),
        }

    print(f"Selected tool: {selected_tool}")

    print("\nSTEP 2: EXECUTE TOOL")
    print("-" * 65)

    try:
        observation = execute_tool(selected_tool)

    except Exception as error:
        return {
            "status": "tool_error",
            "selected_tool": selected_tool,
            "error_type": type(error).__name__,
            "message": str(error),
        }

    print("Tool execution completed.")

    print("\nSTEP 3: OBSERVE RESULT")
    print("-" * 65)

    print(
        json.dumps(
            observation,
            indent=4
        )
    )

    print("\nSTEP 4: RETURN RESPONSE")
    print("-" * 65)

    return {
        "status": "success",
        "user_request": user_request,
        "selected_tool": selected_tool,
        "observation": observation,
    }


def main():

    print("=" * 65)
    print("AVAILABLE AGENT TOOLS")
    print("=" * 65)

    for name, description in TOOL_DESCRIPTIONS.items():
        print(f"\n{name}")
        print(f"  {description}")

    requests = [
        "Give me an overview of the energy market.",
        "Check the data quality of our energy dataset.",
        "Forecast electricity demand for the next hour.",
    ]

    for request in requests:

        result = run_agent(request)

        print("\nFINAL AGENT OUTPUT")
        print("-" * 65)

        print(
            json.dumps(
                result,
                indent=4
            )
        )


if __name__ == "__main__":
    main()
