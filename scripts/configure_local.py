"""Configure authorized Azure resources without echoing secrets."""
import json, os, subprocess
from pathlib import Path
from verifiable_intent.crypto.signing import generate_es256_key, private_key_to_jwk

def az(*args):
    return subprocess.check_output(['az',*args,'-o','json'],text=True)

path=Path('.env')
if path.exists():
    raise SystemExit('Existing environment preserved; update it intentionally.')
key=json.loads(az('cognitiveservices','account','keys','list','-n','victor-lead-foundry-20261012','-g','lead-team-rg'))['key1']
connection=json.loads(az('storage','account','show-connection-string','-n','intentjudge20261013','-g','lead-team-rg'))['connectionString']
values={
 'AZURE_OPENAI_ENDPOINT':'https://victor-lead-foundry-20261012.openai.azure.com/',
 'AZURE_OPENAI_API_KEY':key,'AZURE_OPENAI_DEPLOYMENT':'gpt-oss-120b','AZURE_OPENAI_API_VERSION':'2024-10-21',
 'AZURE_TABLE_CONNECTION_STRING':connection,'AZURE_TABLE_NAME':'IntentJudge',
 'DEMO_SIGNING_KEYS':json.dumps({r:private_key_to_jwk(generate_es256_key()) for r in ('issuer','user','agent','merchant')}),
 'MOCK_LLM':'0','AI_CALL_LIMIT':'1500','AI_DAILY_LIMIT':'80','AI_SESSION_LIMIT':'64','AI_RESERVATION_USD':'0.02',
 'AI_PIPELINE_VERSION':'adaptive_fast','AI_REASONING_EFFORT':'low',
 'STORE_BACKEND':'sqlite','SQLITE_PATH':'.intent-judge.sqlite3',
}
path.write_text('\n'.join(f'{k}={json.dumps(v)}' for k,v in values.items())+'\n')
os.chmod(path,0o600)
print('Configured Azure model, table credentials, and generated demo keys; no secret values printed.')
