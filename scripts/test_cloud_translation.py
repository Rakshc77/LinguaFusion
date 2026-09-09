"""One synthetic translation; never prints credentials or raw provider errors."""
import asyncio
import os
import json
import unicodedata
import re
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cloud_api.pilot_providers import PilotProviders, ProviderFailure
from cloud_api.test_budget import TestBudget

async def main():
    root = Path(__file__).resolve().parents[1]
    service = PilotProviders(TestBudget(root / 'cloud_api/local-data/combined-test-budget.sqlite3'))
    if '--reading-guide' in sys.argv:
        results = []
        for language in ('ar', 'or'):
            try:
                native = await service.translate(os.environ.get('LF_TEST_OPENROUTER_KEY', ''), 'Train 42 leaves at 14:30. Please bring 2 tickets.', language, model='google/gemma-3-27b-it')
                guide = await service.romanize(os.environ.get('LF_TEST_OPENROUTER_KEY', ''), native, language)
                results.append(guide)
                print(language, 'translation and reading guide returned; quality review required.', flush=True)
            except (ProviderFailure, ValueError) as error:
                results.append({'language': language, 'error': str(error)})
                print(language, str(error), flush=True)
        report = root / 'cloud_api/local-data/synthetic-tests/reading-guides.json'
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
        return int(any('error' in r for r in results))
    if '--all-languages' in sys.argv:
        results = []
        for language in ('en', 'de', 'es', 'hi', 'ar', 'or'):
            source = 'Der Zug 42 faehrt um 14:30 ab. Bitte bringen Sie 2 Fahrkarten mit.' if language == 'en' else 'Train 42 leaves at 14:30. Please bring 2 tickets.'
            try:
                result = await service.translate(os.environ.get('LF_TEST_OPENROUTER_KEY', ''), source, language)
                normalized = ''.join(str(unicodedata.decimal(c)) if c.isdecimal() else c for c in result)
                numbers = all(value in normalized for value in ('42', '14:30', '2'))
                script_range = {'hi': (0x900, 0x97f), 'ar': (0x600, 0x6ff), 'or': (0xb00, 0xb7f)}.get(language)
                script_ok = not script_range or any(script_range[0] <= ord(c) <= script_range[1] for c in result)
                # This fixture has no Latin-script names/codes to preserve.
                untranslated = bool(script_range and re.search(r'\b(?:train|leaves|please|bring|tickets)\b', result, re.I))
                results.append({'language': language, 'output': result, 'numbers_preserved': numbers, 'expected_script_present': script_ok, 'untranslated_fixture_words': untranslated})
                print(language, 'number check:', numbers, 'script check:', script_ok, flush=True)
            except (ProviderFailure, ValueError) as error:
                results.append({'language': language, 'error': str(error)})
                print(language, 'request failed', flush=True)
        report = root / 'cloud_api/local-data/synthetic-tests/translation-languages.json'
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps({'note': 'Smoke checks only, not native-speaker quality certification.', 'results': results}, ensure_ascii=False, indent=2), encoding='utf-8')
        print('Synthetic report saved. Six attempts reserve at most USD 0.06; not actual billing.')
        return int(any(r.get('error') or r.get('untranslated_fixture_words') or not r.get('numbers_preserved') or not r.get('expected_script_present') for r in results))
    try:
        result = await service.translate(os.environ.get('LF_TEST_OPENROUTER_KEY', ''), 'Hello. The train leaves at 14:30.', 'de')
        print('Translation request succeeded. Synthetic sample result:')
        print(result)
        print('USD 0.01 remains reserved, not reported as actual billed spend.')
    except (ProviderFailure, ValueError) as error:
        print(str(error))
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
