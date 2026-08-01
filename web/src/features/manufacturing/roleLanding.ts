import type { AppRole, Intent, Role } from "../../types";

export interface RoleLanding {
  label: string;
  eyebrow: string;
  description: string;
  legacyRole: Role;
  defaultIntent: Intent;
  focus: string[];
}

export const ROLE_LANDING: Record<AppRole, RoleLanding> = {
  tenant_admin: {
    label: "조직 관리자",
    eyebrow: "ADMIN OPERATIONS PREVIEW",
    description: "관리자 권한으로 workspace의 운영 상태와 governance를 확인합니다.",
    legacyRole: "manager",
    defaultIntent: "overview",
    focus: ["조직 운영", "권한 오류", "감사 상태"],
  },
  executive_viewer: {
    label: "임원 Viewer",
    eyebrow: "EXECUTIVE RISK OVERVIEW",
    description: "조직 위험, 운영 영향과 미조치 중요 사건을 우선 확인합니다.",
    legacyRole: "manager",
    defaultIntent: "overview",
    focus: ["전체 위험", "운영 영향", "대응 상태"],
  },
  process_manager: {
    label: "운영 매니저",
    eyebrow: "MANAGER DECISION VIEW",
    description: "위험 우선순위, 담당자와 다음 운영 판단을 중심으로 봅니다.",
    legacyRole: "manager",
    defaultIntent: "overview",
    focus: ["우선순위", "담당 배정", "기한·에스컬레이션"],
  },
  process_engineer: {
    label: "도메인 엔지니어",
    eyebrow: "ENGINEER EVIDENCE VIEW",
    description: "관측 변화, 원인 후보, 절차와 점검 근거를 중심으로 봅니다.",
    legacyRole: "engineer",
    defaultIntent: "detail-engineer",
    focus: ["관측 추세", "근거 검토", "점검 계획"],
  },
  maintenance_technician: {
    label: "현장 작업자",
    eyebrow: "FIELD TASK VIEW",
    description: "배정된 점검의 안전 절차, 체크리스트와 기록 항목을 중심으로 봅니다.",
    legacyRole: "engineer",
    defaultIntent: "recommend-check",
    focus: ["안전", "체크리스트", "현장 기록"],
  },
  quality_auditor: {
    label: "품질·감사 Viewer",
    eyebrow: "QUALITY & AUDIT VIEW",
    description: "Evidence, 버전, lineage와 사람의 행동 기록을 조회합니다.",
    legacyRole: "manager",
    defaultIntent: "show-model-details",
    focus: ["Evidence", "Lineage", "행동 이력"],
  },
  ml_validator: {
    label: "데이터 사이언티스트",
    eyebrow: "MODEL VALIDATION VIEW",
    description: "모델 결과, 데이터 품질, threshold와 오류 사례를 검증합니다.",
    legacyRole: "engineer",
    defaultIntent: "show-model-details",
    focus: ["모델 버전", "데이터 품질", "오류 분석"],
  },
  fde: {
    label: "Forward Deployed Engineer",
    eyebrow: "FDE WORKBENCH PREVIEW",
    description: "고객 workflow와 ontology binding을 진단하고 역할별 template을 구성합니다.",
    legacyRole: "engineer",
    defaultIntent: "explain-risk",
    focus: ["Ontology binding", "Integration", "Role preview"],
  },
};

export function primaryRole(roles: AppRole[]): AppRole {
  return roles[0] ?? "process_manager";
}
