import { navigate } from "../../routing";
import { AuthShell } from "./AuthShell";

export function PendingPage() {
  const params = new URLSearchParams(window.location.search);
  const email = params.get("email");
  const organization = params.get("organization");
  const role = params.get("role");

  return (
    <AuthShell
      eyebrow="PENDING APPROVAL"
      title="가입 요청이 접수되었습니다"
      description="관리자가 역할과 허용 workspace를 할당한 뒤 계정이 활성화됩니다."
    >
      <div className="pending-card" role="status">
        <span className="pending-icon">✓</span>
        <div>
          <strong>승인 대기 중</strong>
          {email ? <p>{email}</p> : null}
          {organization ? <small>요청 조직 · {organization}</small> : null}
          {role ? <small>희망 역할 · {role}</small> : null}
        </div>
      </div>
      <ol className="approval-steps">
        <li><strong>1</strong><span>관리자가 가입 요청을 검토합니다.</span></li>
        <li><strong>2</strong><span>역할과 workspace scope를 할당합니다.</span></li>
        <li><strong>3</strong><span>활성화 후 로그인할 수 있습니다.</span></li>
      </ol>
      <button className="secondary auth-submit" type="button" onClick={() => navigate("/login")}>로그인 화면으로</button>
    </AuthShell>
  );
}
