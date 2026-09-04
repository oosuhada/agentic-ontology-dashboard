export const ASSET_FIELD_LABELS: Record<string, string> = {
  "CNC-S01-L01-01": "1구역 · 1셀 · CNC 가공기 1",
  "CNC-S04-L04-01": "4구역 · 4셀 · CNC 가공기 1",
  "CNC-S01-L04-03": "1구역 · 4셀 · CNC 가공기 3",
  "CNC-S04-L02-03": "4구역 · 2셀 · CNC 가공기 3",
  "CNC-S03-L01-03": "3구역 · 1셀 · CNC 가공기 3",
  "CNC-S02-L02-02": "2구역 · 2셀 · CNC 가공기 2",
  "CNC-S04-L05-01": "4구역 · 5셀 · CNC 가공기 1",
  "CNC-S04-L04-02": "4구역 · 4셀 · CNC 가공기 2",
};

export const SENSOR_FIELD_LABELS: Record<string, string> = {
  rotation_raw: "회전 평균",
  vibration_raw: "진동 평균",
  pressure_raw: "압력 평균",
  voltage_raw: "전압",
  current_raw: "전류",
  relative_vibration_z: "진동 이상도",
  spindle_vibration: "스핀들 진동",
  air_pressure: "공기 압력",
  flow_rate: "유량",
  air_temperature_k: "흡입 공기 온도",
  process_temperature_k: "가공 온도",
  rotational_speed_rpm: "주축 회전수",
  torque_nm: "토크",
  tool_wear_min: "공구 마모",
  mechanical_power_w: "모터 출력",
  power_w: "모터 출력",
  overstrain_index: "과부하 누적 지표",
  overstrain_load: "과부하 누적 지표",
  temperature_difference_k: "공정-공기 온도차",
  temperature_gap_k: "공정-공기 온도차",
  generator_failure_score: "모델 산출 위험 점수",
  model_selected_threshold: "위험 판정 기준값",
  asset_criticality_adjustment: "설비 중요도 보정",
  generator_model_artifact_manifest: "적용 모델 릴리스",
};

const FEATURE_WINDOW_SUFFIX = /(?:(?:_(?:1h|6h|12h|24h|7d|30d)_(?:max_abs|abs_max|abs_mean|change|max|min|mean|std|last))|(?:_(?:current|abs_current)))$/;

const FEATURE_WINDOW_LABELS: Array<[RegExp, string]> = [
  [/_abs_current$/, "현재 절대값"],
  [/_current$/, "현재값"],
  [/_1h_mean$/, "1시간 평균"],
  [/_6h_mean$/, "6시간 평균"],
  [/_6h_abs_mean$/, "6시간 절대평균"],
  [/_6h_(?:max_abs|abs_max)$/, "6시간 최대 절대값"],
  [/_6h_max$/, "6시간 최대값"],
  [/_6h_min$/, "6시간 최소값"],
  [/_6h_std$/, "6시간 변동폭"],
  [/_6h_change$/, "6시간 변화량"],
  [/_12h_mean$/, "12시간 평균"],
  [/_24h_mean$/, "24시간 평균"],
  [/_7d_mean$/, "7일 평균"],
  [/_30d_mean$/, "30일 평균"],
];

function normalizedFeatureKey(value: string): string {
  return value.replace(FEATURE_WINDOW_SUFFIX, "");
}

export const EVENT_FIELD_LABELS: Record<string, string> = {
  "EVT-GS-001": "1구역 1셀 정상 관찰",
  "EVT-GS-002": "4구역 4셀 공구 마모 점검",
  "EVT-GS-003": "1구역 4셀 열 해소 점검",
  "EVT-GS-004": "4구역 2셀 구동부 과부하 긴급 검토",
  "EVT-GS-005": "3구역 1셀 복합 원인 점검",
  "EVT-GS-006": "2구역 2셀 저신뢰 관측 확인",
  "EVT-GS-007": "4구역 5셀 센서 데이터 확인",
  "EVT-GS-008": "4구역 4셀 보고서 생성 경로 확인",
};

export const FIELD_FACTOR_LABELS: Record<string, { item: string; symptom: string }> = {
  rotation_raw: { item: "회전 평균 확인", symptom: "회전 관측 변동" },
  vibration_raw: { item: "진동 평균 확인", symptom: "진동 증가" },
  pressure_raw: { item: "압력 평균 확인", symptom: "압력 변동" },
  air_temperature_k: { item: "흡입 공기 온도 확인", symptom: "주변 온도 조건 변화" },
  process_temperature_k: { item: "가공부 열 축적 확인", symptom: "공정 온도 상승" },
  rotational_speed_rpm: { item: "주축 회전수 확인", symptom: "회전수 이상" },
  torque_nm: { item: "구동 토크 확인", symptom: "토크 상승" },
  tool_wear_min: { item: "공구 사용 시간 확인", symptom: "공구 사용 시간 누적" },
  mechanical_power_w: { item: "모터 출력 확인", symptom: "모터 출력 부하 상승" },
  power_w: { item: "모터 출력 확인", symptom: "모터 출력 부하 상승" },
  overstrain_index: { item: "프레스 과부하 확인", symptom: "과부하 누적" },
  overstrain_load: { item: "프레스 과부하 확인", symptom: "과부하 누적" },
  temperature_difference_k: { item: "공정-공기 온도차 확인", symptom: "열 해소 불균형" },
  temperature_gap_k: { item: "공정-공기 온도차 확인", symptom: "열 해소 불균형" },
  generator_failure_score: { item: "모델 산출 위험 점수", symptom: "예측 위험도 상승" },
  model_selected_threshold: { item: "위험 판정 기준값", symptom: "현재 위험 점수와 비교하는 기준" },
  asset_criticality_adjustment: { item: "설비 중요도 보정", symptom: "설비 중요도 반영" },
  generator_model_artifact_manifest: { item: "적용 모델 릴리스", symptom: "승인된 모델 근거 연결" },
};

export const FAILURE_TYPE_LABELS: Record<string, string> = {
  failure_risk: "일반 고장 위험",
  none: "특이 고장 유형 없음",
  power_or_overstrain_failure: "구동부 과부하 의심",
  tool_wear_failure: "공구/금형 마모 의심",
  heat_dissipation_failure: "냉각/열 해소 이상 의심",
  invalid_sensor_data: "센서 데이터 품질 확인",
  multi_factor_risk: "복합 원인 의심",
  uncertain: "고장 유형 불확실",
  unavailable: "고장 유형 근거 부족",
};

const PRODUCTION_IMPACT_LABELS: Record<string, string> = {
  none: "영향 없음",
  low: "낮음",
  medium: "중간",
  high: "높음",
};

const REVIEW_PRIORITY_LABELS: Record<string, string> = {
  immediate: "즉시 검토",
  high: "높음",
  medium: "중간",
  low: "낮음",
};

interface DisplayAssetLike {
  assetId: string;
  displayName?: string | null;
}

interface DisplayEventLike {
  eventId?: string | null;
  assetId: string;
  assetName?: string | null;
}

interface DisplayFactorLike {
  feature: string;
  label?: string | null;
}

export function displayAssetName(asset: DisplayAssetLike | null | undefined): string {
  if (!asset) return "선택된 설비 없음";
  const mapped = ASSET_FIELD_LABELS[asset.assetId];
  if (mapped) return mapped;
  const runtime = asset.assetId.match(/^(CNC|CMP)-S(\d+)-L(\d+)-(\d+)$/i);
  if (runtime) {
    const [, kind, site, line, slot] = runtime;
    const equipment = kind.toUpperCase() === "CMP" ? "공기압축기" : "CNC 가공기";
    return `${Number(site)}구역 · ${Number(line)}셀 · ${equipment} ${Number(slot)}`;
  }
  return asset.displayName ?? asset.assetId;
}

export function displayAssetShortName(asset: DisplayAssetLike | null | undefined): string {
  if (!asset) return "-";
  const runtime = asset.assetId.match(/^(CNC|CMP)-S\d+-L\d+-(\d+)$/i);
  if (runtime) {
    const [, kind, slot] = runtime;
    return kind.toUpperCase() === "CMP" ? "압축기" : `CNC ${Number(slot)}`;
  }
  const mappedName = displayAssetName(asset);
  const unitSuffix = mappedName.match(/(\d+)호기$/)?.[1];
  if (unitSuffix) return `${Number(unitSuffix)}호기`;
  const mSeriesSuffix = asset.assetId.match(/^M-(\d+)$/)?.[1];
  if (mSeriesSuffix) return `${Number(mSeriesSuffix)}호기`;
  const trailingNumber = asset.assetId.match(/(\d+)$/)?.[1];
  return trailingNumber ? `${Number(trailingNumber)}호기` : mappedName;
}

export function displayEventAssetName(event: DisplayEventLike): string {
  return displayAssetName({ assetId: event.assetId, displayName: event.assetName });
}

export function displayEventLabel(event: Pick<DisplayEventLike, "eventId"> | string | null | undefined): string {
  const eventId = typeof event === "string" ? event : event?.eventId;
  if (!eventId) return "이벤트 미선택";
  return EVENT_FIELD_LABELS[eventId] ?? eventId;
}

export function displaySensorLabel(key: string, fallback?: string | null): string {
  const normalized = normalizedFeatureKey(key);
  return SENSOR_FIELD_LABELS[key] ?? SENSOR_FIELD_LABELS[normalized] ?? fallback ?? normalized.replaceAll("_", " ");
}

export function displaySensorFactorLabel(key: string, fallback?: string | null): string {
  const base = displaySensorLabel(key, fallback);
  const windowLabel = FEATURE_WINDOW_LABELS.find(([pattern]) => pattern.test(key))?.[1] ?? null;
  return windowLabel ? `${base} · ${windowLabel}` : base;
}

export function displayInspectionAssociation(value?: string | null): string {
  if (!value) return "점검 방법 확인 필요";
  if (value === "inspection_candidate") return "모델 근거 기반 점검 후보";
  if (value === "inspection_required") return "현장 점검 필요";
  return humanizeOperationalText(value.replaceAll("_", " "));
}

export function displayExplanationMethod(value?: string | null): string | null {
  if (!value) return null;
  if (value.includes("proxy_attribution") || value.includes("attribution")) return "모델 기여도 분석";
  if (value.includes("shap")) return "모델 영향도 분석";
  return null;
}

export function humanizeOperationalText(value: string): string {
  return value
    .replaceAll("Canonical", "확인된")
    .replaceAll("WorkOrder", "작업 요청")
    .replaceAll("Replay", "재현 분석")
    .replace(/[A-Za-z][A-Za-z0-9_]*(?:_[A-Za-z0-9]+){1,}/g, (token) => {
      const normalized = normalizedFeatureKey(token);
      const mapped = SENSOR_FIELD_LABELS[token] ?? SENSOR_FIELD_LABELS[normalized];
      if (mapped) return mapped;
      if (token === "failure_risk") return "일반 고장 위험";
      return token;
    });
}

export function displayAssetType(value?: string | null): string {
  if (!value) return "설비 유형 미제공";
  if (value.toLowerCase().includes("compressor")) return "공기압축기";
  if (value.toLowerCase().includes("cnc")) return "CNC 가공기";
  return value;
}

export function displayLineLabel(value?: string | null): string {
  if (!value) return "위치 확인 필요";
  const match = value.match(/S(\d+)\s*\/\s*S\d+-L(\d+)/i) ?? value.match(/S(\d+)-L(\d+)/i);
  if (match) return `${Number(match[1])}구역 · ${Number(match[2])}셀`;
  const simple = value.match(/^S(\d+)$/i);
  if (simple) return `${Number(simple[1])}구역`;
  return value;
}

export function displayAssignee(value?: string | null): string {
  if (!value || /unassigned|policy review/i.test(value)) return "미배정";
  return value;
}

export function displayCriticality(value?: string | null): string {
  if (value === "high") return "높음";
  if (value === "medium") return "중간";
  if (value === "low") return "낮음";
  return value || "확인 필요";
}

export function fieldFactorItem(factor: DisplayFactorLike): string {
  const normalized = normalizedFeatureKey(factor.feature);
  return FIELD_FACTOR_LABELS[normalized]?.item ?? displaySensorLabel(factor.feature, factor.label);
}

export function fieldFactorSymptom(factor: DisplayFactorLike): string {
  const normalized = normalizedFeatureKey(factor.feature);
  return FIELD_FACTOR_LABELS[normalized]?.symptom ?? displaySensorLabel(factor.feature, factor.label);
}

export function fieldFactorLocation(factor: Pick<DisplayFactorLike, "feature">): string {
  void factor;
  return "점검 위치 근거 미제공";
}

export function fieldFailureLabel(value: string): string {
  return FAILURE_TYPE_LABELS[value] ?? value;
}

export function displayProductionImpact(value?: string | null): string {
  if (!value) return "생산 영향 수준 미제공";
  return PRODUCTION_IMPACT_LABELS[value] ?? value;
}

export function displayReviewPriority(value?: string | null): string {
  if (!value) return "검토 우선순위 미제공";
  return REVIEW_PRIORITY_LABELS[value] ?? value;
}

const REPORT_TYPE_LABELS: Record<string, string> = {
  "inspection-summary": "점검 결과 요약",
  "operations-decision": "운영 판단 보고",
  "executive-brief": "경영진 운영 브리프",
  "maintenance-effect": "정비 효과 비교",
  "weekly-risk": "주간 운영 리스크",
};

export function displayReportType(value?: string | null): string {
  if (!value) return "보고 유형 확인 필요";
  return REPORT_TYPE_LABELS[value] ?? "업무 보고";
}

export function displayArtifactKind(value?: string | null): string {
  if (!value) return "근거 묶음 확인 필요";
  if (value.startsWith("pm-report:")) return "현재 Case 보고서 초안";
  if (value.startsWith("RESULT#")) return "선택 Case 예측 근거";
  if (value.startsWith("result-artifact://")) return "예측 결과 근거";
  return "연결된 기술 근거";
}

export function displayDataSource(value?: string | null): string {
  if (!value) return "연결된 운영 데이터";
  const normalized = value.toLowerCase();
  if (normalized.includes("wall-clock-live") || normalized.includes("live")) return "실시간 설비 관측 데이터";
  if (normalized.includes("canonical")) return "검증된 기준 관측 데이터";
  if (normalized.includes("presentation") || normalized.includes("demo")) return "시연용 고정 관측 데이터";
  return "연결된 설비 관측 데이터";
}

export function displayModelRelease(value?: string | null): string {
  if (!value) return "적용 모델 확인 필요";
  const normalized = value.toLowerCase();
  if (normalized.includes("cnc") && normalized.includes("random-forest")) return "CNC 고장 위험 예측 모델 v3";
  if (normalized.includes("compressor")) return "공기압축기 고장 위험 예측 모델";
  if (normalized.includes("logistic") || normalized.includes("logreg")) return "기준 고장 위험 예측 모델";
  return "배포 승인된 고장 위험 예측 모델";
}
