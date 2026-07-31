import { useCallback, useEffect, useMemo, useState } from "react";
import { addNote, followUp, getEvents, getEvidence, getLayout, getReport, recordDecision, resetDemo } from "./api";
import { BlockRenderer, StatusBadge } from "./components";
import type { Evidence, EventSummary, FollowUp, Intent, Layout, Report, Role } from "./types";

const INTENTS: Array<{ value: Intent; label: string }> = [
  { value: "overview", label: "기본 화면" },
  { value: "explain-risk", label: "위험 근거" },
  { value: "compare", label: "센서 비교" },
  { value: "recommend-check", label: "점검 순서" },
  { value: "show-model-details", label: "모델 상세" },
];

export default function App() {
  const [role, setRole] = useState<Role>("manager");
  const [intent, setIntent] = useState<Intent>("overview");
  const [events, setEvents] = useState<EventSummary[]>([]);
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
    getEvents()
      .then((items) => {
        if (!active) return;
        setEvents(items);
        setSelectedEventId((current) => current || items[0]?.event_id || "");
      })
      .catch((reason: Error) => active && setError(reason.message));
    return () => { active = false; };
  }, []);

  const loadDetail = useCallback(async (eventId: string, activeRole: Role, activeIntent: Intent) => {
    if (!eventId) return;
    setLoading(true);
    setError("");
    try {
      const [nextEvidence, nextReport, nextLayout] = await Promise.all([
        getEvidence(eventId),
        getReport(eventId, activeRole, true),
        getLayout(eventId, activeRole, activeIntent, true),
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
  }, []);

  useEffect(() => {
    void loadDetail(selectedEventId, role, intent);
    // Intent-only changes are loaded explicitly so a follow-up response is not
    // overwritten by this base event/role effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedEventId, role, loadDetail]);

  const selected = useMemo(
    () => events.find((event) => event.event_id === selectedEventId) ?? null,
    [events, selectedEventId],
  );

  function changeRole(nextRole: Role) {
    setRole(nextRole);
    setIntent(nextRole === "manager" ? "overview" : "detail-engineer");
  }

  async function handleDecision(decision: string, note: string) {
    if (!evidence) return;
    await recordDecision(evidence.event_id, role === "manager" ? "김현우" : evidence.equipment.assigned_engineer, decision, note);
    setNotice("판단과 메모를 감사 기록에 저장했습니다.");
  }

  async function handleNote(body: string) {
    if (!evidence) return;
    await addNote(evidence.event_id, evidence.equipment.assigned_engineer, body);
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

  async function handleReset() {
    await resetDemo();
    setNotice("발표 상태를 초기화했습니다.");
    setLastFollowUp(null);
    await loadDetail(selectedEventId, role, "overview");
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">FS</span>
          <div><strong>Factory Signal Board</strong><small>Role-aware maintenance intelligence</small></div>
        </div>

        <div className="sidebar-section">
          <span className="section-label">사용자 역할</span>
          <div className="role-switch" role="group" aria-label="사용자 역할 선택">
            <button className={role === "manager" ? "active" : ""} onClick={() => changeRole("manager")}>매니저</button>
            <button className={role === "engineer" ? "active" : ""} onClick={() => changeRole("engineer")}>엔지니어</button>
          </div>
        </div>

        <div className="sidebar-section grow">
          <span className="section-label">설비 사건</span>
          <div className="event-nav">
            {events.map((event) => (
              <button key={event.event_id} className={selectedEventId === event.event_id ? "active" : ""} onClick={() => setSelectedEventId(event.event_id)}>
                <span><strong>{event.equipment.display_name}</strong><small>{event.scenario_id} · {event.equipment.line}</small></span>
                <StatusBadge status={event.status} />
              </button>
            ))}
          </div>
        </div>

        <button className="reset-button" onClick={handleReset}>발표 상태 초기화</button>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div>
            <span className="eyebrow">{role === "manager" ? "MANAGER DECISION VIEW" : "ENGINEER EVIDENCE VIEW"}</span>
            <h1>{selected?.equipment.display_name ?? "설비를 선택하세요"}</h1>
            <p>{selected ? `${selected.equipment.line} · 담당 ${selected.equipment.assigned_engineer}` : ""}</p>
          </div>
          <div className="topbar-actions">
            <label>
              화면 관점
              <select value={intent} onChange={(event) => {
                const nextIntent = event.target.value as Intent;
                setIntent(nextIntent);
                void loadDetail(selectedEventId, role, nextIntent);
              }}>
                {INTENTS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
              </select>
            </label>
            {layout ? <span className={`mode-badge ${layout.mode.includes("fallback") ? "fallback" : ""}`}>{layout.mode}</span> : null}
          </div>
        </header>

        {notice ? <div className="notice" role="status"><span>{notice}</span><button onClick={() => setNotice("")}>닫기</button></div> : null}
        {error ? <div className="error-panel" role="alert"><strong>연결 또는 계약 오류</strong><p>{error}</p><button onClick={() => loadDetail(selectedEventId, role, intent)}>다시 시도</button></div> : null}
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
          AI4I-compatible Gold fixture · 실제 설비 제어 없음 · 예측 원인은 현장 점검 전까지 가설입니다.
        </footer>
      </main>
    </div>
  );
}
