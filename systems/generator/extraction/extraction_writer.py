"""
extraction_writer.py

담당 기능:
- 메인 학습 파이프라인과 완벽하게 격리된 참고용 정형화 원본 저장 모듈.
- 추출된 sources 데이터프레임을 PATHS.data_preprocessed / raw_extracted 디렉토리에 CSV 파일로 보존한다.

입력:
- sources(dict): 파싱 완료된 데이터프레임 딕셔너리
- plans(dict): 파일별 추출 계획 딕셔너리
- force_reanalyze(bool): 재작성 무시 여부

출력:
- None: 파일 영속화만 수행

의존 모듈:
- os, pandas: 디렉토리 생성 및 CSV 쓰기
- systems.generator.generator_config.PATHS: 전역 경로 레지스트리

예외/경계 상황:
- 파일 하나가 저장에 실패하더라도 전체 파이프라인에 영향을 주지 않도록 예외를 포착하여 경고 로그만 남기고 다른 파일 저장을 지속한다.

설계 원칙과의 연결:
- docs/architecture.md의 '비작업 산출물 장애 격리' 원칙에 따라 메인 파이프라인의 구동을 방해하지 않는다.
"""

import os
import logging
import pandas as pd
from systems.generator.generator_config import PATHS

logger = logging.getLogger(__name__)

RAW_EXTRACTED_DIR = PATHS.data_preprocessed / "raw_extracted"


def persist_raw_extracted(sources: dict, plans: dict, force_reanalyze: bool) -> None:
    """학습 파이프라인과 완전히 분리된 참고용 원본 추출 저장 단계."""
    try:
        RAW_EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.warning(f"[RawExtractedWriter] 디렉터리 생성 실패, 저장 단계를 건너뜁니다: {e}")
        return

    for key, df in sources.items():
        try:
            plan = plans.get(key, {})
            out_name = os.path.splitext(plan.get("filename", f"{key}.csv"))[0] + ".csv"
            out_path = RAW_EXTRACTED_DIR / out_name

            if out_path.exists() and not force_reanalyze:
                logger.info(f"[RawExtractedWriter] 캐시 존재, 재저장 생략: '{out_path}'")
                continue

            df.to_csv(out_path, index=False)
            logger.info(f"[RawExtractedWriter] 저장 완료: '{out_path}' ({len(df)} rows)")
        except Exception as e:
            logger.warning(f"[RawExtractedWriter] '{key}' 저장 실패 (건너뛰고 지속): {e}")
            continue
