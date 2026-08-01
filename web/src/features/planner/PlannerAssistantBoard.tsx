import { useState } from "react";
import {
  generateDashboardDraft,
  generateGroundedNarrative,
  planObjectQuery,
  recommendBoards,
} from "../../api";
import type { AppRole } from "../../types";
import type {
  BoardRecommendationResponse,
  DashboardDraftResponse,
  GroundedNarrativeResponse,
  ObjectQueryPlanResponse,
} from "./types";

interface PlannerAssistantBoardProps {
  workspaceId: string;
  selectedEventId: string;
  appRole: AppRole;
  onApplyDraft: (draft: DashboardDraftResponse) => void;
}

type PlannerTool = "query" | "boards" | "narrative" | "draft";

const TARGET_ROLES: AppRole[] = [
  "tenant_admin",
  "executive_viewer",
  "process_manager",
  "process_engineer",
  "maintenance_technician",
  "quality_auditor",
  "ml_validator",
  "fde",
];

function ModeBadge({ mode, provider }: { mode: string; provider: string }) {
  return <span className={`planner-mode ${mode.includes("fallback") ? "fallback" : ""}`}>{mode} · {provider}</span>;
}

export function PlannerAssistantBoard({
  workspaceId,
  selectedEventId,
  appRole,
  onApplyDraft,
}: PlannerAssistantBoardProps) {
  const canDraft = appRole === "fde" || appRole === "tenant_admin";
  const [tool, setTool] = useState<PlannerTool>("query");
  const [prompt, setPrompt] = useState("critical 위험 사건과 관련 설비를 보여줘");
  const [targetRole, setTargetRole] = useState<AppRole>("process_manager");
  const [queryResult, setQueryResult] = useState<ObjectQueryPlanResponse | null>(null);
  const [recommendation, setRecommendation] = useState<BoardRecommendationResponse | null>(null);
  const [narrative, setNarrative] = useState<GroundedNarrativeResponse | null>(null);
  const [draft, setDraft] = useState<DashboardDraftResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function run() {
    if (!prompt.trim()) return;
    setLoading(true);
    setError("");
    try {
      if (tool === "query") {
        setQueryResult(await planObjectQuery({ workspace_id: workspaceId, query: prompt.trim() }));
      } else if (tool === "boards") {
        setRecommendation(await recommendBoards({ workspace_id: workspaceId, goal: prompt.trim() }));
      } else if (tool === "narrative") {
        if (!selectedEventId) throw new Error("먼저 사건을 선택하세요.");
        setNarrative(await generateGroundedNarrative({
          workspace_id: workspaceId,
          event_id: selectedEventId,
          goal: prompt.trim(),
        }));
      } else {
        setDraft(await generateDashboardDraft({
          workspace_id: workspaceId,
          target_role: targetRole,
          goal: prompt.trim(),
        }));
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Planner 요청을 처리하지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="card planner-assistant-card">
      <div className="planner-tool-tabs" role="tablist" aria-label="Ontology Planner tools">
        <button type="button" className={tool === "query" ? "active" : ""} onClick={() => setTool("query")}>Object Query</button>
        <button type="button" className={tool === "boards" ? "active" : ""} onClick={() => setTool("boards")}>Board 추천</button>
        <button type="button" className={tool === "narrative" ? "active" : ""} onClick={() => setTool("narrative")}>Grounded 설명</button>
        {canDraft ? <button type="button" className={tool === "draft" ? "active" : ""} onClick={() => setTool("draft")}>Dashboard Draft</button> : null}
      </div>

      <div className="planner-prompt-row">
        {tool === "draft" ? (
          <label>대상 역할<select value={targetRole} onChange={(event) => setTargetRole(event.target.value as AppRole)}>{TARGET_ROLES.map((role) => <option key={role} value={role}>{role}</option>)}</select></label>
        ) : null}
        <label className="planner-prompt-label">자연어 요청<textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} /></label>
        <button type="button" className="primary" onClick={() => void run()} disabled={loading || !prompt.trim()}>{loading ? "검증 중" : "Draft 생성"}</button>
      </div>

      <div className="planner-safety-note">
        <strong>Governed planning</strong>
        <span>Object type·property·Board Catalog·role permission을 서버에서 다시 검증합니다. 제안은 자동 저장되지 않습니다.</span>
      </div>
      {error ? <p className="planner-error">{error}</p> : null}

      {tool === "query" && queryResult ? (
        <div className="planner-result">
          <div className="planner-result-heading"><div><strong>{queryResult.intent.object_type}</strong><small>{queryResult.intent.rationale}</small></div><ModeBadge mode={queryResult.mode} provider={queryResult.provider} /></div>
          <code>{JSON.stringify({ search: queryResult.intent.search, filters: queryResult.intent.filters }, null, 2)}</code>
          <div className="planner-object-grid">{queryResult.preview_items.map((item) => <article key={item.id}><strong>{item.id}</strong><span>{item.object_type}</span><pre>{JSON.stringify(item.properties, null, 2)}</pre></article>)}</div>
          {!queryResult.preview_items.length ? <p>조건에 맞는 Object가 없습니다.</p> : null}
        </div>
      ) : null}

      {tool === "boards" && recommendation ? (
        <div className="planner-result">
          <div className="planner-result-heading"><div><strong>{recommendation.role_code} Board 제안</strong><small>현재 개인 배치와 숨김·넓이 signal을 참고했습니다.</small></div><ModeBadge mode={recommendation.mode} provider={recommendation.provider} /></div>
          <div className="planner-recommendation-list">{recommendation.recommendations.map((item) => <article key={item.definition_id}><div><strong>{item.display_name}</strong><small>{item.definition_id} · {item.category}</small></div><b>{Math.round(item.score * 100)}%</b><p>{item.reason}</p>{item.preference_signals.map((signal) => <span key={signal}>{signal}</span>)}</article>)}</div>
        </div>
      ) : null}

      {tool === "narrative" && narrative ? (
        <div className="planner-result">
          <div className="planner-result-heading"><div><strong>{narrative.headline}</strong><small>{narrative.event_id}</small></div><ModeBadge mode={narrative.mode} provider={narrative.provider} /></div>
          <p className="grounded-summary">{narrative.summary}</p>
          <div className="grounded-claim-list">{narrative.claims.map((claim, index) => <article key={index}><p>{claim.text}</p><code>{claim.evidence_field_ids.join(" · ")}</code></article>)}</div>
        </div>
      ) : null}

      {tool === "draft" && draft ? (
        <div className="planner-result">
          <div className="planner-result-heading"><div><strong>{draft.target_role} Dashboard Draft</strong><small>{draft.recommended_definition_ids.length}개 Catalog Board 제안 · 저장되지 않음</small></div><ModeBadge mode={draft.mode} provider={draft.provider} /></div>
          <div className="planner-draft-tabs">{draft.tabs.map((tab) => <article key={tab.id}><strong>{tab.title}</strong><small>{tab.boards.map((board) => board.definition_id).join(" · ")}</small></article>)}</div>
          <button type="button" className="primary" onClick={() => onApplyDraft(draft)}>검토를 위해 Canvas에 적용</button>
          <small className="planner-approval-note">Canvas 적용 후에도 개인 저장 또는 Template 승인 요청을 눌러야만 persistence가 발생합니다.</small>
        </div>
      ) : null}
    </section>
  );
}
