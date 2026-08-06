"""Identity, membership, permission, and session contracts."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

UserStatus = Literal["pending_approval", "active", "disabled"]

SESSION_COOKIE = "ontology_session"
CSRF_COOKIE = "ontology_csrf"
SESSION_TTL_HOURS = 12
SESSION_IDLE_MINUTES = 60

ROLE_DEFINITIONS: dict[str, tuple[str, str]] = {
    "process_manager": ("관리자·임원", "위험 우선순위와 실제 운영 판단, Executive Report를 담당합니다."),
    "process_engineer": ("실무 엔지니어", "설비 근거를 검토하고 현장 점검 메모를 기록합니다."),
}

PERMISSION_DEFINITIONS: dict[str, str] = {
    "app.access": "현재 MVP 접근",
    "events.read": "Event, Evidence, Report와 Activity 조회",
    "events.decision": "관리자·임원의 실제 운영 판단 기록",
    "events.note": "실무 엔지니어의 현장 점검 메모 기록",
}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "process_manager": {"app.access", "events.read", "events.decision"},
    "process_engineer": {"app.access", "events.read", "events.note"},
}

DEMO_ACCOUNTS: tuple[dict[str, Any], ...] = (
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
    requested_role: Literal["process_manager", "process_engineer"] = "process_engineer"
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


class ActiveProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, max_length=128)


class ProjectMembershipUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["active", "suspended"] = "active"
    roles: list[str] = Field(min_length=1)


class AdminUserUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: UserStatus | None = None
    roles: list[str] | None = None
    workspace_scopes: list[str] | None = None
    permission_overrides: dict[str, bool] | None = None


class DisplayPreferenceUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[3] = 3
    textSize: Literal["small", "default", "large", "extra-large"] = "default"
    density: Literal["compact", "standard", "comfortable"] = "standard"
    showTechnicalMetadata: bool = False


class Principal(BaseModel):
    user_id: str
    organization_id: str
    email: str
    display_name: str
    status: UserStatus
    roles: list[str]
    permissions: list[str]
    workspace_scopes: list[str]
    project_scopes: list[str] = Field(default_factory=list)
    project_roles: dict[str, list[str]] = Field(default_factory=dict)
    active_project_id: str | None = None
    active_project_roles: list[str] = Field(default_factory=list)
    is_admin: bool
    default_path: str
    landing_key: str
