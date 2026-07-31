from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

UserStatus = Literal["pending_approval", "active", "disabled"]

SESSION_COOKIE = "ontology_session"
CSRF_COOKIE = "ontology_csrf"
SESSION_TTL_HOURS = 12

ROLE_DEFINITIONS: dict[str, tuple[str, str]] = {
    "tenant_admin": ("조직 관리자", "사용자, 역할, workspace scope와 관리자 감사를 관리합니다."),
    "executive_viewer": ("임원 Viewer", "조직 위험, 영향, 추세와 대응 상태를 확인합니다."),
    "process_manager": ("운영 매니저", "우선순위, 배정, 기한과 에스컬레이션을 관리합니다."),
    "process_engineer": ("도메인 엔지니어", "원인 분석, 근거 검토, 점검 계획과 보고를 수행합니다."),
    "maintenance_technician": ("현장 작업자", "배정된 점검, 체크리스트와 측정 결과를 기록합니다."),
    "quality_auditor": ("품질·감사 Viewer", "lineage, 버전, 사용자 행동과 근거를 재구성합니다."),
    "ml_validator": ("데이터 사이언티스트", "모델, 데이터, threshold, 오류와 drift를 검증합니다."),
    "fde": ("Forward Deployed Engineer", "고객 workflow, ontology, integration과 dashboard template을 구축합니다."),
}

PERMISSION_DEFINITIONS: dict[str, str] = {
    "app.access": "일반 사용자 앱 접근",
    "events.read": "Manufacturing Predictive Maintenance Pack 사건과 근거 조회",
    "events.decision": "운영 판단 기록",
    "events.note": "점검 및 전달 메모 기록",
    "ontology.registry.read": "온톨로지 registry 조회",
    "admin.access": "관리자 앱 접근",
    "admin.users.read": "사용자와 역할 조회",
    "admin.users.manage": "가입 승인, 비활성화, 역할 및 scope 변경",
    "admin.audit.read": "관리자 변경 감사 조회",
}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "tenant_admin": set(PERMISSION_DEFINITIONS),
    "executive_viewer": {"app.access", "events.read", "ontology.registry.read"},
    "process_manager": {"app.access", "events.read", "events.decision", "ontology.registry.read"},
    "process_engineer": {"app.access", "events.read", "events.note", "ontology.registry.read"},
    "maintenance_technician": {"app.access", "events.read", "events.note", "ontology.registry.read"},
    "quality_auditor": {"app.access", "events.read", "ontology.registry.read"},
    "ml_validator": {"app.access", "events.read", "ontology.registry.read"},
    "fde": {"app.access", "events.read", "events.note", "ontology.registry.read"},
}

DEMO_ACCOUNTS: tuple[dict[str, Any], ...] = (
    {
        "email": "admin@ontology.local",
        "password": "OntologyAdmin!2026",
        "display_name": "Ontology 관리자",
        "roles": ["tenant_admin"],
    },
    {
        "email": "executive@ontology.local",
        "password": "Executive!2026",
        "display_name": "임원 Viewer",
        "roles": ["executive_viewer"],
    },
    {
        "email": "manager@ontology.local",
        "password": "Manager!2026",
        "display_name": "김현우",
        "roles": ["process_manager"],
    },
    {
        "email": "engineer@ontology.local",
        "password": "Engineer!2026",
        "display_name": "박지민",
        "roles": ["process_engineer"],
    },
    {
        "email": "technician@ontology.local",
        "password": "Technician!2026",
        "display_name": "현장 작업자",
        "roles": ["maintenance_technician"],
    },
    {
        "email": "quality@ontology.local",
        "password": "Quality!2026",
        "display_name": "품질 감사 담당",
        "roles": ["quality_auditor"],
    },
    {
        "email": "datascientist@ontology.local",
        "password": "DataScience!2026",
        "display_name": "데이터 사이언티스트",
        "roles": ["ml_validator"],
    },
    {
        "email": "fde@ontology.local",
        "password": "FDE!2026",
        "display_name": "Forward Deployed Engineer",
        "roles": ["fde"],
    },
)


class AuthError(RuntimeError):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=2, max_length=80)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=200)
    organization_name: str = Field(min_length=2, max_length=120)
    terms_accepted: bool

    @field_validator("display_name", "organization_name")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not EMAIL_PATTERN.match(normalized):
            raise ValueError("올바른 이메일 주소를 입력하세요.")
        return normalized

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        groups = (
            any(character.islower() for character in value),
            any(character.isupper() for character in value),
            any(character.isdigit() for character in value),
            any(not character.isalnum() for character in value),
        )
        if not all(groups):
            raise ValueError("비밀번호에는 영문 대문자·소문자·숫자·특수문자를 모두 포함해야 합니다.")
        return value

    @field_validator("terms_accepted")
    @classmethod
    def require_terms(cls, value: bool) -> bool:
        if not value:
            raise ValueError("이용약관 동의가 필요합니다.")
        return value


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not EMAIL_PATTERN.match(normalized):
            raise ValueError("올바른 이메일 주소를 입력하세요.")
        return normalized


class AdminUserUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: UserStatus | None = None
    roles: list[str] | None = None
    workspace_scopes: list[str] | None = None


class Principal(BaseModel):
    user_id: str
    email: str
    display_name: str
    status: UserStatus
    roles: list[str]
    permissions: list[str]
    workspace_scopes: list[str]
    is_admin: bool
    default_path: str
    landing_key: str
