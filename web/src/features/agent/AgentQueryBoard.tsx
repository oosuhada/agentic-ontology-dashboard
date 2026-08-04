import { Button, Card, FormGroup, HTMLSelect, InputGroup, NumericInput, TextArea } from "@blueprintjs/core";
import { useState } from "react";
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
}: AgentQueryBoardProps) {
  const [question, setQuestion] = useState(initialQuestion);
  const [route, setRoute] = useState<"auto" | AgentRoute>("auto");
  const [objectType, setObjectType] = useState(initialObjectType);
  const [objectId, setObjectId] = useState(initialObjectId);
  const [topK, setTopK] = useState(8);
  const [runId, setRunId] = useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!question.trim()) return;
    await onQuery({
      project_id: projectId,
      workspace_id: workspaceId,
      question: question.trim(),
      route,
      object_type: objectType.trim() || undefined,
      object_id: objectId.trim() || undefined,
      top_k: topK,
    });
  }

  return (
    <div className="agent-query-column">
      <Card elevation={0} className="agent-query-card">
        <span className="eyebrow">MULTI-STORE QUERY</span>
        <h2>Ask with governed evidence</h2>
        <p>직접 SQL·Cypher를 입력하지 않고 등록된 relational, graph, vector tool만 실행합니다.</p>
        <form onSubmit={(event) => void submit(event)}>
          <FormGroup label="Question" labelFor="agent-question">
            <TextArea
              id="agent-question"
              fill
              rows={5}
              value={question}
              placeholder="M-014와 연결된 최근 위험 사건, 관계 경로, 유사 정비 사례와 SOP를 보여줘."
              onChange={(event) => setQuestion(event.currentTarget.value)}
            />
          </FormGroup>
          <div className="agent-query-two-column">
            <FormGroup label="Route" labelFor="agent-route">
              <HTMLSelect
                id="agent-route"
                fill
                value={route}
                onChange={(event) => setRoute(event.currentTarget.value as "auto" | AgentRoute)}
              >
                <option value="auto">Auto classify</option>
                <option value="relational">Relational</option>
                <option value="graph">Graph</option>
                <option value="vector">Vector</option>
                <option value="hybrid">Hybrid</option>
              </HTMLSelect>
            </FormGroup>
            <FormGroup label="Evidence limit" labelFor="agent-top-k">
              <NumericInput
                id="agent-top-k"
                fill
                min={1}
                max={30}
                value={topK}
                onValueChange={(value) => setTopK(Math.min(30, Math.max(1, value || 1)))}
              />
            </FormGroup>
          </div>
          <FormGroup label="Object type (optional)" labelFor="agent-object-type">
            <InputGroup id="agent-object-type" value={objectType} placeholder="Equipment" onChange={(event) => setObjectType(event.currentTarget.value)} />
          </FormGroup>
          <FormGroup label="Object identity (optional)" labelFor="agent-object-id">
            <InputGroup id="agent-object-id" value={objectId} placeholder="M-014" onChange={(event) => setObjectId(event.currentTarget.value)} />
          </FormGroup>
          <Button type="submit" intent="primary" icon="search-around" fill loading={loading} disabled={!question.trim()}>
            Run governed query
          </Button>
        </form>
      </Card>

      <Card elevation={0} className="agent-run-loader-card">
        <span className="eyebrow">RUN INSPECTOR</span>
        <h2>Open a persisted run</h2>
        <p>감사나 handoff에 전달받은 run ID를 같은 Project scope 안에서 다시 조회합니다.</p>
        <InputGroup aria-label="Agent run ID" value={runId} placeholder="agent-..." onChange={(event) => setRunId(event.currentTarget.value)} />
        <Button fill icon="history" loading={loadingRun} disabled={!runId.trim()} onClick={() => void onLoadRun(runId.trim())}>
          Load run
        </Button>
      </Card>
    </div>
  );
}
