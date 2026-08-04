import { Button, Callout, Card, Icon } from "@blueprintjs/core";
import { navigate, projectHomePath } from "../../routing";
import { useAuth } from "../auth/AuthContext";

interface ProjectTombstonePageProps {
  projectId: string;
}

export function ProjectTombstonePage({ projectId }: ProjectTombstonePageProps) {
  const { user } = useAuth();
  const fallbackProjectId = user?.active_project_id && user.active_project_id !== projectId
    ? user.active_project_id
    : user?.project_scopes.find((item) => item !== projectId) ?? null;

  return (
    <main className="project-tombstone-page">
      <Card elevation={1} className="project-tombstone-card">
        <div className="project-tombstone-icon"><Icon icon="archive" size={28} /></div>
        <span className="eyebrow">PROJECT UNAVAILABLE</span>
        <h1>이 Project는 보관되었거나 삭제되었습니다</h1>
        <p>
          요청한 <code>{projectId}</code> Project는 더 이상 활성 Project 목록에 없습니다.
          기존 deep link, Saved View 또는 공유 링크에서 접근한 경우 관리자에게 복구 여부를 확인하세요.
        </p>
        <Callout intent="warning" icon="info-sign">
          보관된 Project의 Dashboard, Dataset, Ontology, Agent 및 Governance 리소스는 다른 Project로 자동 전환되지 않습니다.
        </Callout>
        <div className="button-row">
          {fallbackProjectId ? (
            <Button
              intent="primary"
              icon="projects"
              onClick={() => navigate(projectHomePath(fallbackProjectId), { replace: true })}
            >
              접근 가능한 Project 열기
            </Button>
          ) : null}
          <Button icon="log-out" onClick={() => navigate("/login", { replace: true })}>로그인 화면</Button>
        </div>
      </Card>
    </main>
  );
}
