import { FormEvent, useState } from "react";
import { ApiError } from "../../api";
import { navigate, safeApplicationReturnPath } from "../../routing";
import { useAuth } from "./AuthContext";
import { AuthShell } from "./AuthShell";

const DEMO_ACCOUNTS = [
  {
    label: "관리자·임원",
    description: "Overview · Operations · Executive Report",
    email: "manager@ontology.local",
    password: "Manager!2026",
  },
  {
    label: "실무 엔지니어",
    description: "Objects · Evidence · 현장 메모",
    email: "engineer@ontology.local",
    password: "Engineer!2026",
  },
] as const;

const PUBLIC_DEMO_HOSTS = new Set([
  "dashboard.oosu.dev",
  "127.0.0.1",
  "localhost",
]);

function shouldShowDemoAccounts() {
  const explicitFlag = import.meta.env.VITE_ENABLE_DEMO_ACCOUNTS;
  if (explicitFlag === "1" || explicitFlag === "true") return true;
  if (import.meta.env.DEV) return true;
  return typeof window !== "undefined" && PUBLIC_DEMO_HOSTS.has(window.location.hostname);
}

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
      const returnTo = safeApplicationReturnPath(new URLSearchParams(window.location.search).get("returnTo"));
      navigate(returnTo ?? user.default_path, { replace: true });
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
    const account = DEMO_ACCOUNTS.find((item) => item.email === value);
    if (!account) return;
    setEmail(account.email);
    setPassword(account.password);
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

      {shouldShowDemoAccounts() ? (
        <details className="demo-account-picker" open>
          <summary>MVP 데모 역할 선택</summary>
          <div className="demo-account-grid" role="group" aria-label="MVP 데모 계정">
            {DEMO_ACCOUNTS.map((account) => (
              <button
                key={account.email}
                className={`demo-account-card ${email === account.email ? "is-selected" : ""}`}
                type="button"
                onClick={() => selectDemo(account.email)}
              >
                <strong>{account.label}</strong>
                <span>{account.description}</span>
                <small>{account.email}</small>
              </button>
            ))}
          </div>
          <small>최종 MVP에서 사용하는 두 역할만 빠르게 선택할 수 있습니다.</small>
        </details>
      ) : null}

      <p className="auth-footer-copy">
        계정이 없나요? <button className="link-button" type="button" onClick={() => navigate("/register")}>회원가입</button>
      </p>
    </AuthShell>
  );
}
