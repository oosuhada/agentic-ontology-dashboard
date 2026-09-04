import { lazy, Suspense } from "react";
import { StatusBadge } from "../../components/StatusBadge";
import { agentPath, navigate } from "../../routing";
import { OntologyLifecycleLoader } from "../../ui/foundry/OntologyLifecycleLoader";
import { useI18n } from "../../ui/i18n/I18nProvider";
import type {
  AppRole,
  BlockType,
  Evidence,
  EventSummary,
  FollowUp,
  Layout,
  Report,
  Role,
  UIBlock,
} from "../../types";
import type { DashboardDraftResponse } from "../planner/types";
import type { RoleWorkspaceData } from "../roles/types";
import { ServerFilteredEventScope } from "./ServerFilteredEventScope";
import type { BoardCatalogDefinition, BoardVisualizationRuntime, DashboardBoard, SelectionFilter } from "./types";
import { localizedBoardTitle } from "./dashboardLocalization";

const BlockRenderer = lazy(() => import("../../components").then((module) => ({ default: module.BlockRenderer })));
const PlannerAssistantBoard = lazy(() => import("../planner/PlannerAssistantBoard").then((module) => ({ default: module.PlannerAssistantBoard })));
const RoleBoardRenderer = lazy(() => import("../roles/RoleBoardRenderer").then((module) => ({ default: module.RoleBoardRenderer })));
const OperationsKpiBoard = lazy(() => import("./AdvancedBoards").then((module) => ({ default: module.OperationsKpiBoard })));
const RiskTrendWorkbench = lazy(() => import("./AdvancedBoards").then((module) => ({ default: module.RiskTrendWorkbench })));
const EventDataGridBoard = lazy(() => import("./AdvancedBoards").then((module) => ({ default: module.EventDataGridBoard })));
const OntologyRelationshipBoard = lazy(() => import("./AdvancedBoards").then((module) => ({ default: module.OntologyRelationshipBoard })));
const ActivityStreamBoard = lazy(() => import("./AdvancedBoards").then((module) => ({ default: module.ActivityStreamBoard })));
const AnalysisReferenceBoard = lazy(() => import("./AnalysisReferenceBoard").then((module) => ({ default: module.AnalysisReferenceBoard })));
const CatalogDataBoard = lazy(() => import("./CatalogDataBoard").then((module) => ({ default: module.CatalogDataBoard })));

const ROLE_RENDERERS = new Set([
  "ExecutivePortfolio", "ExecutiveRiskTrend", "ExecutiveUnresolved", "ExecutiveBusinessImpact",
  "AuditReconstruction", "AuditVersionSnapshot", "AuditEvidenceTrace", "AuditActionHistory", "AuditExportCheckpoint",
  "FieldTask", "FieldSafetyLocation", "FieldMeasurements", "FieldTaskActions",
  "FDEWorkspaceOverview", "FDEOntologyRegistry", "FDEDeploymentChecklist", "FDEDiagnosticEvents", "FDEApprovalQueue",
  "MLVersionMatrix", "MLThresholdCost", "MLSliceError", "MLDriftSchema", "MLGoldRegression", "MLReleaseCandidate",
]);

function LazyBoard({ children }: { children: React.ReactNode }) {
  const { t } = useI18n();
  return <Suspense fallback={<OntologyLifecycleLoader variant="board" operation={t("dashboard.loadingBoardModule")} />}>{children}</Suspense>;
}

const LEGACY_RENDERERS = new Set<BlockType>([
  "StatusSummary",
  "RiskKpi",
  "PriorityList",
  "ImpactSummary",
  "ManagerDecisionCard",
  "SensorLineChart",
  "AnomalyTimeline",
  "FactorContribution",
  "EvidenceTable",
  "RecommendedActions",
  "EngineerChecklist",
  "DataQualityWarning",
  "ModelDetails",
  "ConversationThread",
]);

interface DashboardBoardRendererProps {
  board: DashboardBoard;
  definition: BoardCatalogDefinition;
  evidence: Evidence;
  report: Report;
  layout: Layout;
  events: EventSummary[];
  selectedEventId: string;
  dashboardId: string;
  projectId: string;
  workspaceId: string;
  appRole: AppRole;
  role: Role;
  canRecordDecision: boolean;
  canRecordNote: boolean;
  parameterState: Record<string, unknown>;
  selectionFilters: SelectionFilter[];
  affectedCount: number;
  roleWorkspaceData: RoleWorkspaceData | null;
  onSelectEvent: (sourceBoardId: string, eventId: string) => void;
  onSelectionFilter: (filter: SelectionFilter) => void;
  onVisualizationRuntime: (boardId: string, runtime: BoardVisualizationRuntime) => void;
  onAuditCheckpoint: (format: "json" | "csv" | "pdf", reason: string) => Promise<void>;
  onFieldAction: (
    action: "complete" | "issue_found" | "blocked",
    input: {
      checklist: string[];
      measurements: Record<string, number | string>;
      photo_metadata: Array<Record<string, unknown>>;
      note: string;
      location: string;
      safety_risk: boolean;
    },
  ) => Promise<void>;
  onApplyPlannerDraft: (draft: DashboardDraftResponse) => void;
  onModelRelease: (input: {
    model_version: string;
    dataset_version: string;
    policy_version: string;
    metrics: Record<string, string | number>;
    threshold_evaluation: Record<string, string | number>;
    notes: string;
  }) => Promise<void>;
  onDecision: (decision: string, note: string) => Promise<void>;
  onNote: (body: string) => Promise<void>;
  onAsk: (question: string) => Promise<void>;
  lastFollowUp: FollowUp | null;
}

export function DashboardBoardRenderer({
  board,
  definition,
  evidence,
  report,
  layout,
  events,
  selectedEventId,
  dashboardId,
  projectId,
  workspaceId,
  appRole,
  role,
  canRecordDecision,
  canRecordNote,
  parameterState,
  selectionFilters,
  affectedCount,
  roleWorkspaceData,
  onSelectEvent,
  onSelectionFilter,
  onVisualizationRuntime,
  onAuditCheckpoint,
  onFieldAction,
  onApplyPlannerDraft,
  onModelRelease,
  onDecision,
  onNote,
  onAsk,
  lastFollowUp,
}: DashboardBoardRendererProps) {
  const { t } = useI18n();
  const boardTitle = localizedBoardTitle(board, t);
  if (definition.renderer === "PlannerAssistant") {
    return (
      <LazyBoard><PlannerAssistantBoard
        workspaceId={workspaceId}
        selectedEventId={selectedEventId}
        appRole={appRole}
        onApplyDraft={onApplyPlannerDraft}
      /></LazyBoard>
    );
  }

  if (ROLE_RENDERERS.has(definition.renderer)) {
    return (
      <LazyBoard><RoleBoardRenderer
        renderer={definition.renderer}
        data={roleWorkspaceData}
        selectedEventId={selectedEventId}
        onSelectEvent={(eventId) => onSelectEvent(board.id, eventId)}
        onAuditCheckpoint={onAuditCheckpoint}
        onFieldAction={onFieldAction}
        onModelRelease={onModelRelease}
      /></LazyBoard>
    );
  }

  if (LEGACY_RENDERERS.has(definition.renderer as BlockType)) {
    const existing = layout.blocks.find((item) => item.type === definition.renderer);
    const block: UIBlock = existing
      ? { ...existing, block_id: board.id, title: boardTitle, order: board.order + 1 }
      : {
          block_id: board.id,
          type: definition.renderer as BlockType,
          title: boardTitle,
          order: board.order + 1,
          emphasis: board.width === 12 ? "primary" : "secondary",
          data_fields: [],
          collapsed: false,
        };
    const renderLegacy = (scopedEvents: EventSummary[]) => (
      <BlockRenderer
        block={block}
        evidence={evidence}
        report={report}
        events={scopedEvents}
        selectedEventId={selectedEventId}
        role={role}
        canRecordDecision={canRecordDecision}
        canRecordNote={canRecordNote}
        onSelectEvent={(eventId) => onSelectEvent(board.id, eventId)}
        onDecision={onDecision}
        onNote={onNote}
        onAsk={onAsk}
        lastFollowUp={lastFollowUp}
      />
    );
    const usesRiskEventScope = definition.object_types.length === 0 || definition.object_types.includes("risk_event");
    return (
      <LazyBoard>
        {usesRiskEventScope ? (
          <ServerFilteredEventScope
            boardId={board.id}
            dashboardId={dashboardId}
            workspaceId={workspaceId}
            events={events}
            parameterState={parameterState}
            selectionFilters={selectionFilters}
          >
            {renderLegacy}
          </ServerFilteredEventScope>
        ) : renderLegacy(events)}
      </LazyBoard>
    );
  }

  if (definition.renderer === "GenericDataBoard" && definition.default_data_binding && definition.default_render_spec) {
    return (
      <LazyBoard><CatalogDataBoard
        board={board}
        dashboardId={dashboardId}
        workspaceId={workspaceId}
        definition={definition}
        parameterState={parameterState}
        selectionFilters={selectionFilters}
        onSelectionFilter={onSelectionFilter}
        onVisualizationRuntime={onVisualizationRuntime}
      /></LazyBoard>
    );
  }

  switch (definition.renderer) {
    case "OperationsKpi":
      return (
        <LazyBoard><ServerFilteredEventScope
          boardId={board.id}
          dashboardId={dashboardId}
          workspaceId={workspaceId}
          events={events}
          parameterState={parameterState}
          selectionFilters={selectionFilters}
        >
          {(scopedEvents) => <OperationsKpiBoard events={scopedEvents} parameterState={parameterState} />}
        </ServerFilteredEventScope></LazyBoard>
      );
    case "RiskTrendWorkbench":
      return (
        <LazyBoard><ServerFilteredEventScope
          boardId={board.id}
          dashboardId={dashboardId}
          workspaceId={workspaceId}
          events={events}
          parameterState={parameterState}
          selectionFilters={selectionFilters}
        >
          {(scopedEvents) => <RiskTrendWorkbench
            boardId={board.id}
            events={scopedEvents}
            selectedEventId={selectedEventId}
            parameterState={parameterState}
            onSelectEvent={(eventId) => onSelectEvent(board.id, eventId)}
            onSelectionFilter={onSelectionFilter}
          />}
        </ServerFilteredEventScope></LazyBoard>
      );
    case "EventDataGrid":
      return (
        <LazyBoard><EventDataGridBoard
          boardId={board.id}
          dashboardId={dashboardId}
          workspaceId={workspaceId}
          events={events}
          selectedEventId={selectedEventId}
          parameterState={parameterState}
          selectionFilters={selectionFilters}
          onSelectEvent={(eventId) => onSelectEvent(board.id, eventId)}
          onSelectionFilter={onSelectionFilter}
        /></LazyBoard>
      );
    case "AnalysisReference":
      return (
        <LazyBoard><AnalysisReferenceBoard
          board={board}
          workspaceId={workspaceId}
          onSelectionFilter={onSelectionFilter}
          onVisualizationRuntime={onVisualizationRuntime}
        /></LazyBoard>
      );
    case "OntologyRelationship":
      return (
        <LazyBoard><OntologyRelationshipBoard
          workspaceId={workspaceId}
          events={events}
          selectedEventId={selectedEventId}
          onSelectEvent={(eventId) => onSelectEvent(board.id, eventId)}
        /></LazyBoard>
      );
    case "ActivityStream":
      return (
        <LazyBoard><ServerFilteredEventScope
          boardId={board.id}
          dashboardId={dashboardId}
          workspaceId={workspaceId}
          events={events}
          parameterState={parameterState}
          selectionFilters={selectionFilters}
        >
          {(scopedEvents) => <ActivityStreamBoard
            events={scopedEvents}
            selectedEventId={selectedEventId}
            evidence={evidence}
            report={report}
            onSelectEvent={(eventId) => onSelectEvent(board.id, eventId)}
          />}
        </ServerFilteredEventScope></LazyBoard>
      );
    case "ObjectContext": {
      const selected = events.find((event) => event.event_id === selectedEventId);
      return (
        <section className="card platform-board-card">
          <h2>{boardTitle}</h2>
          {selected ? (
            <>
              <div className="platform-object-heading"><strong>{selected.equipment.display_name}</strong><StatusBadge status={selected.status} /></div>
              <dl className="platform-object-dl">
                <dt>Equipment</dt><dd>{selected.equipment.equipment_id}</dd>
                <dt>Risk Event</dt><dd>{selected.event_id}</dd>
                <dt>Line</dt><dd>{selected.equipment.line}</dd>
                <dt>Engineer</dt><dd>{selected.equipment.assigned_engineer}</dd>
              </dl>
            </>
          ) : <p>{t("dashboard.noSelectedObject")}</p>}
        </section>
      );
    }
    case "ParameterSummary":
      return (
        <section className="card platform-board-card">
          <h2>{boardTitle}</h2>
          <div className="parameter-board-grid">
            {Object.entries(parameterState).map(([key, value]) => (
              <div key={key}><span>{key}</span><code>{String(value ?? "-")}</code></div>
            ))}
          </div>
          <p className="affected-summary">{t("dashboard.downstreamAffected", { count: affectedCount })}</p>
        </section>
      );
    case "AuditTrace":
      return (
        <section className="card platform-board-card">
          <h2>{boardTitle}</h2>
          <ol className="trace-flow">
            <li><span>{t("dashboard.auditObject")}</span><strong>risk_event:{evidence.event_id}</strong></li>
            <li><span>{t("dashboard.auditEvidence")}</span><strong>{evidence.evidence_id}</strong></li>
            <li><span>{t("dashboard.auditModelPolicy")}</span><strong>{evidence.model.model_version} · {evidence.model.policy_version}</strong></li>
            <li><span>{t("dashboard.auditHumanAction")}</span><strong>{evidence.recommended_decision}</strong></li>
          </ol>
          <small>{t("dashboard.auditTraceDetail")}</small>
          <button
            type="button"
            className="secondary agent-drilldown-button"
            onClick={() => navigate(agentPath(projectId, workspaceId, {
              question: `${evidence.event_id}의 위험 근거, 관계 경로, 관련 문서를 검증해줘`,
              objectType: "risk_event",
              objectId: evidence.event_id,
            }))}
          >
            {t("dashboard.traceInAgent")}
          </button>
        </section>
      );
    case "IntegrationHealth":
      return (
        <section className="card platform-board-card">
          <h2>{boardTitle}</h2>
          <div className="health-list">
            <div><span>{t("dashboard.manufacturingAdapter")}</span><strong className="health-ok">{t("dashboard.connected")}</strong></div>
            <div><span>{t("dashboard.evidenceContext")}</span><strong>{evidence.maintenance_context.provider}</strong></div>
            <div><span>{t("dashboard.reportProvider")}</span><strong>{report.mode}</strong></div>
            <div><span>{t("dashboard.layoutPlanner")}</span><strong>{layout.mode}</strong></div>
          </div>
        </section>
      );
    case "ModelHealth":
      return (
        <section className="card platform-board-card">
          <h2>{boardTitle}</h2>
          <div className="metric-grid">
            <div className="metric"><span>{t("dashboard.modelLabel")}</span><strong>{evidence.model.model_version}</strong></div>
            <div className="metric"><span>{t("dashboard.policyLabel")}</span><strong>{evidence.model.policy_version}</strong></div>
            <div className="metric"><span>{t("dashboard.confidenceLabel")}</span><strong>{evidence.confidence}</strong></div>
            <div className="metric"><span>{t("dashboard.qualityIssues")}</span><strong>{evidence.data_quality_warnings.length}</strong></div>
          </div>
        </section>
      );
    case "TextBoard":
      return (
        <section className="card platform-board-card text-board-card">
          <h2>{boardTitle}</h2>
          <p>{String(board.settings.text ?? "")}</p>
          <small>{t("dashboard.plainTextOnly")}</small>
        </section>
      );
    default:
      return (
        <section className="card platform-board-card">
          <h2>{boardTitle}</h2>
          <p>{t("dashboard.rendererMissing")}</p>
          <code>{definition.renderer}</code>
        </section>
      );
  }
}
