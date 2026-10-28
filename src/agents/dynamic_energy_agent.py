"""INNEVA.E local dynamic agent — Checkpoint 18.7.1.

Conservative request-intent verification authorizes explicit tools and supplements missing ones.
Keeps the original reporting agent and scoped validator unchanged.
"""
import argparse
import json
import re
from ollama import Client
from energy_tools import execute_tool
from dynamic_response_validator import validate_dynamic_response

MODEL = 'qwen2.5:3b'
SUPPORTED_MODES = ('development_90d', 'full_history')
ALLOWED_TOOLS = ('get_energy_overview', 'get_data_quality', 'forecast_next_hour')
MAX_TOOL_ROUNDS = 2
MAX_ANSWER_ATTEMPTS = 2

DESCRIPTIONS = {
    'get_energy_overview': 'Historical average/peak electricity demand, renewable generation, wholesale prices, observed counts and date range.',
    'get_data_quality': 'Missing values, dataset completeness, hourly continuity, offshore wind and wholesale price gaps.',
    'forecast_next_hour': 'Historical one-hour-ahead demand persistence forecast, target and execution timestamps; not live.',
}
TOOLS = [{
    'type': 'function',
    'function': {
        'name': name, 'description': description,
        'parameters': {
            'type': 'object',
            'properties': {'dataset_mode': {
                'type': 'string', 'enum': list(SUPPORTED_MODES),
                'description': 'Optional; must match the application-selected mode.'}},
            'required': [], 'additionalProperties': False,
        },
    },
} for name, description in DESCRIPTIONS.items()]

SYSTEM_PROMPT = '''You are INNEVA.E's LOCAL HISTORICAL electricity analytics assistant.
Choose approved tools relevant to ALL distinct parts of the question.
For a question asking about demand AND missing data, select BOTH overview and quality.
For demand AND missing data AND forecast, select ALL THREE.
Use tools for facts. Do not invent numbers, causes, accuracy, or live market data.
Demand/generation: MW. Wholesale prices: EUR/MWh. Missing values reduce completeness.
Price observations were not imputed. Forecasts use historical previous-hour persistence.
Forecast target timestamp is NOT execution timestamp. Never change dataset mode.
'''

# Deliberately narrow patterns: avoid treating "missing prices" as a request
# for a price average, or "forecast limitations" as a data-quality audit.
INTENT_PATTERNS = {
    'get_energy_overview': (
        r'\b(?:average|mean|peak|maximum|minimum|highest|lowest|total|summari[sz]e|overview|analy[sz]e|statistics?|historical trend)\b'
        r'[^.!?\n]{0,90}\b(?:electricity\s+)?(?:demand|load|generation|renewables?|wholesale price|market)\b',
        r'\b(?:electricity\s+)?(?:demand|load|generation|renewables?|wholesale price|market)\b'
        r'[^.!?\n]{0,75}\b(?:average|mean|peak|maximum|minimum|statistics?|overview|trend)\b',
    ),
    'get_data_quality': (
        r'\b(?:missing|gaps?|nulls?|completeness|data quality|quality issues?|continuity|incomplete|imput(?:ed|ation))\b',
    ),
    'forecast_next_hour': (
        r'\b(?:forecast|predict(?:ion|ed|ing)?|project(?:ion|ed)?|one.hour.ahead|next.hour demand)\b',
    ),
}


def infer_explicit_tools(question):
    """Conservatively infer explicit requests, not implicit analytical needs."""
    text = question.lower()
    # A forecast-only request is not also a request for average demand.
    return [name for name in ALLOWED_TOOLS
            if any(re.search(pattern, text, re.I) for pattern in INTENT_PATTERNS[name])]


def validate_arguments(arguments, mode):
    if arguments is None:
        arguments = {}
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return 'Invalid JSON tool arguments.'
    if not isinstance(arguments, dict):
        return 'Tool arguments must be a JSON object.'
    extra = set(arguments) - {'dataset_mode'}
    if extra:
        return f'Unexpected tool arguments: {sorted(extra)}'
    if arguments.get('dataset_mode', mode) != mode:
        return 'Tool requested a dataset mode different from the application mode.'
    return None


def build_result(status, model, mode, selected_tools, tool_results, response='',
                 validation=None, attempts=0, error=None, required_tools=None,
                 supplemented_tools=None, proposed_tools=None, rejected_tools=None):
    result = {
        'status': status, 'model': model, 'dataset_mode': mode,
        'selected_tools': list(selected_tools), 'tool_results': tool_results,
        'response': response, 'validation': validation, 'attempts': attempts,
        'required_tools_inferred': list(required_tools or []),
        'tools_added_by_verifier': list(supplemented_tools or []),
        'tools_proposed_by_model': list(proposed_tools or []),
        'tools_rejected_by_authorizer': list(rejected_tools or []),
    }
    if error is not None:
        result['error'] = str(error)
    return result


def answer_completeness_errors(answer, tool_results):
    """Minimum context requirements; deterministic factual checks remain separate."""
    errors = []
    if 'get_energy_overview' in tool_results:
        if not re.search(r'\bMW\b', answer, re.I):
            errors.append('Demand analysis must include MW units.')
    if 'forecast_next_hour' in tool_results:
        if not re.search(r'\bMW\b', answer, re.I):
            errors.append('Forecast must include MW units.')
        if not re.search(r'\b(?:historical|persistence|previous.hour)\b', answer, re.I):
            errors.append('Forecast must describe its historical persistence basis.')
        if not re.search(r'\b(?:not live|not a live|historical forecast|historical scenario)\b', answer, re.I):
            errors.append('Forecast must explicitly clarify it is not live.')
        target = tool_results['forecast_next_hour'].get('forecast_timestamp_utc')
        if not isinstance(target, str) or target not in answer:
            errors.append('Forecast must state the exact historical target timestamp (UTC).')
        if not re.search(r'\b(?:previous.hour persistence|historical persistence|persistence method|persistence model|last observed demand is carried forward|last observed demand forward|last observed demand for the next hour)\b', answer, re.I):
            errors.append('Forecast must describe the previous-hour persistence methodology.')
    if 'get_data_quality' in tool_results:
        if not re.search(r'\b(?:missing|gaps?|incomplete|complete)\b', answer, re.I):
            errors.append('Data-quality answer must discuss missing observations or completeness.')
    return errors


def request_answer(client, model, messages, tool_results, user_request, prior_errors=None):
    answer_messages = list(messages)
    answer_messages.append({
        'role': 'system',
        'content': (
            'Answer the ORIGINAL question completely using ONLY these executed Python results. '
            'Write 2-5 concise sentences or short bullets, not just a bare number. '
            'For demand, state the value and MW. For missing data, state counts and variables. '
            'For forecasts, state MW, historical target timestamp, previous-hour persistence '
            'method. Include the exact sentence: This is a historical scenario, not a live forecast. Do not confuse target and generation timestamps. '
            'Do not invent missingness causes, price imputation, or accuracy claims. '
            'Use decimal dots and NO thousands separators. Do not invent tools.\n'
            'ORIGINAL QUESTION: ' + user_request + '\n'
            'VERIFIED RESULTS: ' + json.dumps(tool_results, ensure_ascii=False)
        ),
    })
    if prior_errors:
        answer_messages.append({
            'role': 'system',
            'content': 'Your previous answer failed checks. Correct every issue. If the forecast is historical, explicitly write: This is a historical scenario, not a live forecast. Issues: '
                       + json.dumps(prior_errors, ensure_ascii=False)
                       + '. Write a fresh answer without mentioning validation.',
        })
    response = client.chat(model=model, messages=answer_messages, stream=False,
                           options={'temperature': 0, 'num_ctx': 4096, 'num_predict': 650})
    return (response.message.content or '').strip()


def run_dynamic_agent(user_request, mode='development_90d', model=MODEL):
    if mode not in SUPPORTED_MODES:
        raise ValueError(f'Unsupported dataset mode: {mode}')
    if model != MODEL:
        raise ValueError(f'Unsupported model: {model}')
    if not isinstance(user_request, str) or not user_request.strip():
        raise ValueError('Question must be nonempty text.')

    print('=' * 65)
    print('INNEVA.E - VERIFIED DYNAMIC ENERGY AGENT (18.7.1)')
    print('=' * 65)
    print(f'MODEL: {model}\nDATASET MODE: {mode}\nUSER REQUEST: {user_request}')
    required = infer_explicit_tools(user_request)
    print(f'EXPLICIT INTENT CHECK: {required}')
    client = Client()
    messages = [
        {'role': 'system', 'content': SYSTEM_PROMPT},
        {'role': 'user', 'content': f'Dataset mode: {mode}\nQuestion: {user_request}'},
    ]
    selected_tools = []
    supplemented = []
    proposed = []
    rejected = []
    tool_results = {}

    def result(status, **kwargs):
        return build_result(status, model, mode, selected_tools, tool_results,
                            required_tools=required, supplemented_tools=supplemented,
                            proposed_tools=proposed, rejected_tools=rejected, **kwargs)

    def run_tool(name, origin):
        if name not in ALLOWED_TOOLS:
            raise ValueError(f'Unauthorized tool: {name}')
        if name not in tool_results:
            value = execute_tool(name, mode=mode)
            if not isinstance(value, dict):
                raise ValueError(f'{name} returned invalid data.')
            valid_status = (value.get('status') in ('pass', 'pass_with_warnings')
                            if name == 'get_data_quality'
                            else value.get('status') == 'success')
            if not valid_status or value.get('dataset_mode') != mode:
                raise ValueError(f'{name} failed or returned the wrong dataset mode.')
            tool_results[name] = value
            selected_tools.append(name)
            if origin == 'verifier':
                supplemented.append(name)
            print(f'EXECUTED: {name} [{origin}]')
        else:
            print(f'REUSED: {name}')
        return tool_results[name]

    for round_number in range(1, MAX_TOOL_ROUNDS + 1):
        print(f'\nTOOL SELECTION ROUND {round_number}/{MAX_TOOL_ROUNDS}')
        try:
            response = client.chat(model=model, messages=messages, tools=TOOLS,
                                   stream=False, options={
                                       'temperature': 0, 'num_ctx': 4096, 'num_predict': 500})
        except Exception as exc:
            return result('error', error=exc)
        assistant = response.message
        calls = assistant.tool_calls or []
        if not calls:
            break
        messages.append(assistant.model_dump(exclude_none=True))
        for call in calls:
            name = call.function.name
            print(f'MODEL SELECTED TOOL: {name}')
            proposed.append(name)
            if name not in ALLOWED_TOOLS:
                return result('rejected', error=f'Unauthorized tool: {name}')
            arg_error = validate_arguments(call.function.arguments, mode)
            if arg_error:
                return result('rejected', error=arg_error)
            # Explicit-intent authorization is a conservative allowlist. When
            # intent is ambiguous (no deterministic match), defer to the LLM.
            # Respond to every tool call to preserve Ollama tool-call protocol.
            if required and name not in required:
                rejected.append(name)
                print(f'SKIPPED UNNECESSARY TOOL: {name} [authorizer]')
                messages.append({
                    'role': 'tool', 'tool_name': name,
                    'content': json.dumps({
                        'status': 'not_executed',
                        'reason': 'Not authorized by the explicit user request.',
                        'authorized_tools': required,
                    }, ensure_ascii=False),
                })
                continue
            try:
                value = run_tool(name, 'model')
            except Exception as exc:
                return result('error', error=exc)
            messages.append({'role': 'tool', 'tool_name': name,
                             'content': json.dumps(value, ensure_ascii=False)})

    # The deterministic verifier adds only tools explicitly indicated by
    # the user's wording. It does not run all tools indiscriminately.
    missing = [name for name in required if name not in tool_results]
    if missing:
        print(f'\nTOOL COVERAGE GAP: {missing}')
        for name in missing:
            try:
                run_tool(name, 'verifier')
            except Exception as exc:
                return result('error', error=exc)
        print('VERIFIER SUPPLEMENTED MISSING TOOLS:', supplemented)

    if not selected_tools:
        return result('no_tools_selected',
                      error='No approved tool was selected; unsupported factual request.')

    errors = None
    for attempt in range(1, MAX_ANSWER_ATTEMPTS + 1):
        print(f'\nVALIDATED ANSWER ATTEMPT {attempt}/{MAX_ANSWER_ATTEMPTS}')
        try:
            answer = request_answer(client, model, messages, tool_results,
                                    user_request, errors)
        except Exception as exc:
            return result('error', attempts=attempt, error=exc)
        # Preserve the model answer and deterministically add mandatory historical provenance.
        # This is verified by the tool metadata, not inferred by the language model.
        if ('forecast_next_hour' in tool_results
                and tool_results['forecast_next_hour'].get('data_freshness') == 'historical_snapshot'
                and not re.search(r'\b(?:not live|not a live|historical forecast|historical scenario)\b', answer, re.I)):
            answer = answer.rstrip() + '\n\nThis is a historical scenario, not a live forecast.'
            print('ADDED VERIFIED HISTORICAL FORECAST DISCLOSURE')
        # Supply missing forecast provenance from verified tool fields, not LLM guesses.
        if 'forecast_next_hour' in tool_results:
            forecast = tool_results['forecast_next_hour']
            target = forecast.get('forecast_timestamp_utc')
            if isinstance(target, str) and target and target not in answer:
                answer = answer.rstrip() + f'\n\nHistorical forecast target: {target} (UTC).'
                print('ADDED VERIFIED FORECAST TARGET TIMESTAMP')
            if (forecast.get('model') == 'previous_hour_persistence'
                    and not re.search(r'\b(?:previous.hour persistence|historical persistence|persistence method|persistence model|last observed demand is carried forward|last observed demand forward|last observed demand for the next hour)\b', answer, re.I)):
                answer = answer.rstrip() + ('\n\nMethod: previous-hour persistence; '
                                             'the last observed demand is carried forward by one hour.')
                print('ADDED VERIFIED FORECAST METHOD')
        validation = validate_dynamic_response(answer, tool_results, mode)
        completeness_errors = answer_completeness_errors(answer, tool_results)
        if completeness_errors:
            validation = dict(validation)
            validation['checks'] = dict(validation.get('checks') or {})
            validation['checks']['answer_completeness'] = False
            validation['errors'] = list(validation.get('errors') or []) + completeness_errors
            validation['status'] = 'fail'
        else:
            validation = dict(validation)
            validation['checks'] = dict(validation.get('checks') or {})
            validation['checks']['answer_completeness'] = True
        print(f'VALIDATION: {validation["status"]}')
        if validation['status'] == 'pass':
            return result('completed', response=answer, validation=validation, attempts=attempt)
        errors = validation['errors']
        print('VALIDATION ERRORS:', json.dumps(errors, ensure_ascii=False))
        print('REJECTED ANSWER:', answer)

    return result('rejected', validation=validation, attempts=MAX_ANSWER_ATTEMPTS,
                  error='Both answer attempts failed validation; no validated answer returned.')


def main():
    parser = argparse.ArgumentParser(description='INNEVA.E local verified dynamic agent')
    parser.add_argument('--mode', choices=SUPPORTED_MODES, default='development_90d')
    parser.add_argument('--question', default='What was the average electricity demand?')
    args = parser.parse_args()
    result = run_dynamic_agent(args.question, mode=args.mode)
    print('\n' + '=' * 65 + '\nAGENT EXECUTION RESULTS\n' + '=' * 65)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if result['status'] not in ('completed', 'no_tools_selected'):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
