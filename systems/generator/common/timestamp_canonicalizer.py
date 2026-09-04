"""
timestamp_canonicalizer.py

담당 기능:
- 시계열 데이터프레임 내 타임스탬프 컬럼을 표준형(datetime64[ns])으로 정규화하고 NaT(유효하지 않은 시각) 발생 건수를 감지/오디팅하는 모듈.

입력:
- series(pd.Series): 정규화 대상 타임스탬프 데이터 시리즈
- col_name(str, optional): 로그 로깅용 컬럼명

출력:
- pd.Series: datetime64[ns] 타입으로 변환된 타임스탬프 시리즈

의존 모듈:
- pandas, logging

예외/경계 상황:
- errors="coerce"를 적용하여 잘못된 문자열이 포함되더라도 크래시 없이 NaT로 변환하고 경고 로그를 기록한다.

설계 원칙과의 연결:
- docs/architecture.md의 '시간 필드 Canonical Type 통일' 원칙에 따라 문자열 vs Timestamp 비교 불일치로 인한 라벨링 무효화를 방지한다.
"""

import logging
import pandas as pd

logger = logging.getLogger(__name__)


def canonicalize_timestamp_series(series: pd.Series, col_name: str = "timestamp") -> pd.Series:
    """
    타임스탬프 시리즈를 datetime64[ns] 표준형으로 정규화하고 NaT(유효하지 않은 시각) 발생 건수를 감사(Audit)한다.
    """
    if series is None or len(series) == 0:
        return series

    if pd.api.types.is_datetime64_any_dtype(series):
        return series

    dt_series = pd.to_datetime(series, errors="coerce")
    nat_count = int(dt_series.isna().sum())
    if nat_count > 0:
        logger.warning(f"[TimestampCanonicalizer] 컬럼 '{col_name}'에서 {nat_count}건의 유효하지 않은 타임스탬프가 감지되어 NaT로 변환되었습니다.")

    return dt_series
