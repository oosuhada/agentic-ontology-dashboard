import { FormEvent, useState } from "react";
import { register } from "../../api";
import { navigate } from "../../routing";
import { AuthShell } from "./AuthShell";

export function RegisterPage() {
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [organizationName, setOrganizationName] = useState("");
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
        terms_accepted: termsAccepted,
      });
      navigate(`/pending?email=${encodeURIComponent(result.email)}&organization=${encodeURIComponent(result.requested_organization_name)}`);
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
