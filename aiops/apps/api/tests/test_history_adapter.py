import pytest
from app.adapters.history import normalize_history, records_from_json, HistoryAdapterError

def test_incident_normalization():
    row=normalize_history('incident',{'incident_id':'IC-DEMO-1','institution_name':'테스트 기관','title':'테스트 제목'})
    assert row['id']=='IC-DEMO-1' and row['kind']=='incident'

def test_event_aliases():
    row=normalize_history('event',{'id':'EV-DEMO-1','institution':'기관','subject':'이벤트'})
    assert row['title']=='이벤트'

def test_missing_required_fields_fails_closed():
    with pytest.raises(HistoryAdapterError): normalize_history('incident',{'title':'id 없음'})

def test_unknown_envelope_fails_closed():
    with pytest.raises(HistoryAdapterError): records_from_json({'result':{'values':[]}})
