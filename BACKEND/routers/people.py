import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_user
from models.cmig import CMIG, CMIGAdministrator
from models.person import Person
from models.user import User
from services.fiscal.cnpj_lookup import lookup_cnpj

router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _check_cmig_access(cmig_id: int, user: User, db: AsyncSession) -> CMIG:
    result = await db.execute(select(CMIG).where(CMIG.id == cmig_id))
    cmig = result.scalar_one_or_none()
    if not cmig:
        raise HTTPException(status_code=404, detail="CMIG não encontrada")

    if user.role == "admin":
        return cmig
    if user.role == "ugo":
        if cmig.warehouse_id != user.warehouse_id:
            raise HTTPException(status_code=403, detail="CMIG não pertence ao seu Galpão")
        return cmig
    if user.role == "ac":
        result = await db.execute(
            select(CMIGAdministrator).where(
                and_(CMIGAdministrator.user_id == user.id, CMIGAdministrator.cmig_id == cmig_id)
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=403, detail="Acesso negado a esta CMIG")
        return cmig
    raise HTTPException(status_code=403, detail="Permissão insuficiente")


async def _accessible_cmig_ids(user: User, db: AsyncSession) -> list[int]:
    if user.role == "admin":
        rows = await db.execute(select(CMIG.id))
    elif user.role == "ugo":
        rows = await db.execute(select(CMIG.id).where(CMIG.warehouse_id == user.warehouse_id))
    elif user.role == "ac":
        rows = await db.execute(
            select(CMIGAdministrator.cmig_id).where(CMIGAdministrator.user_id == user.id)
        )
    else:
        return []
    return [r[0] for r in rows.all()]


def _clean_doc(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def _serialize(p: Person) -> dict:
    return {
        "id": p.id,
        "cmig_id": p.cmig_id,
        "person_type": p.person_type,
        "document": p.document,
        "ie": p.ie,
        "ie_isento": bool(p.ie_isento),
        "im": p.im,
        "name": p.name,
        "trade_name": p.trade_name,
        "email": p.email,
        "phone": p.phone,
        "zip_code": p.zip_code,
        "street": p.street,
        "address_number": p.address_number,
        "complement": p.complement,
        "neighborhood": p.neighborhood,
        "city": p.city,
        "state": p.state,
        "ibge_code": p.ibge_code,
        "country_code": p.country_code,
        "is_customer": bool(p.is_customer),
        "is_supplier": bool(p.is_supplier),
        "is_carrier": bool(p.is_carrier),
        "notes": p.notes,
        "is_active": bool(p.is_active),
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("")
async def list_people(
    cmig_id: int | None = Query(None),
    search: str | None = Query(None),
    is_customer: bool | None = Query(None),
    is_supplier: bool | None = Query(None),
    is_carrier: bool | None = Query(None),
    is_active: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    accessible = await _accessible_cmig_ids(current_user, db)
    if not accessible:
        return {"items": [], "total": 0, "page": page, "page_size": page_size}

    stmt = select(Person)
    if cmig_id is not None:
        if cmig_id not in accessible:
            raise HTTPException(status_code=403, detail="Acesso negado a esta CMIG")
        stmt = stmt.where(Person.cmig_id == cmig_id)
    else:
        stmt = stmt.where(Person.cmig_id.in_(accessible))

    if search:
        s = f"%{search.strip()}%"
        s_doc = f"%{_clean_doc(search)}%" if any(c.isdigit() for c in search) else None
        conds = [
            func.lower(Person.name).like(s.lower()),
            func.lower(Person.trade_name).like(s.lower()),
        ]
        if s_doc:
            conds.append(Person.document.like(s_doc))
        stmt = stmt.where(or_(*conds))

    if is_customer is not None:
        stmt = stmt.where(Person.is_customer == is_customer)
    if is_supplier is not None:
        stmt = stmt.where(Person.is_supplier == is_supplier)
    if is_carrier is not None:
        stmt = stmt.where(Person.is_carrier == is_carrier)
    if is_active is not None:
        stmt = stmt.where(Person.is_active == is_active)

    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(total_stmt)).scalar() or 0

    stmt = stmt.order_by(Person.name).offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(stmt)).scalars().all()

    return {
        "items": [_serialize(p) for p in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{person_id}")
async def get_person(
    person_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = (await db.execute(select(Person).where(Person.id == person_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    await _check_cmig_access(p.cmig_id, current_user, db)
    return _serialize(p)


@router.post("", status_code=201)
async def create_person(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cmig_id = body.get("cmig_id")
    if not cmig_id:
        raise HTTPException(status_code=422, detail="cmig_id é obrigatório")
    await _check_cmig_access(cmig_id, current_user, db)

    document = _clean_doc(body.get("document") or "")
    if not document:
        raise HTTPException(status_code=422, detail="document (CPF/CNPJ) é obrigatório")
    if len(document) not in (11, 14):
        raise HTTPException(
            status_code=422, detail="document deve ter 11 (CPF) ou 14 (CNPJ) dígitos"
        )

    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="name é obrigatório")

    person_type = body.get("person_type") or ("PJ" if len(document) == 14 else "PF")
    if person_type not in ("PF", "PJ"):
        raise HTTPException(status_code=422, detail="person_type deve ser 'PF' ou 'PJ'")

    dup = await db.execute(
        select(Person).where(and_(Person.cmig_id == cmig_id, Person.document == document))
    )
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Documento já cadastrado nesta CMIG")

    p = Person(
        cmig_id=cmig_id,
        person_type=person_type,
        document=document,
        ie=body.get("ie"),
        ie_isento=bool(body.get("ie_isento", False)),
        im=body.get("im"),
        name=name,
        trade_name=body.get("trade_name"),
        email=body.get("email"),
        phone=body.get("phone"),
        zip_code=body.get("zip_code"),
        street=body.get("street"),
        address_number=body.get("address_number"),
        complement=body.get("complement"),
        neighborhood=body.get("neighborhood"),
        city=body.get("city"),
        state=body.get("state"),
        ibge_code=body.get("ibge_code"),
        country_code=body.get("country_code") or "1058",
        is_customer=bool(body.get("is_customer", True)),
        is_supplier=bool(body.get("is_supplier", False)),
        is_carrier=bool(body.get("is_carrier", False)),
        notes=body.get("notes"),
        is_active=bool(body.get("is_active", True)),
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return _serialize(p)


@router.patch("/{person_id}")
async def update_person(
    person_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = (await db.execute(select(Person).where(Person.id == person_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    await _check_cmig_access(p.cmig_id, current_user, db)

    editable = {
        "ie",
        "ie_isento",
        "im",
        "name",
        "trade_name",
        "email",
        "phone",
        "zip_code",
        "street",
        "address_number",
        "complement",
        "neighborhood",
        "city",
        "state",
        "ibge_code",
        "country_code",
        "is_customer",
        "is_supplier",
        "is_carrier",
        "notes",
        "is_active",
    }
    for k, v in body.items():
        if k in editable:
            setattr(p, k, v)

    await db.commit()
    await db.refresh(p)
    return _serialize(p)


@router.delete("/{person_id}", status_code=204)
async def delete_person(
    person_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = (await db.execute(select(Person).where(Person.id == person_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Pessoa não encontrada")
    await _check_cmig_access(p.cmig_id, current_user, db)
    db.delete(p)
    await db.commit()


@router.post("/lookup-cnpj")
async def lookup_cnpj_endpoint(
    body: dict,
    current_user: User = Depends(get_current_user),
):
    cnpj = body.get("cnpj")
    if not cnpj:
        raise HTTPException(status_code=422, detail="cnpj é obrigatório")
    data = await lookup_cnpj(cnpj)
    if not data:
        raise HTTPException(status_code=404, detail="CNPJ não encontrado na BrasilAPI")
    return data
