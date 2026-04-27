"""
Simulador de Custos — Mercado Livre
Endpoints para calcular comissão, frete e margem líquida de anúncios ML.
"""
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from pydantic import BaseModel, Field

from database import get_db
from dependencies import get_current_user
from models.user import User
from models.integration import MarketplaceAccount
from services import ml_service

router = APIRouter()


# ── helpers ────────────────────────────────────────────────────────────────────

async def _get_account_with_token(account_id: int, user: User, db: AsyncSession) -> tuple[MarketplaceAccount, str]:
    result = await db.execute(
        select(MarketplaceAccount)
        .options(selectinload(MarketplaceAccount.administrators))
        .where(MarketplaceAccount.id == account_id, MarketplaceAccount.is_active == True)
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Conta de marketplace não encontrada")
    if user.role not in ("admin", "ugo"):
        admin_ids = {a.user_id for a in account.administrators}
        if user.id not in admin_ids:
            raise HTTPException(status_code=403, detail="Sem acesso a esta conta de marketplace")
    if account.platform != "mercadolivre":
        raise HTTPException(status_code=400, detail="Simulador disponível apenas para Mercado Livre")

    now = datetime.now(timezone.utc)
    expires = account.token_expires_at
    if expires and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires and expires <= now:
        if not account.refresh_token:
            raise HTTPException(status_code=401, detail="Token expirado. Reconecte a conta em Integrações.")
        token_data = await ml_service.refresh_ml_token(account.refresh_token)
        account.access_token = token_data["access_token"]
        account.refresh_token = token_data.get("refresh_token", account.refresh_token)
        account.token_expires_at = now + timedelta(seconds=token_data.get("expires_in", 21600))
        await db.commit()

    if not account.access_token:
        raise HTTPException(status_code=401, detail="Conta sem token. Conecte a conta em Integrações.")

    return account, account.access_token


# ── metadados dos tipos de anúncio ─────────────────────────────────────────────

_LISTING_TYPE_INFO: dict[str, dict] = {
    "free": {
        "label":       "Grátis",
        "fee_range":   "0%",
        "description": "Sem comissão. Duração de 60 dias, baixa exposição nos resultados e sem parcelamento.",
        "restrictions": [
            "Limitado a 5 vendas/ano para produtos novos e 20 vendas/ano para usados",
            "Indisponível para MercadoLíder ou profissionais do Mercado Pago",
            "Não oferece parcelamento em 12x sem juros ao comprador",
            "Menor visibilidade — aparece abaixo dos anúncios Clássico e Premium",
        ],
    },
    "gold_special": {
        "label":       "Clássico",
        "fee_range":   "10%–14%",
        "description": "Tarifa entre 10% e 14% por categoria. Duração ilimitada, exposição média. Sem parcelamento.",
        "restrictions": [
            "Sem parcelamento em 12x sem juros para o comprador",
        ],
    },
    "gold_pro": {
        "label":       "Premium",
        "fee_range":   "15%–19%",
        "description": "Tarifa entre 15% e 19%. Maior visibilidade e parcelamento em 12x sem juros — ideal para vendedores profissionais.",
        "restrictions": [],
    },
}


# ── schemas ────────────────────────────────────────────────────────────────────

class CommissionRequest(BaseModel):
    account_id: int
    price: float = Field(..., gt=0, description="Preço de venda do produto")
    category_id: str = Field(..., description="ID da categoria ML (ex: MLB1055)")
    listing_type_id: str = Field(
        "gold_special",
        description="Tipo de anúncio: free (Grátis) | gold_special (Clássico) | gold_pro (Premium)",
    )
    shipping_mode: str = Field("me2", description="Modalidade de envio: me2 | me1")
    logistic_type: str = Field("drop_off", description="Tipo logístico: drop_off | fulfillment | xd_drop_off | cross_docking")


class ShippingRequest(BaseModel):
    account_id: int
    price: float = Field(..., gt=0, description="Preço de venda do produto")
    listing_type_id: str = Field("gold_special", description="Tipo de anúncio")
    shipping_mode: str = Field("me2", description="Modalidade de envio")
    logistic_type: str = Field("drop_off", description="Tipo logístico")
    weight_kg: float = Field(..., gt=0, description="Peso em kg")
    height_cm: float = Field(..., gt=0, description="Altura em cm")
    width_cm: float = Field(..., gt=0, description="Largura em cm")
    length_cm: float = Field(..., gt=0, description="Comprimento em cm")


class SimulatorFullRequest(BaseModel):
    account_id: int
    price: float = Field(..., gt=0, description="Preço de venda do produto")
    cost_price: float | None = Field(None, ge=0, description="Custo do produto (para margem sobre custo)")
    category_id: str = Field(..., description="ID da categoria ML")
    listing_type_id: str = Field("gold_special", description="Tipo de anúncio")
    shipping_mode: str = Field("me2", description="Modalidade de envio")
    logistic_type: str = Field("drop_off", description="Tipo logístico")
    weight_kg: float | None = Field(None, gt=0, description="Peso em kg (necessário para calcular frete)")
    height_cm: float | None = Field(None, gt=0, description="Altura em cm")
    width_cm: float | None = Field(None, gt=0, description="Largura em cm")
    length_cm: float | None = Field(None, gt=0, description="Comprimento em cm")
    free_shipping: bool = Field(True, description="Anúncio com frete grátis (custo para vendedor)")


# ── endpoints ──────────────────────────────────────────────────────────────────

@router.get("/listing-types")
async def list_listing_types():
    """
    Lista todos os tipos de anúncio do Mercado Livre Brasil com estrutura de taxas.
    Não requer autenticação.
    """
    types = await ml_service.get_listing_types_ml()
    return {"listing_types": types}


@router.post("/commission")
async def simulate_commission(
    body: CommissionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Calcula a composição real da taxa de venda ML para o anúncio configurado.

    Retorna os 3 componentes separados (meli_percentage_fee, financing_add_on_fee, fixed_fee)
    mais o total consolidado (sale_fee_amount = valor real a subtrair do preço de venda),
    junto com metadados do tipo de anúncio e receita líquida estimada sem frete.
    """
    _, access_token = await _get_account_with_token(body.account_id, current_user, db)
    commission = await ml_service.get_commission_details(
        access_token=access_token,
        price=body.price,
        category_id=body.category_id,
        listing_type=body.listing_type_id,
        shipping_mode=body.shipping_mode,
        logistic_type=body.logistic_type,
    )
    info = _LISTING_TYPE_INFO.get(body.listing_type_id, {})
    return {
        **commission,
        # Contexto de preço e receita (sem frete)
        "price":                   round(body.price, 2),
        "net_revenue_before_ship": round(body.price - commission["sale_fee_amount"], 2),
        # Metadados do tipo de anúncio
        "listing_type_label":        info.get("label", body.listing_type_id),
        "listing_type_fee_range":    info.get("fee_range", ""),
        "listing_type_description":  info.get("description", ""),
        "listing_type_restrictions": info.get("restrictions", []),
    }


@router.post("/shipping")
async def simulate_shipping(
    body: ShippingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Calcula o custo de frete grátis (subsidiado pelo vendedor) para as dimensões informadas.

    Retorna: custo bruto de tabela, desconto ML e custo líquido ao vendedor.
    """
    account, access_token = await _get_account_with_token(body.account_id, current_user, db)
    if not account.platform_user_id:
        raise HTTPException(
            status_code=400,
            detail="Conta sem seller_id registrado. Reconecte a conta no Mercado Livre.",
        )
    return await ml_service.get_shipping_details(
        access_token=access_token,
        seller_id=account.platform_user_id,
        price=body.price,
        listing_type=body.listing_type_id,
        shipping_mode=body.shipping_mode,
        logistic_type=body.logistic_type,
        weight_kg=body.weight_kg,
        height_cm=body.height_cm,
        width_cm=body.width_cm,
        length_cm=body.length_cm,
    )


@router.post("/full")
async def simulate_full(
    body: SimulatorFullRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Simulação completa: comissão + frete + receita líquida + margem sobre venda.
    Se `cost_price` for informado, calcula também lucro bruto e margem sobre custo.
    Se dimensões não forem fornecidas, frete é considerado 0.
    """
    account, access_token = await _get_account_with_token(body.account_id, current_user, db)
    costs = await ml_service.get_listing_costs(
        access_token=access_token,
        seller_id=account.platform_user_id or "",
        price=body.price,
        category_id=body.category_id,
        listing_type=body.listing_type_id,
        shipping_mode=body.shipping_mode,
        logistic_type=body.logistic_type,
        weight_kg=body.weight_kg,
        height_cm=body.height_cm,
        width_cm=body.width_cm,
        length_cm=body.length_cm,
        free_shipping=body.free_shipping,
    )

    gross_profit: float | None = None
    margin_on_cost_pct: float | None = None
    if body.cost_price is not None and body.cost_price > 0:
        gross_profit = round(costs["net_revenue"] - body.cost_price, 2)
        margin_on_cost_pct = round((gross_profit / body.cost_price) * 100, 2)

    return {
        **costs,
        "cost_price":          body.cost_price,
        "gross_profit":        gross_profit,
        "margin_on_cost_pct":  margin_on_cost_pct,
        "listing_type_id":     body.listing_type_id,
        "logistic_type":       body.logistic_type,
    }
