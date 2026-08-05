import { Button, FormGroup, HTMLSelect, InputGroup, NumericInput, TextArea } from "@blueprintjs/core";
import { Paperclip, Search, Send } from "lucide-react";
import { useEffect, useState } from "react";
import type { AgentQueryInput, AgentRoute } from "./types";

interface AgentQueryBoardProps {
  projectId: string;
  workspaceId: string;
  initialQuestion?: string;
  initialObjectType?: string;
  initialObjectId?: string;
  loading: boolean;
  loadingRun: boolean;
  onQuery: (input: AgentQueryInput) => Promise<void>;
  onLoadRun: (runId: string) => Promise<void>;
  graphRoutesAvailable?: boolean;
}

export function AgentQueryBoard({
  projectId,
  workspaceId,
  initialQuestion = "",
  initialObjectType = "",
  initialObjectId = "",
  loading,
  loadingRun,
  onQuery,
  onLoadRun,
  graphRoutesAvailable = true,
}: AgentQueryBoardProps) {
  const [question, setQuestion] = useState(initialQuestion);
  const [route, setRoute] = useState<"auto" | AgentRoute>("auto");
  const [objectType, setObjectType] = useState(initialObjectType);
  const [objectId, setObjectId] = useState(initialObjectId);
  const [topK, setTopK] = useState(8);
  const [runId, setRunId] = useState("");
  const [advanced, setAdvanced] = useState(Boolean(initialObjectType || initialObjectId));

  useEffect(() => {
    if (!graphRoutesAvailable && ["graph", "vector", "hybrid"].includes(route)) setRoute("relational");
  }, [graphRoutesAvailable, route]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!question.trim()) return;
    await onQuery({ project_id: projectId, workspace_id: workspaceId, question: question.trim(), route, object_type: objectType.trim() || undefined, object_id: objectId.trim() || undefined, top_k: topK });
  }

  return (
    <div className="agent-query-column">
      <form className="agent-composer" onSubmit={(event) => void submit(event)}>
        <header><div><span className="eyebrow">GOVERNED COMPOSER</span><strong>Ask with scoped evidence</strong></div><button type="button" className={`fd-toolbar-button ${advanced ? "active" : ""}`} onClick={() => setAdvanced((current) => !current)}><Paperclip size={12} /> Context</button></header>
        <FormGroup label="Question" labelFor="agent-question">
          <TextArea id="agent-question" fill rows={3} value={question} placeholder="M-014와 연결된 최근 위험 사건, 관계 경로, 유사 정비 사례와 SOP를 보여줘." onChange={(event) => setQuestion(event.currentTarget.value)} />
        </FormGroup>
        {advanced ? <div className="agent-composer-context">
          <FormGroup label="Object type" labelFor="agent-object-type"><InputGroup id="agent-object-type" value={objectType} placeholder="Equipment" onChange={(event) => setObjectType(event.currentTarget.value)} /></FormGroup>
          <FormGroup label="Object identity" labelFor="agent-object-id"><InputGroup id="agent-object-id" value={objectId} placeholder="M-014" onChange={(event) => setObjectId(event.currentTarget.value)} /></FormGroup>
        </div> : null}
        <footer>
          <div className="agent-composer-options">
            <FormGroup label="Route" labelFor="agent-route" helperText={!graphRoutesAvailable ? "Project 3 연결 전에는 Relational evidence만 사용할 수 있습니다." : undefined}><HTMLSelect id="agent-route" value={route} onChange={(event) => setRoute(event.currentTarget.value as "auto" | AgentRoute)}><option value="auto" disabled={!graphRoutesAvailable}>Auto classify</option><option value="relational">Relational</option><option value="graph" disabled={!graphRoutesAvailable}>Graph</option><option value="vector" disabled={!graphRoutesAvailable}>Vector</option><option value="hybrid" disabled={!graphRoutesAvailable}>Hybrid</option></HTMLSelect></FormGroup>
            <FormGroup label="Evidence limit" labelFor="agent-top-k"><NumericInput id="agent-top-k" min={1} max={30} value={topK} onValueChange={(value) => setTopK(Math.min(30, Math.max(1, value || 1)))} /></FormGroup>
          </div>
          <Button type="submit" intent="primary" icon={<Send size={13} />} loading={loading} disabled={!question.trim()}>Run governed query</Button>
        </footer>
      </form>
      <div className="agent-run-loader-card">
        <span>Open persisted run</span>
        <InputGroup aria-label="Agent run ID" value={runId} placeholder="agent-..." onChange={(event) => setRunId(event.currentTarget.value)} />
        <Button icon={<Search size={12} />} loading={loadingRun} disabled={!runId.trim()} onClick={() => void onLoadRun(runId.trim())}>Load</Button>
      </div>
    </div>
  );
}
