import { useState } from "react";
import {
  AlertTriangle,
  ClipboardCheck,
  Clock3,
  DatabaseZap,
  Gauge,
  RotateCcw,
  ShieldCheck,
  Volume2,
  Wrench,
  Zap,
} from "lucide-react";
import { displayAssetName, displayAssetShortName } from "../displayLabels";

const statusMeta = {
  critical: { label: "위험", tone: "critical", sentence: "즉시 점검이 필요한 위험 신호" },
  warning: { label: "경고", tone: "warning", sentence: "우선순위 점검 후보" },
  attention: { label: "주의", tone: "attention", sentence: "추가 관찰 필요" },
  normal: { label: "정상", tone: "normal", sentence: "특이 위험 신호 없음" },
  data_quality_hold: { label: "데이터 확인", tone: "hold", sentence: "데이터 확인 후 판단" },
} as const;

const reportText = {
  inspectionEyebrow: "점검 요청 보고서",
  reportTypeLabel: "보고서 종류",
  inspectionReportType: "예지보전 점검 요청",
  generationMethod: "규칙 기반 생성",
};

const featureDisplayMap: Record<string, { label: string; checkLabel: string; plainReason: string; category: string }> = {
  rotation_raw_6h_mean: {
    label: "회전 상태 평균값",
    checkLabel: "Backend 점검 항목 계약 미연결",
    plainReason: "이 항목은 모델의 주요 위험 근거입니다. 구체적인 현장 점검 위치와 방법은 Backend Evidence 또는 maintenance recommendation 계약 연결 후 표시합니다.",
    category: "회전 계통",
  },
  rotation_raw_6h_abs_mean: {
    label: "회전 변동 크기",
    checkLabel: "Backend 점검 항목 계약 미연결",
    plainReason: "이 항목은 모델의 주요 위험 근거입니다. 구체적인 현장 점검 위치와 방법은 Backend Evidence 또는 maintenance recommendation 계약 연결 후 표시합니다.",
    category: "회전 계통",
  },
  rotation_raw_6h_std: {
    label: "회전 불안정성",
    checkLabel: "Backend 점검 항목 계약 미연결",
    plainReason: "이 항목은 모델의 주요 위험 근거입니다. 구체적인 현장 점검 위치와 방법은 Backend Evidence 또는 maintenance recommendation 계약 연결 후 표시합니다.",
    category: "회전 계통",
  },
  pressure_raw_6h_abs_mean: {
    label: "압력 변동 크기",
    checkLabel: "Backend 점검 항목 계약 미연결",
    plainReason: "이 항목은 모델의 주요 위험 근거입니다. 구체적인 현장 점검 위치와 방법은 Backend Evidence 또는 maintenance recommendation 계약 연결 후 표시합니다.",
    category: "압력 계통",
  },
  pressure_raw_current: {
    label: "현재 압력",
    checkLabel: "Backend 점검 항목 계약 미연결",
    plainReason: "이 항목은 모델의 주요 위험 근거입니다. 구체적인 현장 점검 위치와 방법은 Backend Evidence 또는 maintenance recommendation 계약 연결 후 표시합니다.",
    category: "압력 계통",
  },
  vibration_raw_6h_mean: {
    label: "진동 평균값",
    checkLabel: "Backend 점검 항목 계약 미연결",
    plainReason: "이 항목은 모델의 주요 위험 근거입니다. 구체적인 현장 점검 위치와 방법은 Backend Evidence 또는 maintenance recommendation 계약 연결 후 표시합니다.",
    category: "진동 계통",
  },
  vibration_raw_6h_std: {
    label: "진동 불안정성",
    checkLabel: "Backend 점검 항목 계약 미연결",
    plainReason: "이 항목은 모델의 주요 위험 근거입니다. 구체적인 현장 점검 위치와 방법은 Backend Evidence 또는 maintenance recommendation 계약 연결 후 표시합니다.",
    category: "진동 계통",
  },
  voltage_raw_6h_mean: {
    label: "전압 평균값",
    checkLabel: "Backend 점검 항목 계약 미연결",
    plainReason: "이 항목은 모델의 주요 위험 근거입니다. 구체적인 현장 점검 위치와 방법은 Backend Evidence 또는 maintenance recommendation 계약 연결 후 표시합니다.",
    category: "전기 계통",
  },
};

const sensorDisplayMap: Record<string, { label: string; plainNote: string }> = {
  rotation_raw: { label: "회전 상태", plainNote: "회전 계통의 최근 평균 관측값" },
  pressure_raw: { label: "압력", plainNote: "압축기 압력의 최근 평균 관측값" },
  vibration_raw: { label: "진동", plainNote: "진동 센서의 최근 평균 관측값" },
  voltage_raw: { label: "전압", plainNote: "전압 센서의 최근 평균 관측값" },
};

const sourceFieldLabels: Record<string, { label: string; description: string }> = {
  "model_prediction.status_grade": { label: "위험 상태 판단", description: "모델이 이 설비를 위험, 경고, 주의, 정상 중 어디로 봤는지입니다." },
  "model_prediction.probability": { label: "위험 예측 확률", description: "향후 24시간 안에 고장 위험이 있다고 본 정도입니다." },
  "model_prediction.confidence": { label: "예측 신뢰도", description: "예측 판단이 한쪽으로 얼마나 뚜렷하게 기울었는지 보여주는 보조 정보입니다." },
  "sensor_evidence.window.start": { label: "센서 확인 시작 시각", description: "위험 판단에 사용한 센서 데이터의 시작 시각입니다." },
  "sensor_evidence.window.end": { label: "센서 확인 종료 시각", description: "위험 판단에 사용한 센서 데이터의 마지막 시각입니다." },
  "sensor_evidence.window_rows": { label: "사용한 센서 데이터 수", description: "이번 판단에 포함된 센서 기록 개수입니다." },
  "top_factors[0..2]": { label: "위험을 크게 올린 상위 근거", description: "모델이 위험 판단에 가장 크게 반영한 센서 패턴 3개입니다." },
  "sensor_evidence.sensors.rotation_raw": { label: "회전 상태 센서 기록", description: "회전부 속도 저하와 흔들림을 확인하기 위해 사용한 센서 기록입니다." },
  "sensor_evidence.sensors": { label: "센서 기록 묶음", description: "압력, 회전, 진동, 전압 등 설비 상태를 보여주는 최근 센서 기록입니다." },
};

const inspectionReport = {
  assetId: "CMP-S03-L03-01",
  displayName: "공기압축기 03구역 03라인 1호기",
  locationLabel: "03구역 / 03라인",
  assetTypeLabel: "공기압축기",
  observedAt: "2026-08-29 23:00",
  horizon: "24시간",
  status: "critical" as keyof typeof statusMeta,
  probability: 0.824661,
  confidence: 0.649322,
  evidenceLabel: "공기압축기 03구역 03라인 1호기의 예측 근거 묶음",
  predictionLabel: "2026년 8월 29일 오후 11시 기준 예측 결과",
  datasetLabel: "AI4I 기반 합성 예지보전 데이터셋 v3.1",
  sensorWindowLabel: "8월 28일 오후 11시 10분 ~ 8월 29일 오후 11시",
  sensorWindowSummary: "최근 약 24시간 동안 수집된 센서 데이터 144건을 기준으로 산출했습니다.",
  targets: [
    { rank: 1, feature: "rotation_raw_6h_mean", contributionLabel: "매우 높음" },
    { rank: 2, feature: "rotation_raw_6h_abs_mean", contributionLabel: "높음" },
    { rank: 3, feature: "rotation_raw_6h_std", contributionLabel: "높음" },
  ],
  sensors: [
    { key: "rotation_raw", current: 420.1058, average: 455.2, deltaLabel: "34.9 낮음", deltaTone: "down", zScoreLabel: "평소 변동폭의 2.9배 낮음", interpretation: "평소보다 크게 낮아 우선 확인이 필요합니다." },
    { key: "pressure_raw", current: 96.3931, average: 100.0, deltaLabel: "3.6 낮음", deltaTone: "down", zScoreLabel: "평소 변동폭의 0.8배 낮음", interpretation: "평소 변동 범위 안의 낮은 변화입니다." },
    { key: "vibration_raw", current: 39.8073, average: 36.8, deltaLabel: "3.0 높음", deltaTone: "up", zScoreLabel: "평소 변동폭의 1.6배 높음", interpretation: "평소보다 다소 높아 함께 확인합니다." },
    { key: "voltage_raw", current: 175.0854, average: 176.0, deltaLabel: "0.9 낮음", deltaTone: "neutral", zScoreLabel: "평소 변동폭의 0.2배 낮음", interpretation: "평소 범위에 가까운 변화입니다." },
  ],
  evidenceCards: [
    { id: "model-risk", groupLabel: "모델 예측 결과", title: "위험 상태 등급", value: "위험", description: "모델이 이 설비를 즉시 점검이 필요한 위험 상태로 분류했습니다.", rawFields: ["model_prediction.status_grade", "model_prediction.probability", "model_prediction.confidence"] },
    { id: "sensor-window", groupLabel: "센서 데이터 범위", title: "최근 센서 관측 범위", value: "센서 데이터 144건", description: "8월 28일 오후 11시 10분부터 8월 29일 오후 11시까지의 센서 데이터 144건을 사용했습니다. 약 24시간 기준입니다.", rawFields: ["sensor_evidence.window.start", "sensor_evidence.window.end", "sensor_evidence.window_rows"] },
    { id: "risk-factors", groupLabel: "주요 위험 근거", title: "회전 계통 위험 신호", value: "회전 상태 평균값, 회전 변동 크기, 회전 불안정성", description: "회전 관련 센서 패턴이 위험 예측에 크게 기여했습니다.", rawFields: ["top_factors[0..2]", "sensor_evidence.sensors.rotation_raw"] },
  ],
};

const inspectionAssetOptions = Array.from({ length: 20 }, (_, index) => {
  const unit = index + 1;
  const assetId = `CMP-S03-L03-${String(unit).padStart(2, "0")}`;
  const statusPattern = ["critical", "warning", "normal", "data_quality_hold", "attention", "normal"] as const;
  const status = unit === 1 ? "critical" : unit === 2 ? "warning" : unit === 5 ? "attention" : statusPattern[index % statusPattern.length];
  const probability = status === "critical"
    ? Math.max(0.71, 0.86 - (index % 3) * 0.03)
    : status === "warning"
      ? Math.max(0.56, 0.66 - (index % 4) * 0.02)
      : status === "attention"
        ? Math.max(0.32, 0.43 - (index % 3) * 0.025)
        : status === "data_quality_hold"
          ? null
          : Math.max(0.08, 0.18 - (index % 4) * 0.015);
  const targetSet = status === "warning"
    ? [
      { rank: 1, feature: "pressure_raw_6h_abs_mean", contributionLabel: "높음" },
      { rank: 2, feature: "vibration_raw_6h_std", contributionLabel: "중간" },
      { rank: 3, feature: "pressure_raw_current", contributionLabel: "중간" },
    ]
    : status === "attention" || status === "normal"
      ? [
        { rank: 1, feature: "vibration_raw_6h_mean", contributionLabel: "중간" },
        { rank: 2, feature: "voltage_raw_6h_mean", contributionLabel: "낮음" },
        { rank: 3, feature: "rotation_raw_6h_std", contributionLabel: "낮음" },
      ]
      : inspectionReport.targets;
  return {
    ...inspectionReport,
    assetId,
    displayName: `공기압축기 03구역 03라인 ${unit}호기`,
    status,
    probability,
    confidence: status === "data_quality_hold" ? null : Math.max(0.58, 0.78 - (index % 5) * 0.035),
    targets: targetSet,
  };
});

const targetIcons: Record<string, typeof RotateCcw> = {
  rotation_raw_6h_mean: RotateCcw,
  rotation_raw_6h_abs_mean: Gauge,
  rotation_raw_6h_std: Volume2,
  pressure_raw_6h_abs_mean: Gauge,
  pressure_raw_current: Gauge,
  vibration_raw_6h_mean: Volume2,
  vibration_raw_6h_std: Volume2,
  voltage_raw_6h_mean: Zap,
};

function percent(value: number | null) {
  return value === null ? "-" : `${Math.round(value * 100)}%`;
}

function formatOneDecimal(value: number) {
  return Number(value).toFixed(1);
}

function featureLabel(feature: string) {
  return featureDisplayMap[feature]?.label ?? feature;
}

function featureCheckLabel(feature: string) {
  return featureDisplayMap[feature]?.checkLabel ?? "관련 설비 상태 확인";
}

function featureReason(feature: string) {
  return featureDisplayMap[feature]?.plainReason ?? "모델이 주요 위험 근거로 선택한 항목입니다.";
}

function inspectionLocation(feature: string) {
  void feature;
  return { range: "점검 위치 근거 미제공", note: "Backend 점검 위치 계약 연결 후 표시", className: "loc-generic" };
}

function contributionTone(label: string) {
  if (label === "매우 높음") return "critical";
  if (label === "높음") return "high";
  if (label === "중간") return "medium";
  return "low";
}

function sensorMeta(key: string) {
  return sensorDisplayMap[key] ?? { label: key, plainNote: "센서 관측값" };
}

function sourceFieldMeta(field: string) {
  return sourceFieldLabels[field] ?? { label: "추가 근거 정보", description: "이 판단에 사용된 내부 추적 정보입니다." };
}

function Kpi({ icon: Icon, label, value, detail, tone = "" }: { icon: typeof Gauge; label: string; value: string; detail: string; tone?: string }) {
  return (
    <article className={`kpi ${tone}`}>
      <Icon size={18} />
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

function StatusBadge({ status }: { status: keyof typeof statusMeta }) {
  const meta = statusMeta[status];
  return <span className={`status-badge ${meta.tone}`}>{meta.label}</span>;
}

export function OperationsInspectionReportPage() {
  const [activeAssetId, setActiveAssetId] = useState("CMP-S03-L03-02");
  const activeAsset = inspectionAssetOptions.find((asset) => asset.assetId === activeAssetId) ?? inspectionAssetOptions[0];
  const riskFactorLabels = activeAsset.targets.map((target) => featureLabel(target.feature)).join(", ");
  const primaryCategory = featureDisplayMap[activeAsset.targets[0]?.feature]?.category ?? "주요 계통";
  const activeReport = {
    ...inspectionReport,
    ...activeAsset,
    evidenceLabel: `${activeAsset.displayName}의 예측 근거 묶음`,
    evidenceCards: inspectionReport.evidenceCards.map((card) => {
      if (card.id === "model-risk") {
        return { ...card, value: statusMeta[activeAsset.status].label, description: `모델이 이 설비를 ${statusMeta[activeAsset.status].sentence}로 분류했습니다.` };
      }
      if (card.id === "risk-factors") {
        return { ...card, title: `${primaryCategory} 위험 신호`, value: riskFactorLabels, description: `${primaryCategory} 관련 센서 패턴이 이번 예측 근거에 포함됐습니다.`, rawFields: ["top_factors[0..2]", "sensor_evidence.sensors"] };
      }
      return card;
    }),
  };
  const quickSwitchAssets = inspectionAssetOptions
    .filter((asset) => asset.locationLabel === activeAsset.locationLabel && asset.status !== "normal")
    .slice(0, 6);

  return (
    <div className="operations-inspection-report-panel" data-testid="operations-static-report">
      <header className="topbar">
        <div>
          <span>{reportText.inspectionEyebrow}</span>
          <h1>예지보전 점검 요청 보고서</h1>
          <p>모델 예측과 근거 자료를 바탕으로 현장 확인이 필요한 항목만 분리해 보여줍니다.</p>
        </div>
        <div className="report-meta">
          <small>{reportText.reportTypeLabel}</small>
          <strong>{reportText.inspectionReportType}</strong>
          <span>{reportText.generationMethod}</span>
        </div>
      </header>

      <section className="inspection-hero">
        <div>
          <span>대상 설비</span>
          <h2>{activeReport.displayName}</h2>
          <p>{activeReport.assetTypeLabel} · {activeReport.locationLabel}</p>
          <p>내부 ID {activeReport.assetId}</p>
          <p>{activeReport.observedAt} 기준 · {activeReport.horizon} 예측</p>
        </div>
        <div className="asset-switcher">
          <label htmlFor="inspection-asset-select">다른 설비 보기</label>
          <select id="inspection-asset-select" value={activeAssetId} onChange={(event) => setActiveAssetId(event.target.value)}>
            {inspectionAssetOptions.map((asset) => (
              <option key={asset.assetId} value={asset.assetId}>{displayAssetName(asset)} · {statusMeta[asset.status].label}</option>
            ))}
          </select>
          <div className="asset-switcher-chips" aria-label="주요 설비 바로 보기">
            {quickSwitchAssets.map((asset) => (
              <button key={asset.assetId} type="button" className={asset.assetId === activeAssetId ? "active" : ""} onClick={() => setActiveAssetId(asset.assetId)} title={`${displayAssetName(asset)} · ${statusMeta[asset.status].label} · 위험 예측 확률 ${percent(asset.probability)}`}>
                {displayAssetShortName(asset)}
              </button>
            ))}
          </div>
        </div>
        <StatusBadge status={activeReport.status} />
      </section>

      <section className="kpis report-kpis" aria-label="점검 요청 핵심 지표">
        <Kpi icon={AlertTriangle} label="위험 예측 확률" value={percent(activeReport.probability)} detail="고장 확정 아님" tone="warm" />
        <Kpi icon={Gauge} label="예측 신뢰도" value={percent(activeReport.confidence)} detail="예측 판단의 확실한 정도" />
        <Kpi icon={Clock3} label="예측 기간" value={activeReport.horizon} detail={activeReport.observedAt} />
        <Kpi icon={ShieldCheck} label="판단 상태" value="미확정" detail="현장 확인 후 승격" />
      </section>

      <details className="formula-disclosure">
        <summary>위험 예측 확률이 만들어지는 방식 보기</summary>
        <div>
          <strong>위험도 = 기준 위험도 + Σ(센서 패턴 × 중요하게 본 정도)</strong>
          <strong>위험 예측 확률 = 위험도를 0~100%로 바꾼 값</strong>
          <dl>
            <div><dt>기준 위험도</dt><dd>모델이 판단을 시작할 때 사용하는 기본 기준입니다.</dd></div>
            <div><dt>센서 패턴</dt><dd>최근 센서 흐름을 요약한 값입니다.</dd></div>
            <div><dt>중요하게 본 정도</dt><dd>모델이 어떤 센서 흐름을 더 중요하게 봤는지입니다.</dd></div>
            <div><dt>위험도를 올린 정도</dt><dd>해당 센서 흐름이 최종 위험 판단에 보탠 정도입니다.</dd></div>
          </dl>
          <p>이 리포트 화면은 확률을 새로 계산하지 않고, 모델이 이미 계산해 둔 위험 예측 결과를 보여줍니다.</p>
        </div>
      </details>

      <div className="inspection-layout">
        <section className="report-panel manager-brief">
          <div className="panel-heading compact"><div><span>MANAGER BLOCK</span><h2>관리자 판단</h2></div></div>
          <p className="lead-text">{activeReport.displayName}는 향후 {activeReport.horizon} 내 위험 예측 확률이 {percent(activeReport.probability)}로 {statusMeta[activeReport.status].label} 상태입니다. 아래 항목은 저장되는 결정이 아니라 관리자가 검토할 후속 판단 후보입니다.</p>
          <div className="decision-stack">
            <article><ClipboardCheck size={16} /><div><strong>현장 점검 요청</strong><span>현장 담당자가 회전, 진동, 압력 상태를 확인해야 합니다.</span></div></article>
            <article><AlertTriangle size={16} /><div><strong>생산 영향 시 정지 검토</strong><span>자동 정지가 아니라, 생산 영향이 큰 경우 검토 안건으로 올립니다.</span></div></article>
            <article><DatabaseZap size={16} /><div><strong>근거 품질 확인</strong><span>센서 데이터 범위와 근거 패키지가 판단에 충분한지 확인합니다.</span></div></article>
          </div>
        </section>

        <section className="report-panel">
          <div className="panel-heading compact"><div><span>ENGINEER BLOCK</span><h2>점검 항목</h2></div></div>
          <div className="equipment-sketch" aria-label="공기압축기 설비 참고도">
            <div className="compressor-visual" aria-hidden="true">
              <span className="vibration-zone" /><span className="pipe pipe-1" /><span className="pipe pipe-2" /><span className="pipe pipe-3" /><span className="pipe pipe-4" />
              <span className="motor">모터</span><span className="shaft drive">축/벨트</span><span className="pump">압축부</span><span className="valve">배관/밸브<br />압력계</span><span className="tank">압력 탱크</span><span className="power-unit">전원부</span>
              {activeReport.targets.map((target) => <mark key={target.feature} className={`callout ${inspectionLocation(target.feature).className}`}>{target.rank}</mark>)}
            </div>
            <div>
              <strong>공기압축기 설비 참고도</strong>
              <ul className="sketch-legend">
                {activeReport.targets.map((target) => {
                  const location = inspectionLocation(target.feature);
                  return <li key={target.feature}><b>{target.rank}</b>{location.range}: {location.note}</li>;
                })}
              </ul>
            </div>
          </div>
          <div className="target-list">
            {activeReport.targets.map((target) => {
              const TargetIcon = targetIcons[target.feature] ?? Wrench;
              return (
                <article key={target.feature}>
                  <b>{target.rank}</b><i><TargetIcon size={18} /></i>
                  <div><strong>{featureCheckLabel(target.feature)}</strong><p>{featureReason(target.feature)}</p></div>
                  <span className={`target-severity ${contributionTone(target.contributionLabel)}`}>{target.contributionLabel}</span>
                </article>
              );
            })}
          </div>
        </section>
      </div>

      <div className="inspection-layout lower">
        <section className="map-panel">
          <div className="panel-heading"><div><span>SENSOR EVIDENCE</span><h2>센서 참고값</h2></div><span className="status-badge attention">최근 144건</span></div>
          <div className="sensor-window"><strong>{activeReport.sensorWindowLabel}</strong><p>{activeReport.sensorWindowSummary}</p></div>
          <div className="sensor-table">
            {activeReport.sensors.map((sensor) => {
              const meta = sensorMeta(sensor.key);
              return <div key={sensor.key}><span>{meta.label}</span><strong>현재값: {formatOneDecimal(sensor.current)}</strong><small>{meta.plainNote}</small><div className={`sensor-delta ${sensor.deltaTone}`}><b>평균값: {formatOneDecimal(sensor.average)}</b><em>{sensor.deltaLabel}</em></div><div className={`variation-note ${sensor.deltaTone}`}><strong>평균 대비: {sensor.zScoreLabel}</strong><p>{sensor.interpretation}</p></div></div>;
            })}
          </div>
        </section>

        <aside className="report-panel">
          <div className="panel-heading compact"><div><span>EVIDENCE TRACE</span><h2>근거 추적</h2></div></div>
          <div className="evidence-card-list">
            {activeReport.evidenceCards.map((card) => (
              <article key={card.id}>
                <span>{card.groupLabel}</span><strong>{card.title}: {card.value}</strong><p>{card.description}</p>
                <details><summary>사용한 근거 보기</summary><div className="source-field-list">{card.rawFields.map((field) => { const meta = sourceFieldMeta(field); return <div key={field}><strong>{meta.label}</strong><p>{meta.description}</p></div>; })}</div></details>
              </article>
            ))}
          </div>
          <div className="trace-meta"><span>근거 묶음</span><strong>{activeReport.evidenceLabel}</strong><span>예측 기록</span><strong>{activeReport.predictionLabel}</strong><span>사용 데이터</span><strong>{activeReport.datasetLabel}</strong></div>
        </aside>
      </div>

      <section className="priority-panel warning-strip">
        <ShieldCheck size={18} />
        <p>이 리포트는 점검 요청 산출물입니다. 고장 발생, 고장 원인, 정비 필요 여부, 자동 설비 정지를 확정하지 않습니다.</p>
      </section>
    </div>
  );
}
