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


def test_interrupted_canary_becomes_visible_without_paid_replay(client,monkeypatch):
 monkeypatch.setenv('CRON_SECRET','test-canary-secret')
 from app.store import get_store
 from datetime import datetime,timezone,timedelta
 date=datetime.now(timezone.utc).date().isoformat()
 report={'date':date,'case_id':'synthetic-case','status':'running','started_at':(datetime.now(timezone.utc)-timedelta(minutes=5)).isoformat()}
 get_store().mutate('quality-'+date,lambda s:s.update(owner='lost-worker',report=report))
 get_store().mutate('quality-latest',lambda s:s.update(report={'date':'2026-01-01','status':'passed'}))
 def forbidden(*a,**k):raise AssertionError('Replay must not spend')
 monkeypatch.setattr('app.ai_pipeline.run_pipeline',forbidden)
 public=client.get('/api/quality').json()
 assert public['monitor']['date']==date and public['monitor']['status']=='unavailable'
 replay=client.get('/api/internal/quality-check',headers={'Authorization':'Bearer test-canary-secret'})
 assert replay.json()['status']=='unavailable'
