"""INNEVA.E checkpoint 17.9A: deterministic, offline validator evaluation.

Run from project root:
    python3 src/evaluation/evaluate_agent_validator.py
    python3 src/evaluation/evaluate_agent_validator.py --strict

No Ollama, network, Streamlit, database, or CSV required. Fixtures are synthetic
and intentionally resemble the canonical dataset's published aggregates.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENTS = ROOT / "src" / "agents"
sys.path.insert(0, str(AGENTS))
from response_validator import validate_response  # noqa: E402

OUT = ROOT / "reports" / "evaluation"

MODES = {
    "development_90d": dict(n=2160, avg=13148.30, peak=18172.11, renewable=7266.53,
                            complete=2135, price=127.88, priced=2156, start="2026-07-03T00:00:00+00:00"),
    "full_history": dict(n=24096, avg=13307.08, peak=23201.57, renewable=6706.37,
                         complete=24071, price=89.14, priced=24092, start="2024-01-01T00:00:00+00:00"),
}


def fixtures(mode):
    d = MODES[mode]
    overview = dict(tool="get_energy_overview", status="success", dataset_mode=mode,
                    observation_count=d["n"], source_column_count=37,
                    first_timestamp_utc=d["start"],
                    last_timestamp_utc="2026-09-30T23:00:00+00:00",
                    average_demand_mw=d["avg"], peak_demand_mw=d["peak"],
                    average_renewable_generation_mw=d["renewable"],
                    renewable_complete_hours=d["complete"],
                    average_wholesale_price_eur_mwh=d["price"],
                    observed_price_hours=d["priced"], originally_missing_prices=4,
                    imputed_price_count=0, price_imputation_method="none")
    quality = dict(tool="get_data_quality", status="pass_with_warnings", dataset_mode=mode,
                   total_hours=d["n"], unique_hours=d["n"], source_column_count=37,
                   missing_demand=0, missing_offshore_wind=25, originally_missing_prices=4,
                   remaining_missing_prices=4, imputed_price_count=0, imputation_method="none")
    forecast = dict(tool="forecast_next_hour", status="success", dataset_mode=mode,
                    observation_count=d["n"], model="previous_hour_persistence",
                    latest_observation_utc="2026-09-30T23:00:00+00:00",
                    forecast_timestamp_utc="2026-10-01T00:00:00+00:00",
                    generated_at_utc="2026-10-25T19:00:00+00:00",
                    predicted_demand_mw=10585.38)
    tools = {"get_energy_overview": overview, "get_data_quality": quality,
             "forecast_next_hour": forecast}
    narrative = (
        f"Historical market conditions: From January 1, 2024 to September 30, 2026, "
        f"average demand is {d['avg']:,.2f} MW and peak demand is {d['peak']:,.2f} MW. "
        f"Average renewable generation is {d['renewable']:,.2f} MW. "
        f"There are 25 missing offshore wind values and 4 missing wholesale prices. "
        f"The one-hour demand forecast is 10,585.38 MW using previous-hour persistence, "
        f"not live market data. Completeness and continuity do not establish source accuracy."
    )
    return tools, narrative


def cases(mode):
    tools, good = fixtures(mode)
    d = MODES[mode]
    def case(name, expected, check=None, narrative=None, mutation=None):
        t = copy.deepcopy(tools)
        if mutation:
            mutation(t)
        return dict(name=name, expected=expected, check=check,
                    text=good if narrative is None else narrative, tools=t)

    items = [
        case("valid_baseline", "pass"),
        case("valid_calendar_commas", "pass", narrative=good + " Reporting date: July 3, 2026."),
        case("empty_narrative", "fail", "narrative_present", narrative=""),
        case("malformed_grouping", "fail", "valid_numeric_grouping",
             narrative=good + " An additional value is 1,3148.3 MW."),
        case("wrong_average_demand", "fail", "narrative_numeric_values_match_tools",
             narrative=good.replace(f"average demand is {d['avg']:,.2f} MW",
                                    "average demand is 1,000.00 MW")),
        case("demand_from_prices", "fail", "demand_not_calculated_from_prices",
             narrative=good + " Average demand is calculated using observed wholesale prices only."),
        case("quality_proves_accuracy", "fail", "no_quality_accuracy_overclaim_extended",
             narrative=good + " Data completeness ensures source accuracy."),
        case("false_offshore_completeness", "fail", "no_offshore_completeness_contradiction",
             narrative=good + " No missing values in offshore wind were found."),
        case("missing_required_tool", "fail", "required_tools_executed",
             mutation=lambda t: t.pop("forecast_next_hour")),
        case("inconsistent_mode", "fail", "dataset_modes_consistent",
             mutation=lambda t: t["get_data_quality"].update(dataset_mode="wrong_mode")),
        case("inconsistent_observation_count", "fail", "observation_counts_consistent",
             mutation=lambda t: t["get_data_quality"].update(total_hours=1)),
        case("invalid_forecast_time", "fail", "forecast_timestamps_valid",
             mutation=lambda t: t["forecast_next_hour"].update(
                 forecast_timestamp_utc="2026-09-30T22:00:00+00:00")),
        case("unexpected_imputation", "fail", "no_price_imputation",
             mutation=lambda t: t["get_data_quality"].update(imputed_price_count=4)),
        case("incorrect_price_hours", "fail", "observed_hour_counts_match_tools",
             narrative=good + f" There are 100 hours with observed wholesale prices."),
    ]
    return items


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="Exit nonzero if any expectation fails")
    args = parser.parse_args()
    results = []
    for mode in MODES:
        print(f"\nDATASET MODE: {mode}")
        for test in cases(mode):
            try:
                result = validate_response(test["text"], test["tools"])
                status = result["status"]
                checks = result.get("checks", {})
                correct = status == test["expected"] and (
                    test["check"] is None or checks.get(test["check"]) is False
                )
                record = dict(mode=mode, case=test["name"], expected=test["expected"],
                              actual=status, targeted_check=test["check"],
                              target_value=checks.get(test["check"]) if test["check"] else None,
                              passed=correct, check_count=len(checks), errors=result.get("errors", []))
            except Exception as exc:
                record = dict(mode=mode, case=test["name"], expected=test["expected"],
                              actual="exception", targeted_check=test["check"],
                              passed=False, error=f"{type(exc).__name__}: {exc}")
            results.append(record)
            print(f"  {'PASS' if record['passed'] else 'FAIL'}  {test['name']} "
                  f"(expected={test['expected']}, actual={record['actual']})")
    total = len(results)
    passed = sum(r["passed"] for r in results)
    summary = dict(checkpoint="17.9A", evaluation_type="deterministic_synthetic_regression",
                   evaluated_at_utc=datetime.now(timezone.utc).isoformat(),
                   total=total, passed=passed, failed=total-passed,
                   pass_rate=round(passed / total, 4),
                   note="Evaluates validator only, not LLM reliability or real dataset accuracy.",
                   results=results)
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "validator_regression_17_9A.json"
    target.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nRESULT: {passed}/{total} expectations met ({100*passed/total:.1f}%)")
    print(f"Saved: {target}")
    if args.strict and passed != total:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
