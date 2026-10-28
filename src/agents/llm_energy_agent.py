
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from energy_tools import (
    TOOL_DESCRIPTIONS,
    execute_tool,
)


# ============================================================
# INNEVA.E - LLM ENERGY INTELLIGENCE AGENT
# MODULE 14 | CHECKPOINT 14.2
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(PROJECT_ROOT / ".env")

MODEL_NAME = os.getenv(
    "OPENAI_MODEL",
    "gpt-4.1-mini"
)

MAX_TOOL_ROUNDS = 5

SYSTEM_INSTRUCTIONS = """
You are the INNEVA.E Energy Intelligence Agent.

Your purpose is to analyze historical electricity market data
using the tools provided by the application.

Rules:

1. Use tools when answering questions that require numerical
   information from the energy database.

2. Never invent energy statistics or forecasting results.

3. The available dataset covers September 2026.

4. The dataset is a historical snapshot, not a live feed.

5. The forecast tool generates a one-hour-ahead prediction
   immediately after the last available historical observation.

6. Never describe this historical forecast as a current
   or real-time forecast.

7. If the user asks about data quality, use the data quality tool.

8. When multiple tools are needed, request them as appropriate.

9. Distinguish observed values, forecasts, and interpretations.

10. The previous-hour persistence model was the strongest
    method in our September evaluation, but its accuracy
    has not been established across other months.

11. Explain limitations clearly and concisely.

12. Do not claim that missing values have been corrected
    unless a tool explicitly confirms this.

13. Do not attempt to execute arbitrary code or access
    unregistered tools.
"""


# ------------------------------------------------------------
# TOOL DEFINITIONS
# ------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "name": "get_energy_overview",
        "description": TOOL_DESCRIPTIONS[
            "get_energy_overview"
        ],
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_data_quality",
        "description": TOOL_DESCRIPTIONS[
            "get_data_quality"
        ],
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "forecast_next_hour",
        "description": TOOL_DESCRIPTIONS[
            "forecast_next_hour"
        ],
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        "strict": True,
    },
]


def run_agent(user_request):
    """
    Execute an LLM-controlled tool-calling loop.

    The model chooses tools.
    Python executes only registered functions.
    Tool results are returned to the model.
    """

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY is missing from your .env file."
        )

    client = OpenAI()

    conversation = [
        {
            "role": "user",
            "content": user_request,
        }
    ]

    print("\n" + "=" * 65)
    print("INNEVA.E - LLM ENERGY INTELLIGENCE AGENT")
    print("=" * 65)

    print(f"\nUSER: {user_request}")
    print(f"MODEL: {MODEL_NAME}")

    for round_number in range(1, MAX_TOOL_ROUNDS + 1):

        print(
            f"\nAGENT ROUND {round_number}"
        )
        print("-" * 65)

        response = client.responses.create(
            model=MODEL_NAME,
            instructions=SYSTEM_INSTRUCTIONS,
            input=conversation,
            tools=TOOLS,
            tool_choice="auto",
            parallel_tool_calls=False,
            max_output_tokens=800,
            store=False,
        )

        # Preserve the model's output items for the next turn.
        conversation.extend(
            [
                item.model_dump(
                    exclude_none=True
                )
                for item in response.output
            ]
        )

        tool_calls = [
            item
            for item in response.output
            if item.type == "function_call"
        ]

        if not tool_calls:

            final_text = response.output_text

            print("\nFINAL AGENT RESPONSE")
            print("-" * 65)

            print(
                final_text
                if final_text
                else "No text response returned."
            )

            return final_text

        for tool_call in tool_calls:

            tool_name = tool_call.name

            print(
                f"LLM requested tool: {tool_name}"
            )

            try:
                arguments = json.loads(
                    tool_call.arguments or "{}"
                )

                if arguments != {}:
                    raise ValueError(
                        "This tool does not accept arguments."
                    )

                observation = execute_tool(
                    tool_name
                )

            except Exception as error:

                observation = {
                    "status": "error",
                    "tool": tool_name,
                    "error_type": type(error).__name__,
                    "message": str(error),
                }

            print(
                "TOOL RESULT:\n"
                + json.dumps(
                    observation,
                    indent=2
                )
            )

            # Return the tool result to the LLM.
            conversation.append({
                "type": "function_call_output",
                "call_id": tool_call.call_id,
                "output": json.dumps(
                    observation
                ),
            })

    print("\nMaximum tool rounds reached.")

    return (
        "The agent reached its execution limit "
        "before completing the request."
    )


def main():

    request = (
        "Analyze the historical electricity market, "
        "check the data quality, and generate a "
        "one-hour-ahead demand forecast. "
        "Explain the most important findings "
        "and limitations."
    )

    run_agent(request)


if __name__ == "__main__":
    main()
