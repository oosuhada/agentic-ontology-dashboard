import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  DatabaseZap,
  RefreshCw,
  TerminalSquare,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { getOperationsAgentReviewWorkflowRuns } from "../../../api";
import type {
  OperationsAgentReviewWorkflowRun,
  OperationsBootstrapModel,
} from "../api/operationsContracts";
import { OperationsState, formatTimestamp } from "../components/OperationsUi";

type RuntimeStatusFilter = "all" | OperationsAgentReviewWorkflowRun["status"];

const STATUS_FILTERS: Array<{ id: RuntimeStatusFilter; label: string }> = [
  { id: "all", label: "전체" },
  { id: "completed", label: "생성 완료" },
  { id: "partial", label: "대체 요약" },
  { id: "failed", label: "생성 실패" },
  { id: "running", label: "생성 중" },
];

const STATUS_LABEL: Record<OperationsAgentReviewWorkflowRun["status"], string> = {
  completed: "요약 생성 완료",
  partial: "대체 요약 사용",
  failed: "요약 생성 실패",
  running: "요약 생성 중",
};

function triggerLabel(value: string): string {
  if (value === "watcher" || value === "polling_watcher") return "자동 감시 생성";
  if (value === "manual_materialization") return "운영자 요청 생성";
  if (value === "ui_manual_regeneration") return "화면에서 다시 생성";
  return value || "실행 방식 미기록";
}

function engineLabel(value: string): string {
  if (value === "simple") return "기본 생성 흐름";
  if (value === "langgraph") return "LangGraph 실험 흐름";
  return value || "생성 흐름 미기록";
}

function historyWindowLabel(value: string | null): string {
  if (value === "24h") return "최근 24시간";
  if (value === "7d") return "최근 7일";
  if (value === "30d") return "최근 30일";
  return "기준 기간 미기록";
}

function datasetLabel(value: string | null): string {
  if (value === "fixture-compatibility") return "호환 기준 데이터";
  if (value === "dsv-canonical-v3-1") return "Canonical V3.1";
  return value || "데이터 기준 미기록";
}

function stageLabel(value: string | undefined): string {
  if (value === "started") return "처리 시작";
  if (value === "finished") return "처리 완료";
  if (value === "failed") return "처리 실패";
  return "단계 미기록";
}

function reasonLabel(value: string | null | undefined): string {
  if (!value) return "";
  if (value === "ProviderUnavailable") return "LLM 제공자 미연결";
  if (value === "summary_validation_failed") return "요약 검증 실패";
  if (value === "summary_not_materialized") return "저장된 요약 없음";
  if (value === "agent_review_summary_provider_disabled") return "AI 요약 제공자 비활성화";
  return value;
}

function runLine(
  run: OperationsAgentReviewWorkflowRun,
  assetLabels: Map<string, string>,
  eventLabels: Map<string, string>,
): string {
  const asset = run.asset_id ?? run.trace.materialization?.asset_id;
  const event = run.event_id ?? run.trace.materialization?.event_id;
  const assetText = typeof asset === "string"
    ? assetLabels.get(asset) ?? asset
    : "설비 미기록";
  const eventText = typeof event === "string"
    ? eventLabels.get(event) ?? event
    : "이벤트 미기록";
  return [
    formatTimestamp(run.updated_at),
    STATUS_LABEL[run.status],
    triggerLabel(run.trigger),
    engineLabel(run.engine),
    assetText,
    eventText,
    historyWindowLabel(run.history_window),
    stageLabel(run.trace.stage),
  ].join("  |  ");
}

function statusIcon(status: OperationsAgentReviewWorkflowRun["status"]) {
  if (status === "completed") return <CheckCircle2 size={15} />;
  if (status === "failed") return <AlertTriangle size={15} />;
  if (status === "running") return <Clock3 size={15} />;
  return <DatabaseZap size={15} />;
}

export function OperationsSystemAdminPage({
  model,
  refreshing,
  onRefresh,
}: {
  model: OperationsBootstrapModel;
  refreshing: boolean;
  onRefresh: () => void;
}) {
  const [runs, setRuns] = useState<OperationsAgentReviewWorkflowRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [statusFilter, setStatusFilter] = useState<RuntimeStatusFilter>("all");
  const [selectedRun, setSelectedRun] = useState<OperationsAgentReviewWorkflowRun | null>(null);

  const loadRuns = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await getOperationsAgentReviewWorkflowRuns({
        projectId: model.context.projectId,
        status: statusFilter === "all" ? null : statusFilter,
        limit: 100,
      });
      setRuns(response.items);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "AI 요약 처리 이력을 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }, [model.context.projectId, statusFilter]);

  useEffect(() => {
    void loadRuns();
  }, [loadRuns]);

  const filteredRuns = runs;
  const assetLabels = useMemo(
    () => new Map(model.assets.map((asset) => [asset.assetId, asset.displayName])),
    [model.assets],
  );
  const eventLabels = useMemo(
    () => new Map(model.events.map((event) => [
      event.eventId,
      `${event.scenarioId} · ${event.assetName}`,
    ])),
    [model.events],
  );
  const counts = useMemo(() => ({
    completed: runs.filter((run) => run.status === "completed").length,
    partial: runs.filter((run) => run.status === "partial").length,
    failed: runs.filter((run) => run.status === "failed").length,
    running: runs.filter((run) => run.status === "running").length,
  }), [runs]);

  return (
    <div className="operations-system-admin-page">
      <section className="operations-system-admin-hero" aria-label="시스템 관리자 로그 개요">
        <div>
          <span><TerminalSquare size={15} /> 시스템 관리자</span>
          <h2>AI 요약 처리 로그</h2>
          <p>자동 감시, 운영자 요청, 대체 요약, 검증 실패 이력을 프로젝트 단위로 조회합니다.</p>
        </div>
        <button
          type="button"
          className="operations-system-refresh"
          onClick={() => {
            onRefresh();
            void loadRuns();
          }}
          disabled={loading || refreshing}
        >
          <RefreshCw size={15} className={loading || refreshing ? "is-spinning" : ""} />
          새로고침
        </button>
      </section>

      <section className="operations-system-admin-summary" aria-label="AI 요약 처리 상태 요약">
        <div><span>전체 실행</span><strong>{runs.length}</strong></div>
        <div><span>완료</span><strong>{counts.completed}</strong></div>
        <div><span>부분 처리</span><strong>{counts.partial}</strong></div>
        <div><span>실패</span><strong>{counts.failed}</strong></div>
        <div><span>진행 중</span><strong>{counts.running}</strong></div>
      </section>

      <section className="operations-system-terminal" aria-label="AI 요약 처리 터미널 로그">
        <header>
          <div>
            <TerminalSquare size={15} />
            <strong>AI 요약 처리 이력</strong>
            <span>{model.context.projectName} · {model.context.workspaceName}</span>
          </div>
          <div className="operations-system-filter" role="tablist" aria-label="로그 상태 필터">
            {STATUS_FILTERS.map((filter) => (
              <button
                type="button"
                key={filter.id}
                role="tab"
                aria-selected={statusFilter === filter.id}
                className={statusFilter === filter.id ? "is-active" : ""}
                onClick={() => setStatusFilter(filter.id)}
              >
                {filter.label}
              </button>
            ))}
          </div>
        </header>

        {loading ? <OperationsState kind="loading" title="AI 요약 처리 이력 조회 중" detail="저장된 AI 요약 처리 이력을 읽고 있습니다." /> : null}
        {error ? <OperationsState kind="error" title="AI 요약 처리 이력 조회 실패" detail={error} onRetry={loadRuns} /> : null}
        {!loading && !error && filteredRuns.length ? (
          <div className="operations-system-log-list">
            {filteredRuns.map((run) => (
              <button
                type="button"
                key={run.workflow_run_id}
                className={`operations-system-log-line is-${run.status}`}
                onClick={() => setSelectedRun(run)}
              >
                <span>{statusIcon(run.status)}</span>
                <code>{runLine(run, assetLabels, eventLabels)}</code>
              </button>
            ))}
          </div>
        ) : null}
        {!loading && !error && !filteredRuns.length ? (
          <OperationsState kind="empty" title="표시할 로그가 없습니다" detail="선택한 상태 필터에 해당하는 AI 요약 처리 이력이 없습니다." />
        ) : null}
      </section>

      {selectedRun ? (
        <div className="operations-runtime-detail-layer">
          <button type="button" className="operations-runtime-detail-scrim" onClick={() => setSelectedRun(null)} aria-label="상세 닫기" />
          <section className="operations-runtime-detail-dialog" role="dialog" aria-modal="true" aria-label="AI 요약 처리 상세">
            <header>
              <TerminalSquare size={14} />
              <strong>AI 요약 처리 상세</strong>
              <button type="button" onClick={() => setSelectedRun(null)}>닫기</button>
            </header>
            <dl>
              <div><dt>처리 ID</dt><dd>{selectedRun.workflow_run_id}</dd></div>
              <div><dt>상태</dt><dd>{STATUS_LABEL[selectedRun.status]}</dd></div>
              <div><dt>실행 방식</dt><dd>{triggerLabel(selectedRun.trigger)}</dd></div>
              <div><dt>생성 흐름</dt><dd>{engineLabel(selectedRun.engine)}</dd></div>
              <div><dt>설비</dt><dd>{selectedRun.asset_id ? assetLabels.get(selectedRun.asset_id) ?? selectedRun.asset_id : "미기록"}</dd></div>
              <div><dt>이벤트</dt><dd>{selectedRun.event_id ? eventLabels.get(selectedRun.event_id) ?? selectedRun.event_id : "미기록"}</dd></div>
              <div><dt>데이터 기준</dt><dd>{datasetLabel(selectedRun.dataset_version_id)}</dd></div>
              <div><dt>조회 기간</dt><dd>{historyWindowLabel(selectedRun.history_window)}</dd></div>
              <div><dt>시작</dt><dd>{formatTimestamp(selectedRun.started_at)}</dd></div>
              <div><dt>완료</dt><dd>{selectedRun.completed_at ? formatTimestamp(selectedRun.completed_at) : "진행 중"}</dd></div>
              <div><dt>근거 지문</dt><dd>{selectedRun.source_sha256.slice(0, 12)}</dd></div>
              <div><dt>맥락 지문</dt><dd>{selectedRun.context_sha256.slice(0, 12)}</dd></div>
              <div className="is-wide"><dt>요약 저장 키</dt><dd>{selectedRun.summary_key}</dd></div>
              <div className="is-wide"><dt>처리 메모</dt><dd>{selectedRun.error_message ? `${reasonLabel(selectedRun.error_type)}: ${selectedRun.error_message}` : reasonLabel(selectedRun.trace.reason) || "특이사항 없음"}</dd></div>
            </dl>
            {selectedRun.trace.validation_errors?.length ? (
              <ul>
                {selectedRun.trace.validation_errors.map((item) => (
                  <li key={`${selectedRun.workflow_run_id}-${item}`}>{item}</li>
                ))}
              </ul>
            ) : null}
            <small>이 화면은 조회 전용입니다. 작업요청 생성, 승인, 재시도 실행은 제공하지 않습니다.</small>
          </section>
        </div>
      ) : null}
    </div>
  );
}
