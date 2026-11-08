import asyncio, logging, os
from . import repository as repo
from .adapters.history import HistoryApiAdapter, HistoryAdapterError
from .analyzer import analyze
logging.basicConfig(level=os.getenv('LOG_LEVEL','INFO'))
log=logging.getLogger('aiops.worker')
POLL=max(10,int(os.getenv('HISTORY_POLL_SECONDS','300')))

async def poll_once():
    if os.getenv('DATA_MODE','live').lower() == 'mock':
        return
    for kind in ('incident','event'):
        adapter=HistoryApiAdapter(kind)
        if not adapter.configured:
            try: repo.set_integration_state(kind,False,None,'이력 API URL 미설정')
            except Exception: log.exception('state update failed kind=%s',kind)
            continue
        try:
            items=await adapter.fetch()
            for item in items:
                if repo.upsert_history(item): log.info('new history kind=%s id=%s',kind,item['id'])
            repo.set_integration_state(kind,True,True,f'조회 정상: {len(items)}건')
        except HistoryAdapterError as exc:
            try: repo.set_integration_state(kind,True,False,str(exc))
            except Exception: log.exception('state update failed kind=%s',kind)
            log.warning('history fetch failed kind=%s reason=%s',kind,exc)
        except Exception as exc:
            try: repo.set_integration_state(kind,True,False,f'요청 실패({type(exc).__name__})')
            except Exception: log.exception('state update failed kind=%s',kind)
            log.exception('history poll failed kind=%s type=%s',kind,type(exc).__name__)

async def analyze_pending():
    # DB query orders incident before event. One worker serializes jobs to preserve priority.
    for row in repo.pending_analysis(50):
        item=repo.get_history(row['kind'],row['id'])
        if not item: continue
        repo.update_analysis(row['kind'],row['id'],'analyzing')
        try:
            summary,detail,severity,watch_reason=await analyze(dict(item))
            repo.update_analysis(row['kind'],row['id'],'complete',summary,detail,None)
            payload=item.get('source_payload') or {}
            business=next((payload.get(k) for k in ('business_name','business','work_name') if isinstance(payload.get(k),str) and payload.get(k).strip()),None)
            repo.insert_detection({'source_kind':row['kind'],'source_id':row['id'],'institution_name':item.get('institution_name'),'business_name':business,'content':summary,'severity':severity,'status':severity})
            if watch_reason.strip():
                repo.insert_watchlist({'source_kind':row['kind'],'source_id':row['id'],'institution_name':item.get('institution_name'),'business_name':business,'content':watch_reason,'status':'watch'})
            log.info('analysis complete kind=%s id=%s severity=%s watch=%s',row['kind'],row['id'],severity,bool(watch_reason))
        except Exception as exc:
            repo.update_analysis(row['kind'],row['id'],'failed',None,None,f'{type(exc).__name__}: {str(exc)[:300]}')
            log.warning('analysis failed kind=%s id=%s type=%s',row['kind'],row['id'],type(exc).__name__)

async def main():
    await asyncio.to_thread(repo.init_schema)
    await asyncio.to_thread(repo.reset_stale_analysis)
    while True:
        if os.getenv('DATA_MODE','live').lower() != 'mock':
            await poll_once()
            await analyze_pending()
        await asyncio.sleep(POLL)
if __name__=='__main__': asyncio.run(main())
