import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

const API = '/api';
const nav = [
  ['dashboard','대시보드','▦'], ['incidents','장애분석','◈'], ['events','이벤트분석','◉'],
  ['detections','탐지내역','▤'], ['watchlist','관찰대상','◎'], ['integrations','연동 상태','⌘']
];
async function api(path, init={}) {
  const r = await fetch(`${API}${path}`, {headers:{'Content-Type':'application/json', ...(init.headers||{})}, ...init});
  const j = await r.json().catch(()=>({detail:`HTTP ${r.status}`}));
  if (!r.ok) throw new Error(j.detail || `HTTP ${r.status}`);
  return j;
}
function Badge({children,tone=''}) { return <span className={`badge ${tone}`}>{children}</span>; }
function Status({status,configured}) {
  if (configured === false) return <Badge tone="warn">이력 API 미설정</Badge>;
  if (status === 'analyzing' || status === 'queued' || status === 'pending') return <Badge tone="info">분석 중</Badge>;
  if (status === 'complete') return <Badge tone="ok">분석 완료</Badge>;
  if (status === 'failed') return <Badge tone="bad">분석 실패</Badge>;
  return <Badge>상태 확인 필요</Badge>;
}
function Empty({title,body}) { return <div className="empty"><span className="empty-mark">○</span><b>{title}</b><p>{body}</p></div>; }
function Title({eyebrow,title,meta,extra}) { return <div className="section-title"><div><div className="eyebrow">{eyebrow}</div><h2>{title}</h2></div><div className="section-extra">{meta&&<span className="muted">{meta}</span>}{extra}</div></div>; }
function HistoryCard({item,kind,configured,sourceError,sourcePending,sourceDetail,open}) {
  if (configured === false) return <div className="history-empty"><div className="empty-symbol">↗</div><b>{kind==='incident'?'장애':'이벤트'} 이력 API 연결 대기</b><p>실제 API URL·인증·응답 필드를 설정하면 최근 3건과 분석 요약이 표시됩니다.</p><Badge tone="warn">연동 전</Badge></div>;
  if (sourceError && !item) return <div className="history-empty"><div className="empty-symbol">!</div><b>이력 조회 실패 / 상태 확인 필요</b><p>{sourceDetail||'API 요청 실패 또는 응답 스키마 불일치입니다.'}</p><Badge tone="bad">조회 실패</Badge></div>;
  if (sourcePending && !item) return <div className="history-empty"><div className="empty-symbol">…</div><b>이력 조회 대기 / 상태 확인 필요</b><p>API는 설정되어 있으나 아직 성공/실패 결과가 확인되지 않았습니다. Worker 상태를 확인하세요.</p><Badge tone="info">조회 대기</Badge></div>;
  if (!item) return <div className="history-empty"><div className="empty-symbol">✓</div><b>발생 이력 없음</b><p>연동된 이력 API가 현재 항목을 반환하지 않았습니다.</p></div>;
  let summary = item.analysis_summary || (item.analysis_status==='analyzing'||item.analysis_status==='queued' ? '원본 근거를 확인하고 로컬 LLM 분석을 진행하고 있습니다.' : item.analysis_status==='failed' ? '분석 결과 생성에 실패했습니다. 서비스 상태와 로그를 확인하세요.' : '분석 요약 대기 중입니다.');
  return <button className="history-card" onClick={()=>open(kind,item.id)}>
    <div className="history-top"><code>{item.id}</code><div className="badges"><Status status={item.analysis_status} configured={configured}/>{sourceError&&<Badge tone="bad">조회 실패</Badge>}{sourcePending&&<Badge tone="info">조회 대기</Badge>}</div></div>
    <b className="history-title">{item.title||'제목 미제공'}</b>
    <div className="history-org">{item.institution_name||'기관명 미제공'} <span>·</span> {item.occurred_at ? new Date(item.occurred_at).toLocaleString('ko-KR') : '발생 시각 미제공'}</div>
    <p className="summary">{summary}</p><div className="history-link">상세 분석 보기 <span>→</span></div>
  </button>;
}
function DataTable({rows,type,open}) {
  if (!rows?.length) return <Empty title={type==='detections'?'탐지 결과 없음':'현재 관찰대상 없음'} body="실제 이력과 분석 결과가 연결되면 여기에 표시됩니다. 운영 데이터를 임의로 만들지 않습니다."/>;
  return <div className="table-scroll"><table><thead><tr><th>기관 / 업무</th><th>{type==='detections'?'탐지 내용':'관찰 사유 / 내용'}</th><th>원본 식별 키</th><th>상태</th></tr></thead><tbody>{rows.slice(0,5).map((r)=><tr key={`${r.source_kind||type}:${r.source_id||r.id}`} className={r.source_kind&&r.source_id?'clickrow':''} onClick={()=>r.source_kind&&r.source_id&&open(r.source_kind,r.source_id)}><td><b>{r.institution_name||'기관명 미제공'}</b><small>{r.business_name||'업무명 미제공'}</small></td><td className="content-cell">{r.content||'분석 내용 미제공'}</td><td><code>{r.source_id||r.id||'—'}</code><small>{r.source_kind||'—'}</small></td><td><Badge tone={r.status==='critical'?'bad':r.status==='watch'?'warn':''}>{r.status_label||r.status||'확인 필요'}</Badge></td></tr>)}</tbody></table></div>;
}
function Dashboard({data,open,refresh}) {
  const s=data?.summary||{}, src=data?.source_status||{}, inc=data?.incidents||{}, ev=data?.events||{};
  const kpis=[
    ['기관 수',s.institution_count??30,s.institution_is_estimate?'임시값 · 기관 기준 API 미연동':'기관 기준 API', '⌂'],
    ['업무 수',s.business_count??140,s.business_is_estimate?'임시값 · 업무 기준 API 미연동':'업무 기준 API','▣'],
    ['장애 건 수',s.incident_count??0,src.incidents?.configured?'장애 이력 API 기준':'이력 API 연결 대기','!'],
    ['이벤트 건 수',s.event_count??0,src.events?.configured?'이벤트 이력 API 기준':'이력 API 연결 대기','⌁']
  ];
  return <div className="stack">
    <div className="page-heading"><div><div className="eyebrow">OVERVIEW / LOCAL AIOPS</div><h1>통합분석 대시보드</h1><p>장애와 이벤트의 근거를 수집하고 로컬 LLM 분석 상태를 확인합니다.</p></div><button className="btn" onClick={refresh}>↻ 새로고침</button></div>
    {data?.mode==='mock'&&<div className="notice warning"><b>모의 데이터 모드</b><span>표시된 내용은 테스트용이며 실제 운영 데이터가 아닙니다.</span></div>}
    <div className="notice"><span className="notice-dot"></span><div><b>실데이터 연동 상태</b><span>기관/업무 기준 API와 장애/이벤트 이력 API가 미설정된 경우 실제 데이터처럼 채우지 않습니다.</span></div><button className="linkbtn" onClick={()=>open('page','integrations')}>연동 상태 확인 →</button></div>
    <div className="kpis">{kpis.map(([label,value,hint,icon])=><div className="kpi" key={label}><div className="kpi-label">{label}<span className="kpi-icon">{icon}</span></div><div className="kpi-value">{Number(value).toLocaleString('ko-KR')}</div><div className="kpi-hint">{hint}</div></div>)}</div>
    <div className="cols"><section className="panel"><Title eyebrow="PRIORITY 01" title="장애분석" meta="최근 3건" extra={<Badge tone="bad">최우선 분석</Badge>}/><div className="history-list">{(inc.items||[]).slice(0,3).map(x=><HistoryCard key={x.id} item={x} kind="incident" configured={src.incidents?.configured} sourceError={src.incidents?.ok===false} sourcePending={src.incidents?.configured&&src.incidents?.ok==null} sourceDetail={src.incidents?.detail} open={open}/>)}{!(inc.items||[]).length&&<HistoryCard kind="incident" configured={src.incidents?.configured} sourceError={src.incidents?.ok===false} sourcePending={src.incidents?.configured&&src.incidents?.ok==null} sourceDetail={src.incidents?.detail} open={open}/>}</div>{inc.error&&<p className="error">장애 이력 조회 실패: {inc.error}</p>}</section>
    <section className="panel"><Title eyebrow="PRIORITY 02" title="이벤트분석" meta="최근 3건" extra={<Badge tone="info">우선 분석</Badge>}/><div className="history-list">{(ev.items||[]).slice(0,3).map(x=><HistoryCard key={x.id} item={x} kind="event" configured={src.events?.configured} sourceError={src.events?.ok===false} sourcePending={src.events?.configured&&src.events?.ok==null} sourceDetail={src.events?.detail} open={open}/>)}{!(ev.items||[]).length&&<HistoryCard kind="event" configured={src.events?.configured} sourceError={src.events?.ok===false} sourcePending={src.events?.configured&&src.events?.ok==null} sourceDetail={src.events?.detail} open={open}/>}</div>{ev.error&&<p className="error">이벤트 이력 조회 실패: {ev.error}</p>}</section></div>
    <div className="cols"><section className="panel"><Title eyebrow="AI FINDINGS" title="탐지내역" meta={`최근 ${Math.min(data?.detections?.items?.length||0,5)}건`}/><DataTable rows={data?.detections?.items} type="detections" open={open}/></section><section className="panel"><Title eyebrow="WATCH ITEMS" title="관찰대상" meta={`최근 ${Math.min(data?.watchlist?.items?.length||0,5)}건`}/><DataTable rows={data?.watchlist?.items} type="watchlist" open={open}/></section></div>
    <footer className="foot"><span>로컬 우선 · 외부 LLM API 미사용</span><span>API 상태: {data?.api_status||'확인 중'}</span></footer>
  </div>;
}
function ListPage({page,data,open}) {
  const incident=page==='incidents', event=page==='events', detection=page==='detections';
  const title=incident?'장애분석':event?'이벤트분석':detection?'탐지내역':'관찰대상';
  const rows=incident?data?.incidents?.items:event?data?.events?.items:detection?data?.detections?.items:data?.watchlist?.items;
  const configured=incident?data?.source_status?.incidents?.configured:data?.source_status?.events?.configured;
  const [q,setQ]=useState(''); const filtered=(rows||[]).filter(r=>`${r.id||''} ${r.institution_name||''} ${r.title||''} ${r.business_name||''} ${r.content||''}`.toLowerCase().includes(q.toLowerCase()));
  return <div className="stack"><div className="page-heading"><div><div className="eyebrow">RECORDS</div><h1>{title}</h1><p>실제 API에서 반환된 레코드만 표시합니다.</p></div></div>{(incident||event)&&!configured&&<div className="notice warning">이력 API가 설정되지 않았습니다. 연결 후 실제 레코드가 표시됩니다.</div>}<section className="panel"><div className="toolbar"><input value={q} onChange={e=>setQ(e.target.value)} placeholder="ID, 기관, 업무, 제목 검색"/><span className="muted">{filtered.length}건</span></div>{incident||event?<div className="history-list">{filtered.map(x=><HistoryCard key={x.id} item={x} kind={incident?'incident':'event'} configured={configured} sourceError={(incident?data?.source_status?.incidents?.ok:data?.source_status?.events?.ok)===false} sourcePending={(incident?data?.source_status?.incidents?.configured:data?.source_status?.events?.configured)&&(incident?data?.source_status?.incidents?.ok:data?.source_status?.events?.ok)==null} sourceDetail={(incident?data?.source_status?.incidents?.detail:data?.source_status?.events?.detail)} open={open}/>)}{!filtered.length&&<HistoryCard kind={incident?'incident':'event'} configured={configured} sourceError={(incident?data?.source_status?.incidents?.ok:data?.source_status?.events?.ok)===false} sourcePending={(incident?data?.source_status?.incidents?.configured:data?.source_status?.events?.configured)&&(incident?data?.source_status?.incidents?.ok:data?.source_status?.events?.ok)==null} sourceDetail={(incident?data?.source_status?.incidents?.detail:data?.source_status?.events?.detail)} open={open}/>}</div>:<DataTable rows={filtered} type={page} open={open}/>}</section></div>;
}
function Detail({kind,id,back}) {
  const [data,setData]=useState(null),[err,setErr]=useState(''),[tab,setTab]=useState('overview');
  useEffect(()=>{let live=true;api(`/items/${encodeURIComponent(kind)}/${encodeURIComponent(id)}`).then(x=>live&&setData(x)).catch(e=>live&&setErr(e.message));return()=>{live=false}},[kind,id]);
  const item=data?.item; const tabs=[['overview','개요'],['timeline','타임라인'],['web','WEB'],['was','WAS'],['db','DB'],['ai','AI 분석'],['actions','조치 이력'],['report','보고서']];
  return <div className="stack"><button className="back" onClick={back}>← 목록으로 돌아가기</button><div className="page-heading"><div><div className="eyebrow">{kind==='incident'?'INCIDENT DETAIL':'EVENT DETAIL'}</div><h1>{item?.title||id}</h1><p>{item?.institution_name||'기관명 미제공'} · <code>{id}</code></p></div>{item&&<Status status={item.analysis_status} configured={data?.source_configured}/>}</div>{err&&<div className="notice danger">상세 조회 실패: {err}</div>}{!item&&!err&&<section className="panel"><Empty title="상세 정보 조회 중" body="원본 이력과 분석 결과를 조회하고 있습니다."/></section>}{item&&<><section className="panel detail-summary"><div><div className="eyebrow">AI SUMMARY</div><h2>분석 요약</h2><p>{item.analysis_summary||'분석 요약이 아직 등록되지 않았습니다.'}</p></div><div className="detail-meta"><small>발생 시각</small><b>{item.occurred_at?new Date(item.occurred_at).toLocaleString('ko-KR'):'미제공'}</b><small>분석 상태</small><b>{item.analysis_status}</b></div></section><div className="tabs">{tabs.map(([k,v])=><button key={k} className={tab===k?'active':''} onClick={()=>setTab(k)}>{v}</button>)}</div><section className="panel detail-content"><h3>{tabs.find(x=>x[0]===tab)?.[1]}</h3>{tab==='overview'?<pre>{JSON.stringify(item.source_payload||{},null,2)}</pre>:tab==='ai'?<p className="prewrap">{item.analysis_detail||'분석 결과가 아직 등록되지 않았습니다.'}</p>:<Empty title="연동 대기" body="이 상세 데이터 소스가 연결되면 실제 응답을 표시합니다. 임의의 값을 생성하지 않습니다."/>}</section></>}</div>;
}
function Integrations({data}) {
  const [result,setResult]=useState(null),[err,setErr]=useState(''),[busy,setBusy]=useState(false); const s=data?.source_status||{};
  const discover=async()=>{setBusy(true);setErr('');try{setResult(await api('/integrations/jennifer/discover',{method:'POST'}))}catch(e){setErr(e.message)}finally{setBusy(false)}};
  const rows=[['장애 이력 API',s.incidents,'장애 ID·기관명·제목 필드 매핑'],['이벤트 이력 API',s.events,'이벤트 ID·기관명·제목 필드 매핑'],['기관/업무 기준 API',s.institutions,'KPI 임시값 30/140을 실제 값으로 교체'],['Jennifer (뷰서버 Open API)',s.jennifer,'자체 MCP 컨테이너가 뷰서버 REST를 GET으로 호출. 경로 확정 후 활성화'],['Dify Workflow',s.dify,'Workflow API Key와 입출력 매핑'],['Ollama / Qwen3-14B',s.ollama,'로컬 추론 모델'],['BGE-M3',s.embeddings,'로컬 임베딩 모델']];
  return <div className="stack"><div className="page-heading"><div><div className="eyebrow">INTEGRATION STATUS</div><h1>연동 상태</h1><p>미설정·조회 실패·정상 연결을 구분합니다. 스키마를 확인하지 않은 도구는 호출하지 않습니다.</p></div><button className="btn" onClick={discover} disabled={busy}>{busy?'탐색 중…':'Jennifer 도구 스키마 탐색'}</button></div><section className="panel">{rows.map(([label,v,desc])=><div className="integration-row" key={label}><div><b>{label}</b><p>{desc}</p></div>{v?.configured?<Badge tone={v.ok===false?'bad':v.ok===true?'ok':'info'}>{v.ok===false?'조회 실패':v.ok===true?'연결 확인':'설정됨'}</Badge>:<Badge tone="warn">미설정</Badge>}</div>)}</section>{err&&<div className="notice danger">{err}</div>}{result&&<section className="panel"><h2>Jennifer MCP tools/list 결과</h2><p className="muted">탐색 전용 결과입니다. 도구 호출은 자동 실행하지 않습니다.</p><pre>{JSON.stringify(result,null,2)}</pre></section>}<div className="notice"><b>보안 원칙</b><span>Jennifer는 읽기 전용·최소권한으로 연결합니다. 설정 변경·재시작·삭제 도구는 허용하지 않습니다.</span></div></div>;
}
function App(){
  const [theme,setTheme]=useState(localStorage.getItem('aiops-theme')||'light'); const [page,setPage]=useState('dashboard'); const [detail,setDetail]=useState(null); const [data,setData]=useState(null); const [loading,setLoading]=useState(true); const [err,setErr]=useState(''); const [updated,setUpdated]=useState(null);
  useEffect(()=>{document.documentElement.dataset.theme=theme;localStorage.setItem('aiops-theme',theme)},[theme]);
  const refresh=async()=>{setLoading(true);setErr('');try{setData(await api('/dashboard'));setUpdated(new Date())}catch(e){setErr(e.message)}finally{setLoading(false)}};
  useEffect(()=>{refresh();const t=setInterval(refresh,30000);return()=>clearInterval(t)},[]);
  const open=(kind,id)=>{if(kind==='page'){setPage(id);setDetail(null);history.pushState({},'',id==='dashboard'?'/':`/${id}`)}else{setDetail({kind,id});setPage('detail');history.pushState({},'',`/detail/${kind}/${encodeURIComponent(id)}`)}};
  const back=()=>{setDetail(null);setPage('dashboard');history.pushState({},'','/')};
  useEffect(()=>{const pop=()=>{const p=location.pathname.split('/').filter(Boolean);if(p[0]==='detail'&&p.length>=3){setDetail({kind:p[1],id:decodeURIComponent(p.slice(2).join('/'))});setPage('detail')}else{setDetail(null);setPage(nav.some(x=>x[0]===p[0])?p[0]:'dashboard')}};window.addEventListener('popstate',pop);pop();return()=>window.removeEventListener('popstate',pop)},[]);
  const label=nav.find(x=>x[0]===page)?.[1]||(page==='detail'?'상세 분석':'대시보드');
  return <div className="shell"><aside className="sidebar"><div className="brand"><div className="brand-mark">A</div><div><b>AIOps</b><small>통합분석 플랫폼</small></div></div><div className="side-label">WORKSPACE</div><nav>{nav.map(([k,l,i])=><button key={k} className={`nav-item ${page===k?'active':''}`} onClick={()=>open('page',k)}><span className="nav-icon">{i}</span><span>{l}</span>{k==='integrations'&&<i/>}</button>)}</nav><div className="sidebar-bottom"><div className="local-status"><span className="pulse"/><div><b>로컬 실행 모드</b><small>외부 LLM API 미사용</small></div></div><small className="version">AIOps Dashboard · v0.3.1</small></div></aside>
  <main className="main"><header className="topbar"><div className="crumb">AIOps <span>/</span> {label}</div><div className="top-actions"><small>{updated?`갱신 ${updated.toLocaleTimeString('ko-KR')}`:'상태 확인 중'}</small><button className="theme-toggle" onClick={()=>setTheme(theme==='light'?'dark':'light')}>{theme==='light'?'☾ 어두운 테마':'☀ 밝은 테마'}</button><div className="avatar">OP</div></div></header><div className="content">{err&&<div className="notice danger"><b>API 연결 실패</b><span>{err}. FastAPI·DB 상태를 확인하세요.</span><button className="linkbtn" onClick={refresh}>재시도</button></div>}{loading&&!data?<div className="loading"><div className="spinner"/><b>운영 상태를 불러오는 중</b></div>:page==='dashboard'?<Dashboard data={data} open={open} refresh={refresh}/>:['incidents','events','detections','watchlist'].includes(page)?<ListPage page={page} data={data} open={open}/>:page==='integrations'?<Integrations data={data}/>:page==='detail'&&detail?<Detail kind={detail.kind} id={detail.id} back={back}/>:<Dashboard data={data} open={open} refresh={refresh}/>}</div></main></div>
}
createRoot(document.getElementById('root')).render(<App/>);
