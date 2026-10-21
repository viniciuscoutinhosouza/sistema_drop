import os
import re
import uuid as _uuid
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_user, require_menu_permission
from models.go import GO
from models.user import User
from models.warehouse import Warehouse, WarehouseBankAccount
from services import crypto

# Upload de logo — só raster (SVG serve inline em /static e viraria XSS). Valida por magic bytes
# (a extensão do nome do usuário é ignorada — o tipo real vem de _sniff_image_ext).
_LOGO_DIR = "static/uploads/warehouse-logos"
_LOGO_MAX_BYTES = 5 * 1024 * 1024
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _norm_color(v) -> str | None:
    """Cor de tema hex #RRGGBB. None/vazio → None (usa default). Inválido → 400 (falha alto)."""
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    if not _HEX_RE.match(s):
        raise HTTPException(status_code=400, detail=f"Cor inválida '{s}' — use o formato #RRGGBB.")
    return s.lower()


def _sniff_image_ext(data: bytes) -> str | None:
    """Extensão real pelo magic byte (extensão do nome não é confiável). None se não for imagem aceita."""
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


def _norm_cep(v) -> str | None:
    """CEP só com dígitos (8) — a coluna `zip_code` tem no máx. 9 e o front pode mandar formatado
    ('12345-678') ou com caractere extra, estourando o limite (ORA-12899)."""
    if v is None:
        return None
    return re.sub(r"\D", "", str(v))[:8] or None


def _norm_work_type(v) -> str:
    """Tipo de trabalho do galpão. None → default 'dropship'; valor INVÁLIDO falha alto (400) —
    não coage em silêncio (senão configurava MultiLojas achando que salvou e ficava Dropship)."""
    if v is None:
        return "dropship"
    if v not in ("dropship", "multilojas"):
        raise HTTPException(
            status_code=400,
            detail="Tipo de trabalho inválido — use 'dropship' ou 'multilojas'.",
        )
    return v

router = APIRouter()


async def _owned_go_id(user: User, db: AsyncSession) -> int | None:
    """Retorna o id do GO que o usuário é DONO (registro em `goes` com `user_id == user.id`), ou None.

    É o único sinal confiável de "dono do galpão": ter papel `go` NÃO basta (é o papel unificado do
    operador também) e ter `go_id` setado também não (operadores herdam o go_id do dono). Só é dono
    quem POSSUI o registro em `goes`. Isolamento: operador (não-dono) nunca alcança galpão irmão.
    """
    if user.role == "admin":
        return None
    r = await db.execute(select(GO.id).where(GO.user_id == user.id))
    return r.scalar_one_or_none()


def _can_access_warehouse(user: User, warehouse: Warehouse, owned_go_id: int | None) -> bool:
    """Isolamento por galpão para a GESTÃO de galpão (get/update/delete).

    admin → tudo. Caso contrário, o usuário só alcança:
      - o galpão vinculado a ele (`warehouse.id == user.warehouse_id`), OU
      - qualquer galpão do GO que ELE é DONO (`owned_go_id` de `_owned_go_id`) — dono multi-galpão.
    NUNCA um galpão de outro dono. Operador (não é dono de GO) fica restrito ao próprio warehouse_id
    mesmo que tenha `go_id` herdado.
    """
    if user.role == "admin":
        return True
    if user.warehouse_id is not None and warehouse.id == user.warehouse_id:
        return True
    if owned_go_id is not None and warehouse.go_id == owned_go_id:
        return True
    return False


def _serialize(w: Warehouse) -> dict:
    return {
        "id": w.id,
        "go_id": w.go_id,
        "name": w.name,
        "work_type": w.work_type or "dropship",
        "cnpj": w.cnpj,
        "company_name": w.company_name,
        "trade_name": w.trade_name,
        "phone": w.phone,
        "whatsapp": w.whatsapp,
        "email": w.email,
        "zip_code": w.zip_code,
        "street": w.street,
        "number": w.number,
        "complement": w.complement,
        "neighborhood": w.neighborhood,
        "city": w.city,
        "state": w.state,
        "pix_key_type": w.pix_key_type,
        "pix_key": w.pix_key,
        "pg_requires_prepaid": bool(w.pg_requires_prepaid),
        "manual_sale_requires_payment": bool(w.manual_sale_requires_payment),
        "notes": w.notes,
        "logo_url": w.logo_url,
        "theme_sidebar": w.theme_sidebar,
        "theme_accent": w.theme_accent,
        "theme_topbar": w.theme_topbar,
        "theme_sidebar_text": w.theme_sidebar_text,
        "theme_link": w.theme_link,
    }


_THEME_COLOR_FIELDS = ("theme_sidebar", "theme_accent", "theme_topbar", "theme_sidebar_text", "theme_link")


@router.get("")
async def list_warehouses(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista galpões. Admin vê todos; Galpão-DONO (possui registro em `goes`) vê os galpões do seu
    GO; operador/AC vê apenas o galpão vinculado. Isolamento por galpão — nunca galpão de outro dono
    (operador não-dono NÃO vê galpão irmão mesmo com go_id herdado)."""
    if current_user.role == "admin":
        result = await db.execute(select(Warehouse))
        return [_serialize(w) for w in result.scalars().all()]
    # Galpão-DONO multi-galpão: lista os galpões do GO que ele é dono + o próprio galpão vinculado
    # (o OR com warehouse_id evita "galpão sumido" caso o vínculo go_id do galpão esteja divergente).
    owned_go_id = await _owned_go_id(current_user, db)
    if owned_go_id is not None:
        conds = [Warehouse.go_id == owned_go_id]
        if current_user.warehouse_id:
            conds.append(Warehouse.id == current_user.warehouse_id)
        result = await db.execute(select(Warehouse).where(or_(*conds)))
        return [_serialize(w) for w in result.scalars().all()]
    # Operador (não é dono de GO) ou AC — retorna apenas o galpão vinculado (lista com 0 ou 1 item)
    if current_user.warehouse_id:
        result = await db.execute(
            select(Warehouse).where(Warehouse.id == current_user.warehouse_id)
        )
        w = result.scalar_one_or_none()
        return [_serialize(w)] if w else []
    return []


@router.get("/{warehouse_id}")
async def get_warehouse(
    warehouse_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retorna os dados de um galpão específico."""
    result = await db.execute(select(Warehouse).where(Warehouse.id == warehouse_id))
    warehouse = result.scalar_one_or_none()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Galpão não encontrado")
    if not _can_access_warehouse(current_user, warehouse, await _owned_go_id(current_user, db)):
        raise HTTPException(status_code=403, detail="Acesso negado")
    return _serialize(warehouse)


@router.post("", status_code=201)
async def create_warehouse(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_menu_permission("go_empresa")),
):
    """Cria um Galpão. Admin ou GO podem executar."""
    go_id = body.get("go_id") or current_user.go_id
    if not go_id:
        raise HTTPException(status_code=422, detail="go_id é obrigatório")

    warehouse = Warehouse(
        go_id=go_id,
        name=body.get("name", ""),
        work_type=_norm_work_type(body.get("work_type")),
        cnpj=body.get("cnpj"),
        company_name=body.get("company_name"),
        trade_name=body.get("trade_name"),
        phone=body.get("phone"),
        whatsapp=body.get("whatsapp"),
        email=body.get("email"),
        zip_code=_norm_cep(body.get("zip_code")),
        street=body.get("street"),
        number=body.get("number"),
        complement=body.get("complement"),
        neighborhood=body.get("neighborhood"),
        city=body.get("city"),
        state=body.get("state"),
        pix_key_type=body.get("pix_key_type"),
        pix_key=body.get("pix_key"),
        pg_requires_prepaid=bool(body.get("pg_requires_prepaid", False)),
        manual_sale_requires_payment=bool(body.get("manual_sale_requires_payment", False)),
        notes=body.get("notes"),
        theme_sidebar=_norm_color(body.get("theme_sidebar")),
        theme_accent=_norm_color(body.get("theme_accent")),
        theme_topbar=_norm_color(body.get("theme_topbar")),
        theme_sidebar_text=_norm_color(body.get("theme_sidebar_text")),
        theme_link=_norm_color(body.get("theme_link")),
    )
    db.add(warehouse)
    await db.commit()
    await db.refresh(warehouse)
    return _serialize(warehouse)


@router.delete("/{warehouse_id}", status_code=204)
async def delete_warehouse(
    warehouse_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_menu_permission("go_empresa")),
):
    """Remove um galpão. Bloqueia se houver usuários ativos vinculados."""
    result = await db.execute(select(Warehouse).where(Warehouse.id == warehouse_id))
    warehouse = result.scalar_one_or_none()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Galpão não encontrado")
    if not _can_access_warehouse(current_user, warehouse, await _owned_go_id(current_user, db)):
        raise HTTPException(status_code=403, detail="Este Galpão não pertence ao seu GO")

    users_result = await db.execute(
        select(User).where(User.warehouse_id == warehouse_id, User.is_active == True)
    )
    if users_result.scalars().first():
        raise HTTPException(
            status_code=409,
            detail="Galpão possui usuários ativos. Desvincule-os antes de remover.",
        )

    _delete_logo_file(warehouse.logo_url)  # limpa o arquivo do logo (sem órfão em disco)
    db.delete(warehouse)
    await db.commit()


@router.put("/{warehouse_id}")
async def update_warehouse(
    warehouse_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_menu_permission("go_empresa")),
):
    """Atualiza os dados do galpão. Admin ou GO podem executar."""
    result = await db.execute(select(Warehouse).where(Warehouse.id == warehouse_id))
    warehouse = result.scalar_one_or_none()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Galpão não encontrado")

    if not _can_access_warehouse(current_user, warehouse, await _owned_go_id(current_user, db)):
        raise HTTPException(status_code=403, detail="Este Galpão não pertence ao seu GO")

    fields = [
        "name",
        "work_type",
        "cnpj",
        "company_name",
        "trade_name",
        "phone",
        "whatsapp",
        "email",
        "zip_code",
        "street",
        "number",
        "complement",
        "neighborhood",
        "city",
        "state",
        "pix_key_type",
        "pix_key",
        "pg_requires_prepaid",
        "manual_sale_requires_payment",
        "notes",
    ]
    _BOOL_FIELDS = ("pg_requires_prepaid", "manual_sale_requires_payment")
    for field in fields:
        if field in body:
            if field == "zip_code":
                val = _norm_cep(body[field])
            elif field == "work_type":
                val = _norm_work_type(body[field])
            elif field in _BOOL_FIELDS:
                val = bool(body[field])
            else:
                val = body[field]
            setattr(warehouse, field, val)

    # Cores do tema — validadas (hex #RRGGBB ou None). Inválida falha alto (400).
    for field in _THEME_COLOR_FIELDS:
        if field in body:
            setattr(warehouse, field, _norm_color(body[field]))

    await db.commit()
    await db.refresh(warehouse)
    return _serialize(warehouse)


@router.post("/{warehouse_id}/logo")
async def upload_warehouse_logo(
    warehouse_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_menu_permission("go_empresa")),
):
    """Envia o logo do Galpão (aparece no topo do menu). Só raster (jpg/png/webp), validado por
    magic bytes; teto de 5 MB; nome com UUID (ignora o nome do usuário — anti path traversal).
    `go_empresa` é permissão de menu — o acesso ao galpão específico é garantido por
    `_can_access_warehouse` (nunca sobe logo em galpão de outro dono)."""
    result = await db.execute(select(Warehouse).where(Warehouse.id == warehouse_id))
    warehouse = result.scalar_one_or_none()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Galpão não encontrado")
    if not _can_access_warehouse(current_user, warehouse, await _owned_go_id(current_user, db)):
        raise HTTPException(status_code=403, detail="Acesso negado a este Galpão")

    data = await file.read(_LOGO_MAX_BYTES + 1)
    if len(data) > _LOGO_MAX_BYTES:
        raise HTTPException(status_code=413, detail="Logo muito grande (máx. 5 MB).")
    ext = _sniff_image_ext(data)
    if ext is None:
        raise HTTPException(
            status_code=400, detail="Arquivo inválido — envie uma imagem JPG, PNG ou WEBP."
        )

    os.makedirs(_LOGO_DIR, exist_ok=True)
    filename = f"{_uuid.uuid4().hex}{ext}"
    with open(f"{_LOGO_DIR}/{filename}", "wb") as out:
        out.write(data)

    # Remove o logo anterior do disco (best-effort) para não acumular órfãos.
    _delete_logo_file(warehouse.logo_url)

    warehouse.logo_url = f"/{_LOGO_DIR}/{filename}"
    await db.commit()
    return {"logo_url": warehouse.logo_url}


@router.delete("/{warehouse_id}/logo", status_code=204)
async def delete_warehouse_logo(
    warehouse_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_menu_permission("go_empresa")),
):
    """Remove o logo do Galpão (volta ao padrão MIG)."""
    result = await db.execute(select(Warehouse).where(Warehouse.id == warehouse_id))
    warehouse = result.scalar_one_or_none()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Galpão não encontrado")
    if not _can_access_warehouse(current_user, warehouse, await _owned_go_id(current_user, db)):
        raise HTTPException(status_code=403, detail="Acesso negado a este Galpão")
    _delete_logo_file(warehouse.logo_url)
    warehouse.logo_url = None
    await db.commit()


def _delete_logo_file(logo_url: str | None) -> None:
    """Apaga o arquivo de logo do disco (best-effort). Só toca arquivos dentro de _LOGO_DIR."""
    if not logo_url:
        return
    name = os.path.basename(logo_url)
    path = os.path.join(_LOGO_DIR, name)
    try:
        if name and os.path.commonpath([os.path.abspath(path), os.path.abspath(_LOGO_DIR)]) == os.path.abspath(_LOGO_DIR) and os.path.isfile(path):
            os.remove(path)
    except (OSError, ValueError):
        pass


# ─── Contas bancárias / recebimento do Galpão (migration 152, ADR-0031) ─────────

_VALID_BANK_PROVIDERS = {"asaas"}
_BANK_PIX_TYPES = {"cpf", "cnpj", "email", "phone", "random"}
# Limite de cada coluna string — valida fail-loud (400) em vez de estourar ORA-12899 (500).
_BANK_MAXLEN = {
    "provider": 20, "bank_code": 10, "name": 200, "wallet_id": 100,
    "chart_account_label": 255, "agency": 20, "account_number": 30,
    "pix_key": 255, "holder_name": 255, "holder_document": 20, "notes": 2000,
}


def _check_bank_len(field: str, value) -> None:
    if value is not None and len(str(value)) > _BANK_MAXLEN[field]:
        raise HTTPException(
            status_code=400,
            detail=f"Campo '{field}' excede o limite de {_BANK_MAXLEN[field]} caracteres.",
        )


async def _get_warehouse_for_user(warehouse_id: int, user: User, db: AsyncSession) -> Warehouse:
    """Carrega o galpão e aplica o isolamento por galpão (ADR-0026). 404/403 se não puder."""
    w = (
        await db.execute(select(Warehouse).where(Warehouse.id == warehouse_id))
    ).scalar_one_or_none()
    if not w:
        raise HTTPException(status_code=404, detail="Galpão não encontrado")
    if not _can_access_warehouse(user, w, await _owned_go_id(user, db)):
        raise HTTPException(status_code=403, detail="Acesso negado a este Galpão")
    return w


def _serialize_bank(b: WarehouseBankAccount) -> dict:
    """NUNCA devolve a API Key — só o flag `api_key_set` (espelha csc_token_set do fiscal)."""
    return {
        "id": b.id,
        "warehouse_id": b.warehouse_id,
        "provider": b.provider,
        "bank_code": b.bank_code,
        "name": b.name,
        "api_key_set": bool(b.api_key_encrypted),
        "webhook_configured": bool(b.webhook_token_hash),
        "wallet_id": b.wallet_id,
        "chart_account_label": b.chart_account_label,
        "is_sandbox": bool(b.is_sandbox),
        "is_active": bool(b.is_active),
        "is_primary": bool(b.is_primary),
        "agency": b.agency,
        "account_number": b.account_number,
        "pix_key_type": b.pix_key_type,
        "pix_key": b.pix_key,
        "holder_name": b.holder_name,
        "holder_document": b.holder_document,
        "opening_balance": float(b.opening_balance) if b.opening_balance is not None else 0,
        "opening_balance_date": b.opening_balance_date.isoformat() if b.opening_balance_date else None,
        "notes": b.notes,
        "created_at": b.created_at.isoformat() if b.created_at else None,
    }


def _norm_bank_provider(v) -> str:
    p = (v or "asaas").strip().lower()
    if p not in _VALID_BANK_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"Provedor inválido '{p}'. Suportado: {', '.join(sorted(_VALID_BANK_PROVIDERS))}.",
        )
    return p


def _norm_bank_pix_type(v):
    if v is None or str(v).strip() == "":
        return None
    t = str(v).strip().lower()
    if t not in _BANK_PIX_TYPES:
        raise HTTPException(status_code=400, detail="Tipo de chave Pix inválido.")
    return t


def _parse_opening_date(v):
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise HTTPException(status_code=400, detail="Data do saldo inicial inválida (use AAAA-MM-DD).")


def _parse_opening_balance(v):
    if v in (None, ""):
        return 0
    try:
        return float(v)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Saldo inicial inválido.")


def _apply_bank_fields(bank: WarehouseBankAccount, body: dict) -> None:
    """Aplica os campos editáveis (exceto api_key, tratada à parte)."""
    if "provider" in body:
        bank.provider = _norm_bank_provider(body.get("provider"))
    for f in (
        "bank_code", "name", "wallet_id", "chart_account_label", "agency",
        "account_number", "pix_key", "holder_name", "holder_document", "notes",
    ):
        if f in body:
            _check_bank_len(f, body[f])
            setattr(bank, f, body[f])
    if "pix_key_type" in body:
        bank.pix_key_type = _norm_bank_pix_type(body.get("pix_key_type"))
    for f in ("is_sandbox", "is_active", "is_primary"):
        if f in body:
            setattr(bank, f, bool(body[f]))
    if "opening_balance" in body:
        bank.opening_balance = _parse_opening_balance(body.get("opening_balance"))
    if "opening_balance_date" in body:
        bank.opening_balance_date = _parse_opening_date(body.get("opening_balance_date"))


async def _demote_other_primaries(warehouse_id: int, keep_id: int, db: AsyncSession) -> None:
    """Garante no máximo 1 conta `is_primary` por galpão."""
    await db.execute(
        update(WarehouseBankAccount)
        .where(
            WarehouseBankAccount.warehouse_id == warehouse_id,
            WarehouseBankAccount.id != keep_id,
        )
        .values(is_primary=False)
    )


@router.get("/{warehouse_id}/bank-accounts")
async def list_bank_accounts(
    warehouse_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_menu_permission("go_empresa")),
):
    """Lista as contas de recebimento do galpão (sem a API Key).

    Gated por `go_empresa` (igual à escrita): a lista traz dado pessoal do titular (CPF/CNPJ,
    chave Pix) — não é exposta a quem não administra a empresa/galpão.
    """
    await _get_warehouse_for_user(warehouse_id, current_user, db)
    rows = (
        await db.execute(
            select(WarehouseBankAccount)
            .where(WarehouseBankAccount.warehouse_id == warehouse_id)
            .order_by(WarehouseBankAccount.id)
        )
    ).scalars().all()
    return [_serialize_bank(b) for b in rows]


@router.post("/{warehouse_id}/bank-accounts", status_code=201)
async def create_bank_account(
    warehouse_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_menu_permission("go_empresa")),
):
    """Cadastra uma conta de recebimento (ex.: ASAAS) no galpão. API Key cifrada."""
    await _get_warehouse_for_user(warehouse_id, current_user, db)
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="Nome/rótulo da conta é obrigatório")

    bank = WarehouseBankAccount(warehouse_id=warehouse_id, name=name)
    _apply_bank_fields(bank, body)
    bank.name = name
    api_key = (body.get("api_key") or "").strip()
    if api_key:
        try:
            bank.api_key_encrypted = crypto.encrypt(api_key)
        except crypto.CryptoError as e:
            raise HTTPException(status_code=400, detail=f"Não foi possível cifrar a API Key: {e}")
    db.add(bank)
    await db.flush()
    if bank.is_primary:
        await _demote_other_primaries(warehouse_id, bank.id, db)
    await db.commit()
    await db.refresh(bank)
    return _serialize_bank(bank)


@router.put("/{warehouse_id}/bank-accounts/{bank_id}")
async def update_bank_account(
    warehouse_id: int,
    bank_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_menu_permission("go_empresa")),
):
    """Edita uma conta de recebimento. API Key: em branco/ausente mantém a atual (remover = excluir)."""
    await _get_warehouse_for_user(warehouse_id, current_user, db)
    # Anti-IDOR: filtra pelo PAR (id, warehouse_id) — não basta o galpão do path.
    bank = (
        await db.execute(
            select(WarehouseBankAccount).where(
                WarehouseBankAccount.id == bank_id,
                WarehouseBankAccount.warehouse_id == warehouse_id,
            )
        )
    ).scalar_one_or_none()
    if not bank:
        raise HTTPException(status_code=404, detail="Conta bancária não encontrada neste Galpão")

    _apply_bank_fields(bank, body)
    if "api_key" in body and (body.get("api_key") or "").strip():
        try:
            bank.api_key_encrypted = crypto.encrypt(body["api_key"].strip())
        except crypto.CryptoError as e:
            raise HTTPException(status_code=400, detail=f"Não foi possível cifrar a API Key: {e}")
    if bank.is_primary:
        await _demote_other_primaries(warehouse_id, bank.id, db)
    await db.commit()
    await db.refresh(bank)
    return _serialize_bank(bank)


@router.delete("/{warehouse_id}/bank-accounts/{bank_id}", status_code=204)
async def delete_bank_account(
    warehouse_id: int,
    bank_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_menu_permission("go_empresa")),
):
    """Remove uma conta de recebimento do galpão."""
    await _get_warehouse_for_user(warehouse_id, current_user, db)
    bank = (
        await db.execute(
            select(WarehouseBankAccount).where(
                WarehouseBankAccount.id == bank_id,
                WarehouseBankAccount.warehouse_id == warehouse_id,
            )
        )
    ).scalar_one_or_none()
    if not bank:
        raise HTTPException(status_code=404, detail="Conta bancária não encontrada neste Galpão")
    # Falha alto: a conta tem FK ON DELETE CASCADE em payment_charges — excluir apagaria o
    # histórico financeiro (cobranças/estornos) em silêncio. Bloqueia e manda desativar.
    from models.payment import PaymentCharge

    has_charges = (
        await db.execute(
            select(PaymentCharge.id).where(PaymentCharge.bank_account_id == bank_id).limit(1)
        )
    ).first()
    if has_charges:
        raise HTTPException(
            status_code=409,
            detail="Conta tem cobranças registradas e não pode ser excluída. "
            "Desative-a (is_active=false) para preservar o histórico financeiro.",
        )
    db.delete(bank)
    await db.commit()


async def _get_bank_for_user(
    warehouse_id: int, bank_id: int, user: User, db: AsyncSession
) -> WarehouseBankAccount:
    """Carrega a conta bancária com isolamento por galpão + anti-IDOR (par id, warehouse_id)."""
    await _get_warehouse_for_user(warehouse_id, user, db)
    bank = (
        await db.execute(
            select(WarehouseBankAccount).where(
                WarehouseBankAccount.id == bank_id,
                WarehouseBankAccount.warehouse_id == warehouse_id,
            )
        )
    ).scalar_one_or_none()
    if not bank:
        raise HTTPException(status_code=404, detail="Conta bancária não encontrada neste Galpão")
    return bank


@router.post("/{warehouse_id}/bank-accounts/{bank_id}/test-connection")
async def test_bank_connection(
    warehouse_id: int,
    bank_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_menu_permission("go_empresa")),
):
    """Valida a API Key da conta ASAAS (GET /myAccount). Falha alto com mensagem clara."""
    bank = await _get_bank_for_user(warehouse_id, bank_id, current_user, db)
    if bank.provider != "asaas":
        raise HTTPException(status_code=400, detail="Teste disponível apenas para contas ASAAS.")
    from services import asaas_service
    try:
        return await asaas_service.test_connection(bank)
    except asaas_service.AsaasError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{warehouse_id}/bank-accounts/{bank_id}/configure-webhook")
async def configure_bank_webhook(
    warehouse_id: int,
    bank_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_menu_permission("go_empresa")),
):
    """Registra no ASAAS o webhook desta conta (URL pública do sistema) com um authToken gerado
    por nós; guarda só o HASH do token (valida o header `asaas-access-token` no recebimento)."""
    bank = await _get_bank_for_user(warehouse_id, bank_id, current_user, db)
    if bank.provider != "asaas":
        raise HTTPException(status_code=400, detail="Webhook disponível apenas para contas ASAAS.")
    from config import get_settings
    from services import asaas_service

    base = (get_settings().FRONTEND_URL or "").rstrip("/")
    if not base:
        raise HTTPException(status_code=400, detail="URL pública (FRONTEND_URL) não configurada no servidor.")
    webhook_url = f"{base}/api/v1/webhooks/asaas"
    try:
        token = await asaas_service.ensure_webhook(bank, webhook_url)
    except asaas_service.AsaasError as e:
        raise HTTPException(status_code=400, detail=str(e))
    bank.webhook_token_hash = asaas_service.token_hash(token)
    await db.commit()
    return {"ok": True, "webhook_url": webhook_url, "webhook_configured": True}
