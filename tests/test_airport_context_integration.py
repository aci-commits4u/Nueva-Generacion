"""Airport identities enrich both live stages without choosing an itinerary."""
import json
from types import SimpleNamespace

from app.ai_pipeline import call_json
from tests.test_enforcement import client


def test_catalogue_search_is_readonly_and_bounded(client, monkeypatch):
    monkeypatch.setattr('app.foundry_client.extract',lambda *a,**k: (_ for _ in ()).throw(AssertionError('search must not call a model')))
    result=client.get('/api/airports',params={'q':'Heathrow'})
    assert result.status_code==200
    assert result.json()['airports'][0]['code']=='LHR'
    assert result.json()['reference']['version']=='20260905'
    assert client.get('/api/airports',params={'q':'x'*81}).status_code==422


def test_both_live_stages_receive_ambiguity_preserving_reference(monkeypatch):
    monkeypatch.setenv('AZURE_OPENAI_ENDPOINT','https://synthetic.example')
    monkeypatch.setenv('AZURE_OPENAI_API_KEY','synthetic-key')
    monkeypatch.setenv('AZURE_OPENAI_DEPLOYMENT','synthetic-model')
    response=SimpleNamespace(usage=None,id='synthetic-reference',choices=[SimpleNamespace(
        finish_reason='stop',message=SimpleNamespace(content=json.dumps({
            'fields':{},'sources':{},'unsupported':[], 'clarifications':[], 'explanation':'Review.'})))])
    requests=[]
    def capture(**kwargs):
        requests.append(json.loads(kwargs['messages'][1]['content']))
        return response
    fake=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=capture)))
    monkeypatch.setattr('app.ai_pipeline.OpenAI',lambda **kwargs:fake)
    for stage in ('extract','coverage_audit'):
        call_json(stage,'flight','Heathrow to Tokyo next Friday','audited')
    for payload in requests:
        records=payload['airport_reference']['airports']
        assert {'LHR','HND','NRT'} <= {item['code'] for item in records}
        assert len(records)<=30
        assert payload['customer_source_text']=='Heathrow to Tokyo next Friday'
        assert payload['airport_reference']['provenance']['license']=='MIT'
