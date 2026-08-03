import { useCallback, useEffect, useMemo, useState } from "react";
import {
  addNote,
  followUp,
  getDomainPacks,
  getEvents,
  getEvidence,
  getLayout,
  getReport,
  getWorkspaces,
  recordDecision,
} from "../../api";
import { BlockRenderer, StatusBadge } from "../../components";
import { navigate } from "../../routing";
import type {
  AppRole,
  AuthUser,
  DomainPack,
  Evidence,
  EventSummary,
  FollowUp,
  Intent,
  Layout,
  Report,
  Role,
  Workspace,
} from "../../types";
import { useAuth } from "../auth/AuthContext";

const INTENTS: Array<{ value: Intent; label: string }> = [
  { value: "overview", label: "기본 화면" },
  { value: "explain-risk", label: "위험 근거" },
  { value: "compare", label: "센서 비교" },
  { value: "recommend-check", label: "점검 순서" },
  { value: "show-model-details", label: "모델 상세" },
];

interface RoleLanding {
  label: string;
  eyebrow: string;
  description: string;
  legacyRole: Role;
  defaultIntent: Intent;
  focus: string[];
}

const ROLE_LANDING: Record<AppRole, RoleLanding> = {
  tenant_admin: {
    label: "조직 관리자",
    eyebrow: "ADMIN OPERATIONS PREVIEW",
    description: "관리자 권한으로 제조 workspace의 운영 상태를 확인합니다.",
    legacyRole: "manager",
    defaultIntent: "overview",
    focus: ["조직 운영", "권한 오류", "감사 상태"],
  },
  executive_viewer: {
    label: "임원 Viewer",
    eyebrow: "EXECUTIVE RISK OVERVIEW",
    description: "조직 위험, 생산 영향과 미조치 중요 사건을 우선 확인합니다.",
    legacyRole: "manager",
    defaultIntent: "overview",
    focus: ["전체 위험", "생산 영향", "대응 상태"],
  },
  process_manager: {
    label: "운영 매니저",
    eyebrow: "MANAGER DECISION VIEW",
    description: "위험 우선순위, 담당자와 다음 운영 판단을 중심으로 봅니다.",
    legacyRole: "manager",
    defaultIntent: "overview",
    focus: ["우선순위", "담당 배정", "기한·에스컬레이션"],
  },
  process_engineer: {
    label: "도메인 엔지니어",
    eyebrow: "ENGINEER EVIDENCE VIEW",
    description: "센서 변화, 원인 후보, SOP와 점검 근거를 중심으로 봅니다.",
    legacyRole: "engineer",
    defaultIntent: "detail-engineer",
    focus: ["센서 추세", "근거 검토", "점검 계획"],
  },
  maintenance_technician: {
    label: "현장 작업자",
    eyebrow: "FIELD TASK VIEW",
    description: "배정된 점검의 안전 절차, 체크리스트와 기록 항목을 중심으로 봅니다.",
    legacyRole: "engineer",
    defaultIntent: "recommend-check",
    focus: ["안전", "체크리스트", "현장 기록"],
  },
  quality_auditor: {
    label: "품질·감사 Viewer",
    eyebrow: "QUALITY & AUDIT VIEW",
    description: "Evidence, 버전, lineage와 사람의 행동 기록을 조회합니다.",
    legacyRole: "manager",
    defaultIntent: "show-model-details",
    focus: ["Evidence", "Lineage", "행동 이력"],
  },
  ml_validator: {
    label: "데이터 사이언티스트",
    eyebrow: "MODEL VALIDATION VIEW",
    description: "모델 결과, 데이터 품질, threshold와 오류 사례를 검증합니다.",
    legacyRole: "engineer",
    defaultIntent: "show-model-details",
    focus: ["모델 버전", "데이터 품질", "오류 분석"],
  },
  fde: {
    label: "Forward Deployed Engineer",
    eyebrow: "FDE WORKBENCH PREVIEW",
    description: "고객 workflow와 ontology binding을 진단하되 사용자 관리 권한은 갖지 않습니다.",
    legacyRole: "engineer",
    defaultIntent: "explain-risk",
    focus: ["Ontology binding", "Integration", "Role preview"],
  },
};

function primaryRole(user: AuthUser): AppRole {
  return user.roles[0] ?? "process_manager";
}

export function ManufacturingApp() {
  const { user, logout } = useAuth();
  if (!user) throw new Error("ManufacturingApp requires an authenticated user");

  const roleConfig = ROLE_LANDING[primaryRole(user)];
  const role = roleConfig.legacyRole;
  const [intent, setIntent] = useState<Intent>(roleConfig.defaultIntent);
  const [events, setEvents] = useState<EventSummary[]>([]);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [domainPacks, setDomainPacks] = useState<DomainPack[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState("manufacturing-demo");
  const [selectedEventId, setSelectedEventId] = useState("");
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [layout, setLayout] = useState<Layout | null>(null);
  const [lastFollowUp, setLastFollowUp] = useState<FollowUp | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let active = true;
    Promise.all([getEvents(), getWorkspaces(), getDomainPacks()])
      .then(([eventItems, workspaceItems, packItems]) => {
        if (!active) return;
        setEvents(eventItems);
        setWorkspaces(workspaceItems);
        setDomainPacks(packItems);
        setSelectedWorkspaceId(workspaceItems[0]?.id ?? "manufacturing-demo");
        setSelectedEventId((current) => current || eventItems[0]?.event_id || "");
      })
      .catch((reason: Error) => active && setError(reason.message));
    return () => { active = false; };
  }, []);

  const loadDetail = useCallback(async (eventId: string, activeIntent: Intent) => {
    if (!eventId) return;
    setLoading(true);
    setError("");
    try {
      const [nextEvidence, nextReport, nextLayout] = await Promise.all([
        getEvidence(eventId),
        getReport(eventId, role, true),
        getLayout(eventId, role, activeIntent, true),
      ]);
      setEvidence(nextEvidence);
      setReport(nextReport);
      setLayout(nextLayout);
      setLastFollowUp(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "화면을 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }, [role]);

  useEffect(() => {
    void loadDetail(selectedEventId, intent);
    // Intent-only changes are loaded explicitly so a follow-up response is not overwritten.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedEventId, loadDetail]);

  const selected = useMemo(
    () => events.find((event) => event.event_id === selectedEventId) ?? null,
    [events, selectedEventId],
  );
  const selectedPack = domainPacks.find((pack) => pack.workspace_ids.includes(selectedWorkspaceId));
  const canRecordDecision = user.permissions.includes("events.decision");
  const canRecordNote = user.permissions.includes("events.note");

  async function handleDecision(decision: string, note: string) {
    if (!evidence) return;
    await recordDecision(evidence.event_id, user!.display_name, decision, note);
    setNotice("판단과 메모를 감사 기록에 저장했습니다.");
  }

  async function handleNote(body: string) {
    if (!evidence) return;
    await addNote(evidence.event_id, user!.display_name, body);
    setNotice("점검 기록을 저장했습니다.");
  }

  async function handleAsk(question: string) {
    if (!evidence) return;
    setError("");
    try {
      const response = await followUp(evidence.event_id, role, question);
      setLastFollowUp(response);
      setIntent(response.intent);
      setReport(response.report);
      setLayout(response.layout);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "질문을 처리하지 못했습니다.");
    }
  }

  async function handleLogout() {
    await logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">OD</span>
          <div><strong>Ontology Dashboard</strong><small>Ontology-aware operations</small></div>
        </div>

        <div className="sidebar-section">
          <span className="section-label">Workspace</span>
          <select className="workspace-select" value={selectedWorkspaceId} onChange={(event) => setSelectedWorkspaceId(event.target.value)}>
            {workspaces.map((workspace) => <option key={workspace.id} value={workspace.id}>{workspace.display_name}</option>)}
          </select>
          <div className="domain-pack-card">
            <small>DOMAIN PACK</small>
            <strong>{selectedPack?.display_name ?? "Manufacturing Predictive Maintenance Pack"}</strong>
            <span>기존 제조 예지보전 vertical slice</span>
          </div>
        </div>

        <div className="sidebar-section role-context-card">
          <span className="section-label">현재 역할</span>
          <strong>{roleConfig.label}</strong>
          <small>{user.email}</small>
        </div>

        <div className="sidebar-section grow">
          <span className="section-label">Object Priority · Risk Event</span>
          <div className="event-nav">
            {events.map((event) => (
              <button key={event.event_id} className={selectedEventId === event.event_id ? "active" : ""} onClick={() => setSelectedEventId(event.event_id)}>
                <span><strong>{event.equipment.display_name}</strong><small>{event.scenario_id} · {event.equipment.line}</small></span>
                <StatusBadge status={event.status} />
              </button>
            ))}
          </div>
        </div>

        <div className="sidebar-user">
          <div><strong>{user.display_name}</strong><small>{roleConfig.label}</small></div>
          {user.is_admin ? <button onClick={() => navigate("/admin")}>관리자</button> : null}
          <button onClick={handleLogout}>로그아웃</button>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div>
            <span className="eyebrow">{roleConfig.eyebrow}</span>
            <h1>{selected?.equipment.display_name ?? "Risk Event를 선택하세요"}</h1>
            <p>{selected ? `${selected.equipment.line} · 담당 ${selected.equipment.assigned_engineer}` : ""}</p>
          </div>
          <div className="topbar-actions">
            <label>
              화면 관점
              <select value={intent} onChange={(event) => {
                const nextIntent = event.target.value as Intent;
                setIntent(nextIntent);
                void loadDetail(selectedEventId, nextIntent);
              }}>
                {INTENTS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
              </select>
            </label>
            {layout ? <span className={`mode-badge ${layout.mode.includes("fallback") ? "fallback" : ""}`}>{layout.mode}</span> : null}
          </div>
        </header>

        <section className="role-landing-strip" aria-label="역할 기본 화면 설명">
          <div><strong>{roleConfig.label} 기본 화면</strong><p>{roleConfig.description}</p></div>
          <div className="role-focus-list">{roleConfig.focus.map((item) => <span key={item}>{item}</span>)}</div>
        </section>

        {notice ? <div className="notice" role="status"><span>{notice}</span><button onClick={() => setNotice("")}>닫기</button></div> : null}
        {error ? <div className="error-panel" role="alert"><strong>연결 또는 권한 오류</strong><p>{error}</p><button onClick={() => loadDetail(selectedEventId, intent)}>다시 시도</button></div> : null}
        {loading ? <div className="loading-panel"><div className="spinner" /><p>Evidence와 역할별 화면을 구성하고 있습니다.</p></div> : null}

        {!loading && evidence && report && layout ? (
          <div className={`dashboard-grid role-${role}`}>
            {layout.blocks.map((block) => (
              <div key={block.block_id} className={`block-slot emphasis-${block.emphasis} block-${block.type}`}>
                <BlockRenderer
                  block={block}
                  evidence={evidence}
                  report={report}
                  events={events}
                  selectedEventId={selectedEventId}
                  role={role}
                  canRecordDecision={canRecordDecision}
                  canRecordNote={canRecordNote}
                  onSelectEvent={setSelectedEventId}
                  onDecision={handleDecision}
                  onNote={handleNote}
                  onAsk={handleAsk}
                  lastFollowUp={lastFollowUp}
                />
              </div>
            ))}
          </div>
        ) : null}

        <footer className="footer-note">
          Manufacturing Predictive Maintenance Pack · 실제 설비 제어 없음 · 예측 원인은 현장 점검 전까지 가설입니다.
        </footer>
      </main>
    </div>
  );
}
