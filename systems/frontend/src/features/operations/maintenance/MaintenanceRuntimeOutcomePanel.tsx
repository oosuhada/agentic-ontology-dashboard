import { useMemo, useState } from "react";
import {
  recordMaintenanceValueRealization,
  type MaintenanceEventLineageReadModel,
} from "../../../api";
import type { OperationsRoleLens } from "../api/operationsContracts";

function localize(english: boolean, ko: string, en: string): string {
  return english ? en : ko;
}
function optionalNumber(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function latest<T>(items: T[]): T | null {
  return items.length ? items[items.length - 1] : null;
}

function deliveryLabel(
  status: string,
  english: boolean,
): string {
  switch (status) {
    case "processed":
      return localize(english, "시뮬레이션 반영 전달 완료", "Simulation delivery completed");
    case "dead_letter":
      return localize(english, "시뮬레이션 반영 실패", "Simulation delivery failed");
    case "retry":
      return localize(english, "시뮬레이션 반영 재시도 중", "Retrying simulation delivery");
    case "processing":
      return localize(english, "시뮬레이션 반영 전달 중", "Delivering simulation update");
    default:
      return localize(english, "시뮬레이션 반영 대기", "Simulation update pending");
  }
}

export function MaintenanceRuntimeOutcomePanel({
  projectId,
  workspaceId,
  role,
  lineage,
  postMaintenancePredictionAvailable,
  estimatedDowntimeMinutes,
  locale,
  onChanged,
}: {
  projectId: string;
  workspaceId: string;
  role: OperationsRoleLens;
  lineage: MaintenanceEventLineageReadModel | null;
  postMaintenancePredictionAvailable: boolean;
  estimatedDowntimeMinutes: number | null;
  locale: "ko-KR" | "en-US";
  onChanged?: () => void;
}) {
  const english = locale === "en-US";
  const delivery = latest(lineage?.runtime_deliveries ?? []);
  const maintenanceEvent = latest(lineage?.maintenance_events ?? []);
  const realization = latest(lineage?.value_realizations ?? []);
  const [actualDowntimeMinutes, setActualDowntimeMinutes] = useState("");
  const [predictedLossExposureMinor, setPredictedLossExposureMinor] = useState("");
  const [realizedAvoidedExposureMinor, setRealizedAvoidedExposureMinor] = useState("");
  const [basisText, setBasisText] = useState("");
  const [recurrenceObserved, setRecurrenceObserved] = useState<"" | "yes" | "no">("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const basis = useMemo(
    () => basisText.split(/\n|,/).map((item) => item.trim()).filter(Boolean),
    [basisText],
  );
  const actualDowntime = optionalNumber(actualDowntimeMinutes);
  const predictedLoss = optionalNumber(predictedLossExposureMinor);
  const realizedAvoided = optionalNumber(realizedAvoidedExposureMinor);
  const canRecord = Boolean(
    role === "process_manager"
    && maintenanceEvent
    && postMaintenancePredictionAvailable
    && !realization
    && basis.length
    && (actualDowntime !== null || realizedAvoided !== null || recurrenceObserved !== ""),
  );

  const record = async () => {
    if (!canRecord || !maintenanceEvent) return;
    setSubmitting(true);
    setError(null);
    try {
      await recordMaintenanceValueRealization(
        projectId,
        workspaceId,
        maintenanceEvent.maintenance_event_id,
        {
          predicted_downtime_minutes: estimatedDowntimeMinutes,
          actual_downtime_minutes: actualDowntime,
          predicted_loss_exposure_minor: predictedLoss === null ? null : Math.round(predictedLoss),
          realized_avoided_exposure_minor: realizedAvoided === null ? null : Math.round(realizedAvoided),
          currency: "KRW",
          recurrence_observed: recurrenceObserved === "" ? null : recurrenceObserved === "yes",
          basis,
          measured_at: new Date().toISOString(),
        },
      );
      onChanged?.();
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : localize(english, "실현 가치 근거를 기록하지 못했습니다.", "Unable to record realized-value evidence."),
      );
    } finally {
      setSubmitting(false);
    }
  };

  if (!delivery && !(role === "process_manager" && maintenanceEvent && postMaintenancePredictionAvailable)) {
    return null;
  }

  return (
    <div className="operations-runtime-outcome-stack">
      {delivery ? (
        <section
          className="operations-runtime-delivery-status"
          data-status={delivery.delivery_status}
          aria-label={localize(english, "시뮬레이션 반영 상태", "Simulation delivery status")}
        >
          <div>
            <small>{localize(english, "정비 업무 상태와 별도", "Separate from maintenance work status")}</small>
            <strong>{deliveryLabel(delivery.delivery_status, english)}</strong>
          </div>
          <span>{delivery.attempt_count ? `${localize(english, "시도", "Attempt")} ${delivery.attempt_count}` : ""}</span>
          {delivery.overlay_branch_id ? <small>Overlay · {delivery.overlay_branch_id}</small> : null}
          {delivery.last_error ? <small className="operations-cost-error">{delivery.last_error}</small> : null}
        </section>
      ) : null}

      {role === "process_manager" && maintenanceEvent && postMaintenancePredictionAvailable ? (
        realization ? (
          <section className="operations-value-realization" aria-label={localize(english, "실현 가치", "Realized value")}>
            <header>
              <strong>{localize(english, "실현 가치 검증", "Value realization")}</strong>
              <span>{localize(english, "Actual 근거 연결됨", "Actual evidence linked")}</span>
            </header>
            <dl>
              <div>
                <dt>{localize(english, "위험 변화", "Risk change")}</dt>
                <dd>{realization.before_risk_score == null || realization.after_risk_score == null ? "-" : `${(realization.before_risk_score * 100).toFixed(1)}% → ${(realization.after_risk_score * 100).toFixed(1)}%`}</dd>
              </div>
              <div>
                <dt>{localize(english, "예상 / 실제 정지", "Expected / actual downtime")}</dt>
                <dd>{realization.predicted_downtime_minutes == null ? "-" : `${realization.predicted_downtime_minutes}m`} / {realization.actual_downtime_minutes == null ? "-" : `${realization.actual_downtime_minutes}m`}</dd>
              </div>
              <div>
                <dt>{localize(english, "검증된 회피 노출", "Verified avoided exposure")}</dt>
                <dd>{realization.realized_avoided_exposure_minor == null ? localize(english, "미확정", "Not confirmed") : `${realization.realized_avoided_exposure_minor.toLocaleString()} ${realization.currency}`}</dd>
              </div>
              <div>
                <dt>{localize(english, "재발", "Recurrence")}</dt>
                <dd>{realization.recurrence_observed == null ? localize(english, "미확인", "Not checked") : realization.recurrence_observed ? localize(english, "관측됨", "Observed") : localize(english, "관측 없음", "Not observed")}</dd>
              </div>
            </dl>
            <small>{localize(english, "절감 실적은 연결된 운영·재무 actual 근거만 표시합니다.", "Savings are shown only when backed by linked operational or financial actuals.")}</small>
          </section>
        ) : (
          <fieldset className="operations-value-realization" disabled={submitting}>
            <legend>{localize(english, "실현 가치 actual 연결", "Link realized-value actuals")}</legend>
            <p>{localize(english, "정비 후 Result가 승격되었습니다. 모델 점수만으로 절감을 추정하지 않고 운영·재무 actual을 연결해 확정합니다.", "A post-maintenance Result has been promoted. Link operational or financial actuals instead of inferring savings from the model score.")}</p>
            <div className="operations-inspection-grid">
              <label className="operations-field">
                <span>{localize(english, "Case 예상 정지 (분)", "Case expected downtime (min)")}</span>
                <input type="number" value={estimatedDowntimeMinutes ?? ""} readOnly />
              </label>
              <label className="operations-field">
                <span>{localize(english, "실제 정지 (분)", "Actual downtime (min)")}</span>
                <input type="number" min="0" value={actualDowntimeMinutes} onChange={(event) => setActualDowntimeMinutes(event.target.value)} />
              </label>
              <label className="operations-field">
                <span>{localize(english, "Case 예상 손실 노출 (원)", "Case loss exposure (KRW)")}</span>
                <input type="number" min="0" value={predictedLossExposureMinor} onChange={(event) => setPredictedLossExposureMinor(event.target.value)} />
              </label>
              <label className="operations-field">
                <span>{localize(english, "검증된 회피 노출 (원)", "Verified avoided exposure (KRW)")}</span>
                <input type="number" min="0" value={realizedAvoidedExposureMinor} onChange={(event) => setRealizedAvoidedExposureMinor(event.target.value)} />
              </label>
              <label className="operations-field">
                <span>{localize(english, "동일 이상 재발", "Recurrence observed")}</span>
                <select value={recurrenceObserved} onChange={(event) => setRecurrenceObserved(event.target.value as "" | "yes" | "no")}>
                  <option value="">{localize(english, "미확인", "Not checked")}</option>
                  <option value="no">{localize(english, "관측 없음", "Not observed")}</option>
                  <option value="yes">{localize(english, "관측됨", "Observed")}</option>
                </select>
              </label>
            </div>
            <label className="operations-field">
              <span>{localize(english, "Actual 근거 참조", "Actual evidence references")}</span>
              <textarea value={basisText} onChange={(event) => setBasisText(event.target.value)} placeholder={localize(english, "ERP/MES/CMMS URI 또는 감사 가능한 참조를 줄바꿈으로 입력", "Enter auditable ERP/MES/CMMS references, one per line")} />
            </label>
            <button type="button" className="operations-button secondary" disabled={!canRecord} onClick={() => void record()}>
              {submitting ? localize(english, "기록 중", "Recording") : localize(english, "Actual 근거로 실현 가치 기록", "Record value from actual evidence")}
            </button>
            {error ? <small className="operations-cost-error">{error}</small> : null}
          </fieldset>
        )
      ) : null}
    </div>
  );
}
