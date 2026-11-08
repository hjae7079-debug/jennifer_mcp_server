import json
from app.analyzer import parse_analysis

def test_structured_analysis_maps_watchlist():
    raw=json.dumps({'summary':'요약 1\n요약 2','detail':'근거와 확인 항목','severity':'warning','watch_required':True,'watch_reason':'응답 지연 추이를 관찰해야 함'},ensure_ascii=False)
    summary,detail,severity,watch=parse_analysis(raw)
    assert summary.startswith('요약 1')
    assert severity=='warning'
    assert watch=='응답 지연 추이를 관찰해야 함'

def test_plain_text_does_not_infer_watchlist():
    summary,detail,severity,watch=parse_analysis('요약: 원본 응답\n상세: 추가 확인 필요')
    assert '원본 응답' in summary
    assert severity=='info'
    assert watch==''
