import { FormEvent, useState } from "react";
import { ApiError } from "../../api";
import { navigate } from "../../routing";
import { useAuth } from "./AuthContext";
import { AuthShell } from "./AuthShell";

const DEMO_ACCOUNTS = [
  ["관리자", "admin@ontology.local", "OntologyAdmin!2026"],
  ["임원 Viewer", "executive@ontology.local", "Executive!2026"],
  ["운영 매니저", "manager@ontology.local", "Manager!2026"],
  ["도메인 엔지니어", "engineer@ontology.local", "Engineer!2026"],
  ["현장 작업자", "technician@ontology.local", "Technician!2026"],
  ["품질·감사", "quality@ontology.local", "Quality!2026"],
  ["데이터 사이언티스트", "datascientist@ontology.local", "DataScience!2026"],
  ["FDE", "fde@ontology.local", "FDE!2026"],
] as const;

export function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const user = await login(email, password);
      navigate(user.default_path, { replace: true });
    } catch (reason) {
      if (reason instanceof ApiError && reason.code === "pending_approval") {
        navigate(`/pending?email=${encodeURIComponent(email)}`);
        return;
      }
      setError(reason instanceof Error ? reason.message : "로그인하지 못했습니다.");
    } finally {
      setSubmitting(false);
    }
  }

  function selectDemo(value: string) {
    const account = DEMO_ACCOUNTS.find((item) => item[1] === value);
    if (!account) return;
    setEmail(account[1]);
    setPassword(account[2]);
  }

  return (
    <AuthShell
      eyebrow="SIGN IN"
      title="업무 공간에 로그인"
      description="승인된 역할과 workspace 범위에 맞는 기본 화면을 불러옵니다."
    >
      <form className="auth-form" onSubmit={submit}>
        <label>
          이메일
          <input
            type="email"
            autoComplete="username"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="name@organization.com"
            required
          />
        </label>
        <label>
          비밀번호
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="비밀번호"
            required
          />
        </label>
        {error ? <div className="auth-error" role="alert">{error}</div> : null}
        <button className="primary auth-submit" type="submit" disabled={submitting}>
          {submitting ? "로그인 중…" : "로그인"}
        </button>
      </form>

      {import.meta.env.DEV ? (
        <details className="demo-account-picker">
          <summary>개발·데모 계정 선택</summary>
          <label>
            역할
            <select value={DEMO_ACCOUNTS.some((item) => item[1] === email) ? email : ""} onChange={(event) => selectDemo(event.target.value)}>
              <option value="">계정을 선택하세요</option>
              {DEMO_ACCOUNTS.map(([label, accountEmail]) => <option key={accountEmail} value={accountEmail}>{label} · {accountEmail}</option>)}
            </select>
          </label>
          <small>이 선택기는 development build에서만 표시됩니다.</small>
        </details>
      ) : null}

      <p className="auth-footer-copy">
        계정이 없나요? <button className="link-button" type="button" onClick={() => navigate("/register")}>회원가입</button>
      </p>
    </AuthShell>
  );
}
