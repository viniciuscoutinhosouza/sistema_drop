from pydantic import BaseModel, EmailStr, field_validator
import re


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    full_name: str
    email: EmailStr
    whatsapp: str
    person_type: str          # "fisica" | "juridica"
    cpf_cnpj: str
    password: str
    password_confirm: str

    # Address
    zip_code: str
    street: str
    number: str
    complement: str = ""
    neighborhood: str
    city: str
    state: str                # 2-letter UF

    @field_validator("person_type")
    @classmethod
    def validate_person_type(cls, v):
        if v not in ("fisica", "juridica"):
            raise ValueError("Tipo de pessoa deve ser 'fisica' ou 'juridica'")
        return v

    @field_validator("state")
    @classmethod
    def validate_state(cls, v):
        if len(v) != 2:
            raise ValueError("Estado deve ter 2 letras (UF)")
        return v.upper()

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
