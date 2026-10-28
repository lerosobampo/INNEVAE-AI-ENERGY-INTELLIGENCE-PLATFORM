"""INNEVA.E Checkpoint 18.2: scoped validation of dynamic agent answers.

Unlike response_validator.validate_response, this checks only executed tools.
Passing is not a guarantee of complete factual accuracy.
"""
import math
import re
from datetime import datetime, timezone
from response_validator import detect_repetition, parse_timestamp

ALLOWED = {'get_energy_overview', 'get_data_quality', 'forecast_next_hour'}
NUM = r'(?<![\w.,])\d[\d,]*(?:\.\d+)?(?![\w.,])'


def _number(value):
    try:
        return float(value.replace(',', ''))
    except (ValueError, AttributeError):
        return None


def _near_metric(text, anchors, expected, unit='MW'):
    """Check numeric values in a short window after an explicit metric label."""
    if not isinstance(expected, (float, int)) or not math.isfinite(expected):
        return []
    errors = []
    pattern = re.compile(rf'({"|".join(anchors)})[^\n.!?]{{0,100}}?({NUM})\s*{re.escape(unit)}\b', re.I)
    for match in pattern.finditer(text):
        value = _number(match.group(2))
        if value is None or not math.isclose(value, float(expected), abs_tol=0.02, rel_tol=0):
            errors.append(f'Incorrect {match.group(1)}: {match.group(2)} {unit}; expected {expected} {unit}.')
    return errors


def validate_dynamic_response(response_text, tool_results, mode):
    checks = {}
    errors = []
    text = response_text if isinstance(response_text, str) else ''
    lower = text.lower()
    tools = tool_results if isinstance(tool_results, dict) else {}

    def check(name, condition, message):
        checks[name] = bool(condition)
        if not condition:
            errors.append(message)

    check('narrative_present', bool(text.strip()), 'AI answer is empty.')
    check('approved_tools_only', bool(tools) and set(tools).issubset(ALLOWED),
          'No approved tool results were supplied, or an unapproved tool was supplied.')
    check('tool_statuses_valid', all(isinstance(v, dict) and (
        v.get('status') == 'success' if k != 'get_data_quality'
        else v.get('status') in ('pass', 'pass_with_warnings')) for k, v in tools.items()),
          'One or more tool results are invalid or unsuccessful.')
    check('dataset_mode_consistent', all(isinstance(v, dict) and v.get('dataset_mode') == mode
                                         for v in tools.values()), 'Tool results have inconsistent dataset modes.')
    check('no_excessive_repetition', not detect_repetition(text), 'Excessive repetition detected.')

    malformed = []
    for match in re.finditer(r'(?<![\w.,])[-+]?\d+(?:,\d+)+(?:\.\d+)?(?![\w.,])', text):
        raw = match.group(0)
        groups = raw.lstrip('+-').split('.')[0].split(',')
        if not (1 <= len(groups[0]) <= 3 and all(len(g) == 3 for g in groups[1:])):
            malformed.append(raw)
    check('valid_numeric_grouping', not malformed, f'Malformed number grouping: {malformed}')

    numeric_errors = []
    overview = tools.get('get_energy_overview', {})
    if isinstance(overview, dict) and overview:
        numeric_errors += _near_metric(text, [r'average (?:electricity )?demand', r'average load'],
                                       overview.get('average_demand_mw'))
        numeric_errors += _near_metric(text, [r'peak (?:electricity )?demand', r'peak load'],
                                       overview.get('peak_demand_mw'))
        numeric_errors += _near_metric(text, [r'average (?:total )?renewable generation'],
                                       overview.get('average_renewable_generation_mw'))
    forecast = tools.get('forecast_next_hour', {})
    if isinstance(forecast, dict) and forecast:
        numeric_errors += _near_metric(text, [r'predicted demand', r'forecast(?:ed)? demand',
                                               r'(?:demand )?forecast (?:is|of|for)',
                                               r'prediction (?:is|of|for)'],
                                       forecast.get('predicted_demand_mw'))
        # Detect wrong forecast MW in direct sentences even without a metric anchor.
        for sentence in re.split(r'(?<=[.!?])\s+|\n+', text):
            if re.search(r'\b(?:forecast|predicted demand|prediction)\b', sentence, re.I):
                for match in re.finditer(rf'({NUM})\s*MW\b', sentence, re.I):
                    val = _number(match.group(1))
                    expected = forecast.get('predicted_demand_mw')
                    if isinstance(expected, (int, float)) and (val is None or not math.isclose(val, expected, abs_tol=0.02, rel_tol=0)):
                        numeric_errors.append(f'Forecast MW mismatch: {match.group(1)} vs {expected}.')
    check('numeric_values_match_tools', not numeric_errors, '; '.join(dict.fromkeys(numeric_errors)))

    quality = tools.get('get_data_quality', {})
    if isinstance(quality, dict) and quality:
        missing = any(isinstance(quality.get(k), (int, float)) and quality[k] > 0
                      for k in ('missing_offshore_wind', 'remaining_missing_prices', 'missing_demand'))
        contradiction = missing and bool(re.search(
            r'(?:missing (?:values?|data|observations?) (?:do|does) not affect (?:the )?completeness|'
            r'(?:dataset|data) (?:is|are) (?:fully |entirely )?complete|'
            r'no missing (?:values?|data|observations?)|'
            r'missing (?:values?|data) (?:are|is) not (?:an? )?(?:issue|problem))', lower))
        check('missing_data_completeness_consistent', not contradiction,
              'Missing observations exist: do not claim the dataset is complete or unaffected.')
        unsupported_cause = bool(re.search(r'missing (?:values?|data|observations?)[^.!?\n]{0,110}\b(?:due to|caused by|because of)\b', lower))
        check('no_invented_missingness_causes', not unsupported_cause,
              'The tool does not establish the cause of missing observations.')
        false_accuracy = bool(re.search(r'(?:missing (?:values?|data)|completeness|continuity)[^.!?\n]{0,140}(?:do not imply|does not imply|guarantee|ensure|prove|confirm)[^.!?\n]{0,70}(?:accuracy|source accuracy|reliability)', lower))
        check('no_unsupported_accuracy_assurance', not false_accuracy,
              'Data completeness checks cannot establish source accuracy or rule out errors.')
        if quality.get('imputed_price_count') == 0:
            imputation_claim = bool(re.search(r'\b(?:prices? (?:were|was|are|is) (?:filled|imputed)|imputed prices? (?:were|was) used)\b', lower))
            check('no_invented_imputation', not imputation_claim,
                  'No wholesale price imputation occurred.')

    if isinstance(forecast, dict) and forecast:
        target = parse_timestamp(forecast.get('forecast_timestamp_utc'))
        latest = parse_timestamp(forecast.get('latest_observation_utc'))
        generated = parse_timestamp(forecast.get('generated_at_utc'))
        check('forecast_timestamps_valid', target is not None and latest is not None and target > latest,
              'Forecast tool timestamps are invalid.')
        # Check literal ISO target being labelled as execution/generation time.
        target_strings = {str(forecast.get('forecast_timestamp_utc', '')).lower()}
        if target:
            target_strings.update({target.strftime('%Y-%m-%dT%H:%M:%S+00:00').lower(),
                                   target.strftime('%Y-%m-%d %H:%M').lower()})
        confusion = False
        for sentence in re.split(r'(?<=[.!?])\s+|\n+', lower):
            if re.search(r'(?:forecast|prediction) (?:was )?(?:generated|created|executed|run) (?:at|on)', sentence):
                if any(s and s in sentence for s in target_strings):
                    confusion = True
                if target and target.strftime('%B %d, %Y').lower() in sentence:
                    confusion = True
        check('no_forecast_target_as_generation_time', not confusion,
              'Historical forecast target was incorrectly labelled as generation time.')
        check('no_live_forecast_claim', not bool(re.search(r'\b(?:live|real.time) (?:demand )?forecast\b', lower)
                                                  and not re.search(r'\b(?:not|isn.t|is not) (?:a )?(?:live|real.time)\b', lower)),
              'This is a historical persistence scenario, not a live forecast.')

    return {'status': 'pass' if not errors else 'fail', 'checks': checks,
            'errors': errors, 'warning': 'Selected automated checks only; passing does not guarantee factual accuracy.'}
