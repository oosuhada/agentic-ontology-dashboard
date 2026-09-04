import { FormEvent, useState } from "react";
import { ApiError } from "../../api";
import {
  navigate,
  operationsProjectPath,
  safeApplicationReturnPath,
} from "../../routing";
import type { AuthUser } from "../../types";
import { useAuth } from "./AuthContext";
import { AuthShell } from "./AuthShell";
import { useI18n } from "../../ui/i18n/I18nProvider";
import { useDisplayPreferences } from "../../ui/foundry/displayPreferences";
import { Info } from "lucide-react";

const DEMO_ACCOUNTS = [
  {
    label: { ko: "엔지니어", en: "Engineer" },
    description: {
      ko: "설비 상태 · 센서 피쳐 · 점검 · 정비 이력 · 현장 메모",
      en: "Factory status · sensor features · inspection · maintenance history · field notes",
    },
    email: "engineer@ontology.local",
    password: "Engineer!2026",
  },
  {
    label: { ko: "운영 관리", en: "Operations" },
    description: {
      ko: "판단 대기 · 생산 영향 · 정비 승인 · 보고 초안",
      en: "Pending decisions · production impact · maintenance approval · report draft",
    },
    email: "manager@ontology.local",
    password: "Manager!2026",
  },
  {
    label: { ko: "경영진", en: "Executive" },
    description: {
      ko: "Executive Brief · 운영 리스크 · KPI · 의사결정 병목",
      en: "Executive Brief · operational risk · KPI · decision bottlenecks",
    },
    email: "executive@ontology.local",
    password: "Executive!2026",
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
  return (
    typeof window !== "undefined" &&
    PUBLIC_DEMO_HOSTS.has(window.location.hostname)
  );
}

function roleAwareLandingPath(user: AuthUser): string {
  if (user.is_admin) return user.default_path;
  const projectId = user.active_project_id ?? user.project_scopes[0] ?? null;
  if (!projectId) return user.default_path;
  const roles = user.active_project_roles.length
    ? user.active_project_roles
    : user.roles;
  const params = new URLSearchParams({ dashboard: "workflow" });
  if (roles.includes("executive_viewer")) {
    params.set("view", "reports");
    params.set("report", "executive-brief");
    params.set("role", "process_manager");
  } else if (roles.includes("process_manager")) {
    params.set("view", "operations");
    params.set("role", "process_manager");
  } else if (roles.includes("maintenance_technician")) {
    params.set("view", "operations");
    params.set("role", "field_operator");
  } else {
    params.set("view", "overview");
    params.set("role", "field_operator");
  }
  return `${operationsProjectPath(projectId)}?${params.toString()}`;
}

export function LoginPage() {
  const { login } = useAuth();
  const { locale } = useI18n();
  const { preferences } = useDisplayPreferences();
  const english = locale === "en-US";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const roleContextDescription = english
    ? "Connect the same equipment event and evidence across engineering investigation, operational decisions, and executive reporting."
    : "같은 설비 이상 사건과 근거를 엔지니어의 조사, 운영 관리자의 판단, 경영진의 보고 언어로 연결합니다.";

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const user = await login(email, password);
      const returnTo = safeApplicationReturnPath(
        new URLSearchParams(window.location.search).get("returnTo"),
      );
      navigate(returnTo ?? roleAwareLandingPath(user), { replace: true });
    } catch (reason) {
      if (reason instanceof ApiError && reason.code === "pending_approval") {
        navigate(`/pending?email=${encodeURIComponent(email)}`);
        return;
      }
      setError(
        reason instanceof Error
          ? reason.message
          : english
            ? "Unable to sign in."
            : "로그인하지 못했습니다.",
      );
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
      eyebrow="HANBIT TECH · RELIABILITY OPERATIONS"
      title={
        english
          ? "From live equipment status to operational decisions and executive reporting"
          : "실시간 설비 현황에서 운영 판단과 경영 보고까지"
      }
      description={
        roleContextDescription
      }
      showDescription={false}
      showTraceabilityNote={false}
    >
      <form className="auth-form" onSubmit={submit}>
        <label>
          {english ? "Email" : "이메일"}
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
          {english ? "Password" : "비밀번호"}
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder={english ? "Password" : "비밀번호"}
            required
          />
        </label>
        {error ? (
          <div className="auth-error" role="alert">
            {error}
          </div>
        ) : null}
        <button
          className="primary auth-submit"
          type="submit"
          disabled={submitting}
        >
          {submitting
            ? english
              ? "Signing in…"
              : "로그인 중…"
            : english
              ? "Sign in"
              : "로그인"}
        </button>
      </form>

      {shouldShowDemoAccounts() ? (
        <section
          className="demo-account-picker"
          aria-label={
            english
              ? "Role-based Reliability Operations accounts"
              : "역할별 Reliability Operations 계정"
          }
        >
          <header
            className="demo-account-heading"
            tabIndex={0}
            title={preferences.showGuidance ? roleContextDescription : undefined}
            aria-label={`${english ? "Choose a role" : "역할 선택"}. ${roleContextDescription}`}
          >{english ? "Choose a role" : "역할 선택"}</header>
          <div
            className="demo-account-grid"
            role="group"
            aria-label={english ? "Role accounts" : "역할별 계정"}
          >
            {DEMO_ACCOUNTS.map((account) => (
              <div
                className={`demo-account-option ${email === account.email ? "is-selected" : ""}`}
                key={account.email}
              >
                <button
                  className="demo-account-card"
                  type="button"
                  onClick={() => selectDemo(account.email)}
                  aria-describedby={preferences.showGuidance ? `role-help-${account.email.split("@")[0]}` : undefined}
                >
                  <strong>
                    {english ? account.label.en : account.label.ko}
                  </strong>
                  {preferences.showGuidance ? <Info className="demo-account-help-icon" size={13} aria-hidden="true" /> : null}
                </button>
                {preferences.showGuidance ? <div
                  id={`role-help-${account.email.split("@")[0]}`}
                  className="demo-account-popover"
                  role="tooltip"
                >
                    <strong>
                      {english ? account.label.en : account.label.ko}
                    </strong>
                    <p>
                      {english
                        ? account.description.en
                        : account.description.ko}
                    </p>
                    <small>{account.email}</small>
                </div> : null}
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <p className="auth-footer-copy">
        {english ? "Need an account? " : "계정이 없나요? "}
        <button
          className="link-button"
          type="button"
          onClick={() => navigate("/register")}
        >
          {english ? "Create account" : "회원가입"}
        </button>
      </p>
    </AuthShell>
  );
}
