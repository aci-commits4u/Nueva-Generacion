"""Run real UI journeys without paid model calls in an existing Playwright session."""
import argparse
import json
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--session', default='intent-ui-release')
args = parser.parse_args()
artifacts = Path('artifacts')
artifacts.mkdir(exist_ok=True)
for name in ['browser_product', 'browser_new_request', 'browser_flight_ui', 'browser_mobile', 'browser_navigation', 'browser_tutorial_pending', 'browser_availability_races', 'browser_uat_guards']:
    output = artifacts / f'{name}-verification.log'
    with output.open('w') as stream:
        subprocess.run(['playwright-cli', f'-s={args.session}', 'run-code', f'--filename=scripts/{name}.js'], stdout=stream, stderr=subprocess.STDOUT, check=True)
    result_line = next((line for line in output.read_text().splitlines() if line.startswith('{"result":')), None)
    if not result_line or json.loads(result_line).get('result') != 'PASS':
        raise RuntimeError(f'{name} did not return PASS; inspect {output}')
    print(json.dumps({'script': name, 'checks': json.loads(result_line)}), flush=True)
