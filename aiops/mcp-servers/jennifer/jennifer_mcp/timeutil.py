"""시간 변환 규칙 (설계 4.2 실측 제약 반영).

- 조회 구간은 epoch ms 로 보냅니다.
- status/* 는 시작·끝이 분 단위 정시여야 하므로 분 단위로 맞춥니다.
- transaction/time 은 구간 60초 이하만 허용합니다.
- dbsearch 응답의 time 은 Java Date 문자열이므로 epoch ms 로 바꿉니다.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9), "KST")
MINUTE_MS = 60_000

_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M")


def to_epoch_ms(value: str | int | float) -> int:
    """epoch ms(정수/숫자 문자열) 또는 'YYYY-MM-DD HH:MM[:SS]'(KST) 를 epoch ms 로 바꿉니다."""
    if isinstance(value, bool):
        raise ValueError("시간 값이 올바르지 않음")
    if isinstance(value, (int, float)):
        v = int(value)
    else:
        s = str(value).strip()
        if re.fullmatch(r"\d{10,13}", s):
            v = int(s)
        else:
            v = None
            for fmt in _FORMATS:
                try:
                    dt = datetime.strptime(s, fmt).replace(tzinfo=KST)
                    v = int(dt.timestamp() * 1000)
                    break
                except ValueError:
                    continue
            if v is None:
                raise ValueError(f"시간 형식을 해석할 수 없음: {s!r} (epoch ms 또는 'YYYY-MM-DD HH:MM')")
    if v < 10_000_000_000:  # 초 단위로 들어온 경우
        v *= 1000
    return v


def align_minute_range(start, end) -> tuple[int, int]:
    """시작은 분 내림, 끝은 분 올림. 같으면 끝을 1분 뒤로."""
    s = to_epoch_ms(start)
    e = to_epoch_ms(end)
    if e < s:
        raise ValueError("끝 시각이 시작 시각보다 이릅니다")
    s = s - (s % MINUTE_MS)
    if e % MINUTE_MS:
        e = e - (e % MINUTE_MS) + MINUTE_MS
    if e == s:
        e = s + MINUTE_MS
    return s, e


def check_max_window(start_ms: int, end_ms: int, max_ms: int) -> None:
    if end_ms - start_ms > max_ms:
        raise ValueError(f"조회 구간이 너무 깁니다: {(end_ms - start_ms)//1000}초 > {max_ms//1000}초")


_JAVA_DATE = re.compile(
    r"^[A-Za-z]{3} (?P<mon>[A-Za-z]{3}) (?P<day>\d{1,2}) (?P<hms>\d{2}:\d{2}:\d{2}) (?P<tz>[A-Z]{2,5}) (?P<year>\d{4})$"
)
_TZ_OFFSETS = {"KST": 9, "UTC": 0, "GMT": 0}


def java_date_to_epoch_ms(value: str) -> int:
    """'Tue Oct 14 10:00:00 KST 2026' 형식을 epoch ms 로 바꿉니다."""
    m = _JAVA_DATE.match(str(value).strip())
    if not m:
        raise ValueError(f"Java Date 형식이 아님: {value!r}")
    tz = m.group("tz")
    if tz not in _TZ_OFFSETS:
        raise ValueError(f"알 수 없는 시간대: {tz}")
    dt = datetime.strptime(f"{m.group('year')} {m.group('mon')} {m.group('day')} {m.group('hms')}",
                           "%Y %b %d %H:%M:%S")
    dt = dt.replace(tzinfo=timezone(timedelta(hours=_TZ_OFFSETS[tz])))
    return int(dt.timestamp() * 1000)
