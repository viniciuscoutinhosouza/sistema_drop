from pydantic import BaseModel, EmailStr, field_validator


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterUGORequest(BaseModel):
    """Cadastro de operador de Galpão (papel unificado `go`) — realizado pelo Admin ou Galpão."""

    full_name: str
    email: EmailStr
    whatsapp: str
    password: str
    password_confirm: str
    warehouse_id: int | None = None

    @field_validator("password_confirm")
    @classmethod
    def passwords_match(cls, v, info):
        if "password" in info.data and v != info.data["password"]:
            raise ValueError("As senhas não coincidem")
        return v


class RegisterUserRequest(BaseModel):
    """Cadastro unificado de usuário — o perfil de acesso define o papel (base_role).

    Sem perfil informado, o usuário é criado como operador de Galpão (papel unificado `go`).
    Campos de AC (cpf/endereço/plano) só são usados quando o perfil tem base_role == 'ac'.
    """

    full_name: str
    email: EmailStr
    whatsapp: str = ""
    password: str
    password_confirm: str
    warehouse_id: int | None = None
    profile_id: int | None = None

    # Campos opcionais — só aplicados quando o perfil for de base_role 'ac'
    person_type: str = "fisica"  # "fisica" | "juridica"
    cpf_cnpj: str = ""
    plan_id: int | None = None
    zip_code: str = ""
    street: str = ""
    number: str = ""
    complement: str = ""
    neighborhood: str = ""
    city: str = ""
    state: str = ""

    @field_validator("password_confirm")
    @classmethod
    def passwords_match(cls, v, info):
        if "password" in info.data and v != info.data["password"]:
            raise ValueError("As senhas não coincidem")
        return v


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: int
    full_name: str
    email: str
    role: str
    dark_mode: bool
    avatar_url: str | None = None
    go_id: int | None = None
    warehouse_id: int | None = None
    profile_id: int | None = None
    profile_name: str | None = None
    menu_permissions: list[str] = []


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    new_password_confirm: str

    @field_validator("new_password_confirm")
    @classmethod
    def passwords_match(cls, v, info):
        if "new_password" in info.data and v != info.data["new_password"]:
            raise ValueError("As senhas não coincidem")
        return v
