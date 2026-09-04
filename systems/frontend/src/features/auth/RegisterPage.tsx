import { FormEvent, useState } from "react";
import { register } from "../../api";
import { navigate } from "../../routing";
import { AuthShell } from "./AuthShell";
import type { AppRole } from "../../types";

const REQUESTABLE_ROLES: Array<{ value: Exclude<AppRole, "tenant_admin">; label: string; detail: string }> = [
  { value: "executive_viewer", label: "임원 Viewer", detail: "조직 수준 보고서와 경영 영향 검토" },
  { value: "process_manager", label: "운영 매니저", detail: "운영 보고서, 우선순위와 의사결정" },
  { value: "process_engineer", label: "도메인 엔지니어", detail: "Dashboard 분석과 보고서 작성" },
  { value: "maintenance_technician", label: "현장 작업자", detail: "점검 작업, 체크리스트와 현장 기록" },
  { value: "quality_auditor", label: "품질·감사 Viewer", detail: "보고서, Evidence와 감사 이력 검토" },
  { value: "ml_validator", label: "데이터 사이언티스트", detail: "Dataset, 모델과 예측 결과 검증" },
  { value: "fde", label: "FDE", detail: "Ontology·Dashboard template 구축" },
];

export function RegisterPage() {
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [organizationName, setOrganizationName] = useState("");
  const [requestedRole, setRequestedRole] = useState<Exclude<AppRole, "tenant_admin">>("process_engineer");
  const [password, setPassword] = useState("");
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const result = await register({
        display_name: displayName,
        email,
        password,
        organization_name: organizationName,
        requested_role: requestedRole,
        terms_accepted: termsAccepted,
      });
      navigate(`/pending?email=${encodeURIComponent(result.email)}&organization=${encodeURIComponent(result.requested_organization_name)}&role=${encodeURIComponent(result.requested_role)}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "회원가입을 완료하지 못했습니다.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthShell
      eyebrow="CREATE ACCOUNT"
      title="조직 가입 요청"
      description="가입 후 관리자가 조직, 역할과 workspace scope를 검토해 활성화합니다."
    >
      <form className="auth-form" onSubmit={submit}>
        <label>
          이름
          <input value={displayName} onChange={(event) => setDisplayName(event.target.value)} autoComplete="name" required />
        </label>
        <label>
          업무 이메일
          <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" required />
        </label>
        <label>
          조직명 또는 초대 조직
          <input value={organizationName} onChange={(event) => setOrganizationName(event.target.value)} placeholder="조직명을 입력하세요" required />
        </label>
        <label>
          희망 역할
          <select value={requestedRole} onChange={(event) => setRequestedRole(event.target.value as Exclude<AppRole, "tenant_admin">)}>
            {REQUESTABLE_ROLES.map((role) => <option key={role.value} value={role.value}>{role.label} · {role.detail}</option>)}
          </select>
          <small>관리자가 실제 업무 범위와 권한을 확인한 뒤 역할을 확정하거나 수정합니다.</small>
        </label>
        <label>
          비밀번호
          <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" minLength={12} required />
          <small>12자 이상, 영문 대·소문자, 숫자, 특수문자를 포함하세요.</small>
        </label>
        <label className="terms-row">
          <input type="checkbox" checked={termsAccepted} onChange={(event) => setTermsAccepted(event.target.checked)} required />
          <span>서비스 이용과 계정 승인 절차에 동의합니다.</span>
        </label>
        {error ? <div className="auth-error" role="alert">{error}</div> : null}
        <button className="primary auth-submit" type="submit" disabled={submitting}>
          {submitting ? "가입 요청 중…" : "가입 승인 요청"}
        </button>
      </form>
      <p className="auth-footer-copy">
        이미 계정이 있나요? <button className="link-button" type="button" onClick={() => navigate("/login")}>로그인</button>
      </p>
    </AuthShell>
  );
}
