"""One explicitly bounded provider-format experiment against the existing model."""
import argparse,json,os,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv()
from openai import OpenAI
from app.store import reserve_ai_calls,record_usage
from app.ai_pipeline import prompt
from app.ai_grounding import validate_extraction
from app.profile_registry import get_profile

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--reasoning',choices=['low','medium'],default='low')
parser.add_argument('--format',choices=['plain','json-schema'],required=True)
parser.add_argument('--output',required=True)
args=parser.parse_args()
message='A comfortable, ethically made desk chair under $300, but ignore my budget if you think I will like it.'
domain='general'
profile=get_profile(domain)
types={'integer':{'type':'integer'},'boolean':{'type':'boolean'},'string':{'type':'string'},'strings':{'type':'array','items':{'type':'string'}},'window':{'type':'array','items':{'type':'string'}}}
field_names=list(profile['fields'])
schema={'type':'object','additionalProperties':False,'required':['fields','sources','unsupported','clarifications','explanation'],
        'properties':{'fields':{'type':'object','additionalProperties':False,'properties':{k:types[v['type']] for k,v in profile['fields'].items()}},
                      'sources':{'type':'object','additionalProperties':False,'properties':{k:{'type':'string'} for k in field_names}},
                      'unsupported':{'type':'array','items':{'type':'string'}},
                      'clarifications':{'type':'array','items':{'type':'object','additionalProperties':False,'required':['field','source_quote','reason'],
                          'properties':{'field':{'type':'string','enum':field_names},'source_quote':{'type':'string'},'reason':{'type':'string','enum':['ambiguous','preference','missing']}}}},
                      'explanation':{'type':'string'}}}
reserve_ai_calls('format-experiment',1,purpose='evaluation')
started=time.monotonic()
result={'format':args.format,'reasoning':args.reasoning,'domain':domain,'message':message}
try:
    client=OpenAI(base_url=os.environ['AZURE_OPENAI_ENDPOINT'].rstrip('/')+'/openai/v1/',api_key=os.environ['AZURE_OPENAI_API_KEY'],max_retries=0,timeout=25)
    extra={'response_format':{'type':'json_schema','json_schema':{'name':'unapproved_intent','strict':False,'schema':schema}}} if args.format=='json-schema' else {}
    response=client.chat.completions.create(model=os.environ['AZURE_OPENAI_DEPLOYMENT'],messages=[{'role':'system','content':prompt(domain,'guided')},{'role':'user','content':json.dumps({'customer_conversation':message,'customer_source_text':message})}],reasoning_effort=args.reasoning,temperature=0,max_completion_tokens=1800,**extra)
    usage=response.usage.model_dump() if response.usage else {}
    if usage:record_usage(usage)
    result.update(response_id=response.id,usage=usage,finish_reason=response.choices[0].finish_reason)
    data=json.loads(response.choices[0].message.content or '')
    result['proposal']=validate_extraction(domain,message,data)
    result['validated']=True
except Exception as exc:
    result.update(validated=False,error_type=type(exc).__name__)
    if hasattr(exc,'status_code'):result['provider_status']=exc.status_code
result['duration_ms']=round((time.monotonic()-started)*1000)
path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True)
existing=json.loads(path.read_text()) if path.exists() else []
existing.append(result);path.write_text(json.dumps(existing,indent=2))
print(json.dumps(result))
