"""Live canaries are authenticated, replay-safe and report actual outcomes."""
from tests.test_enforcement import client


def test_missing_or_wrong_cron_secret_never_runs(client,monkeypatch):
 monkeypatch.setenv('CRON_SECRET','test-canary-secret')
 assert client.get('/api/internal/quality-check').status_code==401
 assert client.get('/api/internal/quality-check',headers={'Authorization':'Bearer wrong'}).status_code==401


def test_daily_canary_is_idempotent_and_public_report_is_safe(client,monkeypatch):
 monkeypatch.setenv('CRON_SECRET','test-canary-secret')
 calls=[]
 def run(domain,message,session,**kw):
  calls.append(kw['purpose'])
  return {'error':'synthetic failure'}
 monkeypatch.setattr('app.ai_pipeline.run_pipeline',run)
 headers={'Authorization':'Bearer test-canary-secret'}
 first=client.get('/api/internal/quality-check',headers=headers)
 assert first.status_code==200,first.text
 assert first.json()['status']=='failed'
 assert client.get('/api/internal/quality-check',headers=headers).json()==first.json()
 assert calls==['monitor']
 public=client.get('/api/quality')
 assert public.status_code==200 and public.json()['monitor']['status']=='failed'
 assert 'secret' not in public.text and 'customer_conversation' not in public.text


def test_budget_failure_does_not_become_mock_pass(client,monkeypatch):
 monkeypatch.setenv('CRON_SECRET','test-canary-secret')
 def limited(*a,**kw):raise ValueError('Live AI budget unavailable. No fallback was used.')
 monkeypatch.setattr('app.ai_pipeline.run_pipeline',limited)
 r=client.get('/api/internal/quality-check',headers={'Authorization':'Bearer test-canary-secret'})
 assert r.status_code==200 and r.json()['status']=='unavailable'
