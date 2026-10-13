"""Push environment values over CLI stdin; suppress all secret-bearing output."""
from pathlib import Path
import subprocess
from dotenv import dotenv_values
values=dotenv_values('.env')
values['STORE_BACKEND']='azure'
values.pop('SQLITE_PATH',None)
for key,value in values.items():
    if value is None: continue
    secret=key in {'AZURE_OPENAI_API_KEY','AZURE_TABLE_CONNECTION_STRING','DEMO_SIGNING_KEYS'}
    proc=subprocess.run(['npx','--yes','vercel@63.1.2','env','add',key,'production,preview','--project','intent-judge-perfected','--scope','vmj-8946s-projects','--force','--yes','--sensitive' if secret else '--no-sensitive'],input=value,text=True,capture_output=True)
    if proc.returncode: raise SystemExit(f'Environment update failed for {key}; output withheld to protect credentials.')
    print(f'Configured {key}',flush=True)
