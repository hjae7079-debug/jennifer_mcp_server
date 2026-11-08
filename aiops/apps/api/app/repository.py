import os, json
import psycopg
from psycopg.rows import dict_row
from pgvector.psycopg import register_vector

DATABASE_URL=os.getenv('DATABASE_URL','postgresql://aiops_app:change-me@postgres:5432/aiops')

def conn():
    c=psycopg.connect(DATABASE_URL,connect_timeout=5,row_factory=dict_row)
    try: register_vector(c)
    except Exception: pass
    return c

def init_schema():
    with conn() as c:
        c.execute('CREATE EXTENSION IF NOT EXISTS vector')
        c.execute('''CREATE TABLE IF NOT EXISTS history_item(
          kind TEXT NOT NULL CHECK(kind IN ('incident','event')), id TEXT NOT NULL,
          institution_name TEXT NOT NULL, title TEXT NOT NULL, occurred_at TIMESTAMPTZ NULL,
          source_payload JSONB NOT NULL DEFAULT '{}'::jsonb, analysis_status TEXT NOT NULL DEFAULT 'queued',
          analysis_summary TEXT NULL, analysis_detail TEXT NULL, analysis_error TEXT NULL,
          is_demo BOOLEAN NOT NULL DEFAULT FALSE, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY(kind,id))''')
        c.execute('''CREATE TABLE IF NOT EXISTS detection(
          id BIGSERIAL PRIMARY KEY, source_kind TEXT NULL, source_id TEXT NULL, institution_name TEXT NULL,
          business_name TEXT NULL, content TEXT NOT NULL, severity TEXT NOT NULL DEFAULT 'info',
          status TEXT NOT NULL DEFAULT 'new', created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE(source_kind,source_id,content))''')
        c.execute('''CREATE TABLE IF NOT EXISTS watchlist(
          id BIGSERIAL PRIMARY KEY, source_kind TEXT NULL, source_id TEXT NULL, institution_name TEXT NULL,
          business_name TEXT NULL, content TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'watch',
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE(source_kind,source_id,content))''')
        c.execute('''CREATE TABLE IF NOT EXISTS knowledge_chunk(
          id BIGSERIAL PRIMARY KEY, source_ref TEXT NOT NULL, content TEXT NOT NULL,
          embedding vector(1024) NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now())''')
        c.execute('''CREATE TABLE IF NOT EXISTS integration_state(
          name TEXT PRIMARY KEY, configured BOOLEAN NOT NULL, ok BOOLEAN NULL, detail TEXT NOT NULL,
          checked_at TIMESTAMPTZ NOT NULL DEFAULT now())''')
        c.execute('CREATE INDEX IF NOT EXISTS idx_history_kind_time ON history_item(kind,occurred_at DESC NULLS LAST)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_detection_time ON detection(created_at DESC)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_watch_time ON watchlist(created_at DESC)')
        c.commit()

def upsert_history(item):
    with conn() as c:
        exists=c.execute('SELECT 1 FROM history_item WHERE kind=%s AND id=%s',(item['kind'],item['id'])).fetchone() is not None
        c.execute('''INSERT INTO history_item(kind,id,institution_name,title,occurred_at,source_payload,analysis_status,is_demo)
          VALUES(%s,%s,%s,%s,%s,%s::jsonb,'queued',FALSE) ON CONFLICT(kind,id) DO UPDATE SET
          institution_name=EXCLUDED.institution_name,title=EXCLUDED.title,occurred_at=EXCLUDED.occurred_at,
          source_payload=EXCLUDED.source_payload,updated_at=now()''',
          (item['kind'],item['id'],item['institution_name'],item['title'],item.get('occurred_at'),json.dumps(item.get('source_payload',{}),ensure_ascii=False)))
        c.commit(); return not exists

def list_history(kind,limit=3):
    with conn() as c:
        return c.execute('''SELECT kind,id,institution_name,title,occurred_at,analysis_status,analysis_summary,analysis_detail,is_demo
          FROM history_item WHERE kind=%s AND is_demo=FALSE ORDER BY occurred_at DESC NULLS LAST,created_at DESC LIMIT %s''',(kind,limit)).fetchall()

def get_history(kind,ident):
    with conn() as c:
        return c.execute('''SELECT kind,id,institution_name,title,occurred_at,source_payload,analysis_status,analysis_summary,analysis_detail,analysis_error,is_demo,created_at,updated_at
          FROM history_item WHERE kind=%s AND id=%s''',(kind,ident)).fetchone()

def count_history(kind):
    with conn() as c: return c.execute('SELECT count(*) AS n FROM history_item WHERE kind=%s AND is_demo=FALSE',(kind,)).fetchone()['n']

def pending_analysis(limit=50):
    with conn() as c: return c.execute('''SELECT kind,id FROM history_item WHERE analysis_status IN ('queued','pending')
      ORDER BY CASE kind WHEN 'incident' THEN 0 ELSE 1 END,occurred_at DESC NULLS LAST LIMIT %s''',(limit,)).fetchall()

def update_analysis(kind,ident,status,summary=None,detail=None,error=None):
    with conn() as c:
        c.execute('UPDATE history_item SET analysis_status=%s,analysis_summary=%s,analysis_detail=%s,analysis_error=%s,updated_at=now() WHERE kind=%s AND id=%s',(status,summary,detail,error,kind,ident)); c.commit()

def list_detections(limit=5):
    with conn() as c: return c.execute('SELECT id,source_kind,source_id,institution_name,business_name,content,severity AS status,created_at FROM detection ORDER BY created_at DESC LIMIT %s',(limit,)).fetchall()
def list_watchlist(limit=5):
    with conn() as c: return c.execute('SELECT id,source_kind,source_id,institution_name,business_name,content,status,created_at FROM watchlist ORDER BY created_at DESC LIMIT %s',(limit,)).fetchall()
def save_chunk(source_ref,content,embedding):
    with conn() as c: c.execute('INSERT INTO knowledge_chunk(source_ref,content,embedding) VALUES(%s,%s,%s)',(source_ref,content,embedding)); c.commit()


def set_integration_state(name,configured,ok,detail):
    with conn() as c:
        c.execute('''INSERT INTO integration_state(name,configured,ok,detail,checked_at) VALUES(%s,%s,%s,%s,now())
          ON CONFLICT(name) DO UPDATE SET configured=EXCLUDED.configured,ok=EXCLUDED.ok,detail=EXCLUDED.detail,checked_at=now()''',(name,configured,ok,detail[:500])); c.commit()

def get_integration_state(name):
    with conn() as c: return c.execute('SELECT configured,ok,detail,checked_at FROM integration_state WHERE name=%s',(name,)).fetchone()


def insert_detection(item):
    with conn() as c:
        c.execute("""INSERT INTO detection(source_kind,source_id,institution_name,business_name,content,severity,status)
          VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
          (item.get('source_kind'),item.get('source_id'),item.get('institution_name'),item.get('business_name'),item['content'],item.get('severity','info'),item.get('status','new')))
        c.commit()

def insert_watchlist(item):
    with conn() as c:
        c.execute("""INSERT INTO watchlist(source_kind,source_id,institution_name,business_name,content,status)
          VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
          (item.get('source_kind'),item.get('source_id'),item.get('institution_name'),item.get('business_name'),item['content'],item.get('status','watch')))
        c.commit()


def reset_stale_analysis():
    with conn() as c:
        c.execute("UPDATE history_item SET analysis_status='queued',updated_at=now() WHERE analysis_status='analyzing' AND updated_at < now() - interval '10 minutes'")
        c.commit()
