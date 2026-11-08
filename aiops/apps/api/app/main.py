import os, asyncio, logging
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import httpx
from . import repository as repo
from .adapters.history import HistoryApiAdapter
from .adapters.jennifer_mcp import JenniferMCPAdapter, JenniferMCPError
from .adapters.dify import DifyWorkflowAdapter
from .analyzer import embed, MODEL, EMBED_MODEL, OLLAMA, ollama_options

logging.basicConfig(level=os.getenv('LOG_LEVEL','INFO'))
log=logging.getLogger('aiops.api')
MODE=os.getenv('DATA_MODE','live').lower()
ICOUNT=int(os.getenv('INSTITUTION_COUNT','30')); BCOUNT=int(os.getenv('BUSINESS_COUNT','140'))
IEST=os.getenv('INSTITUTION_COUNT_ESTIMATE','true').lower()=='true'; BEST=os.getenv('BUSINESS_COUNT_ESTIMATE','true').lower()=='true'

@asynccontextmanager
async def lifespan(app):
    await asyncio.to_thread(repo.init_schema)
    yield
app=FastAPI(title='AIOps Integrated Dashboard API',version='0.3.0',lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
class Chat(BaseModel): question:str=Field(min_length=1,max_length=8000)
class EmbeddingRequest(BaseModel): source_ref:str=Field(min_length=1,max_length=500); content:str=Field(min_length=1,max_length=20000)

def source(kind):
    a=HistoryApiAdapter(kind)
    if not a.configured: return {'configured':False,'ok':None,'detail':'URL 미설정'}
    try: state=repo.get_integration_state(kind)
    except Exception: state=None
    if state: return {'configured':bool(state['configured']),'ok':state['ok'],'detail':state['detail'],'checked_at':state['checked_at']}
    return {'configured':True,'ok':None,'detail':'설정됨; 첫 조회 대기'}
def source_status():
    j=JenniferMCPAdapter(); d=DifyWorkflowAdapter()
    return {'incidents':source('incident'),'events':source('event'),
      'institutions':{'configured':bool(os.getenv('INSTITUTIONS_API_URL','').strip()),'ok':None,'detail':'기관/업무 API 미설정 또는 KPI 매핑 미완료'},
      'jennifer':{'configured':j.configured,'ok':None,'detail':'jennifer-mcp 컨테이너 연결됨; 뷰서버 경로 확정 필요' if j.configured else '비활성 (JENNIFER_MCP_URL 미설정)'},
      'dify':{'configured':d.configured,'ok':None,'detail':'Workflow 출력 매핑 검증 필요' if d.configured else 'Workflow URL/API Key 미설정'},
      'ollama':{'configured':True,'ok':None,'detail':MODEL},'embeddings':{'configured':True,'ok':None,'detail':EMBED_MODEL}}

@app.get('/healthz')
def healthz(): return {'status':'ok','utc':datetime.now(timezone.utc).isoformat(),'mode':MODE}

@app.get('/dashboard')
def dashboard():
    try:
        if MODE=='mock':
            incidents=[{'kind':'incident','id':'DEMO-IC-001','institution_name':'모의 기관 A','title':'모의 장애 예시 — 실제 데이터 아님','occurred_at':None,'analysis_status':'complete','analysis_summary':'모의 데이터입니다. 실제 장애 분석 결과가 아닙니다.','is_demo':True}]
            events=[{'kind':'event','id':'DEMO-EV-001','institution_name':'모의 기관 B','title':'모의 이벤트 예시 — 실제 데이터 아님','occurred_at':None,'analysis_status':'queued','analysis_summary':'모의 데이터입니다. 실제 이벤트 분석 결과가 아닙니다.','is_demo':True}]
            detections=[{'id':'DEMO-D-1','source_kind':'incident','source_id':'DEMO-IC-001','institution_name':'모의 기관 A','business_name':'모의 업무','content':'모의 탐지 예시 — 실제 데이터가 아닙니다.','status':'demo'}]
            watch=[{'id':'DEMO-W-1','source_kind':'event','source_id':'DEMO-EV-001','institution_name':'모의 기관 B','business_name':'모의 업무','content':'모의 관찰 예시 — 실제 데이터가 아닙니다.','status':'watch'}]
            statuses=source_status(); statuses['incidents']={'configured':True,'ok':True,'detail':'모의 데이터 모드'}; statuses['events']={'configured':True,'ok':True,'detail':'모의 데이터 모드'}
            return {'mode':'mock','api_status':'정상(모의 모드)','summary':{'institution_count':ICOUNT,'institution_is_estimate':True,'business_count':BCOUNT,'business_is_estimate':True,'incident_count':1,'event_count':1},'source_status':statuses,'incidents':{'items':incidents},'events':{'items':events},'detections':{'items':detections},'watchlist':{'items':watch}}
        incidents=repo.list_history('incident',3); events=repo.list_history('event',3); detections=repo.list_detections(5); watch=repo.list_watchlist(5)
        ic=repo.count_history('incident'); ec=repo.count_history('event')
    except Exception as exc:
        log.exception('dashboard database error type=%s',type(exc).__name__); raise HTTPException(503,'데이터베이스 상태를 확인하세요')
    statuses=source_status()
    return {'mode':MODE,'api_status':'정상','summary':{'institution_count':ICOUNT,'institution_is_estimate':IEST,'business_count':BCOUNT,'business_is_estimate':BEST,'incident_count':ic,'event_count':ec},'source_status':statuses,'incidents':{'items':[dict(x) for x in incidents],'error':statuses['incidents']['detail'] if statuses['incidents'].get('ok') is False else None},'events':{'items':[dict(x) for x in events],'error':statuses['events']['detail'] if statuses['events'].get('ok') is False else None},'detections':{'items':[dict(x) for x in detections]},'watchlist':{'items':[dict(x) for x in watch]}}

@app.get('/items/{kind}/{ident}')
def item_detail(kind:str,ident:str):
    if kind not in ('incident','event'): raise HTTPException(404,'unknown record kind')
    if MODE=='mock':
        demo={'kind':kind,'id':ident,'institution_name':'모의 기관','title':'모의 상세 정보 — 실제 데이터 아님','occurred_at':None,'source_payload':{'demo':True,'note':'테스트 전용 예시'},'analysis_status':'complete','analysis_summary':'모의 데이터입니다.','analysis_detail':'실제 분석 결과가 아닙니다.','is_demo':True}
        if not ident.startswith('DEMO-'): raise HTTPException(404,'모의 모드에서 찾을 수 없는 ID')
        return {'item':demo,'source_configured':True}
    try: row=repo.get_history(kind,ident)
    except Exception as exc: log.exception('detail db error'); raise HTTPException(503,'데이터베이스 상태를 확인하세요')
    if not row: raise HTTPException(404,'해당 ID가 이력 DB에 없습니다. 실제 API 동기화 상태를 확인하세요.')
    out=dict(row); out.pop('analysis_error',None)
    return {'item':out,'source_configured':HistoryApiAdapter(kind).configured}

@app.get('/integrations/status')
def integrations_status(): return source_status()

@app.post('/integrations/jennifer/discover')
async def jennifer_discover():
    a=JenniferMCPAdapter()
    if not a.configured: raise HTTPException(400,'JENNIFER_MCP_URL 미설정')
    try: return await a.discover_tools()
    except JenniferMCPError as exc: raise HTTPException(502,str(exc))

@app.post('/chat')
async def chat(req:Chat):
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            r=await client.post(f'{OLLAMA}/api/chat',json={'model':MODEL,'messages':[{'role':'user','content':req.question}],'stream':False,'think':False,'options':ollama_options(0.3)}); r.raise_for_status(); j=r.json()
        return {'model':j.get('model',MODEL),'answer':j.get('message',{}).get('content','')}
    except Exception as exc: raise HTTPException(502,f'로컬 LLM 요청 실패({type(exc).__name__})')

@app.post('/embeddings')
async def embeddings(req:EmbeddingRequest):
    try:
        vector=await embed(req.content); await asyncio.to_thread(repo.save_chunk,req.source_ref,req.content,vector)
        return {'status':'stored','source_ref':req.source_ref,'dimensions':len(vector)}
    except Exception as exc: raise HTTPException(502,f'임베딩/저장 실패({type(exc).__name__})')
