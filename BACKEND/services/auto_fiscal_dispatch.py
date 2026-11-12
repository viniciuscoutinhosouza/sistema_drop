"""Emissão AUTOMÁTICA de NF-e ao ficar "Pronto p/ Envio" (ADR-0041).

Ponto único agnóstico. Dispara a emissão de NF-e de pedidos NÃO-FULL assim que ficam
ready_to_ship/invoice_pending, roteada por `nfe_emission_mode` da conta (own × marketplace,
migration 151) — OPT-IN por conta (`nfe_auto_emit`, migration 184). O opt-in por conta SUBSTITUI
a confirmação por-pedido da ADR-0030 como ato de consentimento do dono.

DESENHO (incorpora o pre-audit):
- **Reuso do núcleo, não de um 2º switch (regra de ouro ADR-0020):** a etapa de emissão chama o
  roteador único `routers.orders.emit_order_nfe(..., current_user=None)` — o MESMO usado pelo botão
  manual, agora com ator de SISTEMA (escopo pulado; `created_by_user_id=NULL`). Nada de reimplementar
  a decisão fiscal aqui. O único branch-por-plataforma é a etapa de FINALIZAÇÃO (ML: destrava a nota
  + reaquece a etiqueta com a DANFE; Shopee: confirma a validação na Shopee), que já é naturalmente
  ramificada.
- **Claim atômico (anti dupla-emissão):** `arm_if_eligible` faz um UPDATE…WHERE condicional (compare-
  and-set) — dois ticks do poll (ou poll+webhook) não re-armam o mesmo pedido, e não re-arma estado
  terminal.
- **Gate de homologação:** só age em ambiente de PRODUÇÃO (homolog não tem valor fiscal → nenhum ato
  silencioso; vira 'error' observável até habilitarem produção).
- **Falhar alto, nunca em silêncio:** toda falha vai para `orders.auto_fiscal_error` + contador de
  tentativas com teto (`auto_fiscal_attempts`) p/ não bater na SEFAZ no mesmo pedido doomed a cada tick.
- **Lane de workflow, não verdade fiscal:** `auto_fiscal_status` (emitting|emitted|done|error) é só
  observabilidade; o SSOT da autorização continua em `nfe_status`/`Invoice`.
"""

import logging
import re

from sqlalchemy import or_, select, update

from models.integration import MarketplaceAccount
from models.order import Order

logger = logging.getLogger(__name__)

# Teto de tentativas da ETAPA DE EMISSÃO (erro de prontidão — NCM/CFOP/cert — reincide a cada tick).
_MAX_ATTEMPTS = 5
# Teto da ETAPA DE FINALIZAÇÃO (nota não resolve: ML preso em pending, Shopee nunca valida, rede
# fora). 5 min/tick → ~6 h de teto antes de 'error' VISÍVEL (a nota costuma resolver em minutos).
_MAX_FINALIZE_TICKS = 72
# Estados da lane automática.
_ST_EMITTING = "emitting"
_ST_EMITTED = "emitted"
_ST_DONE = "done"
_ST_ERROR = "error"

# LGPD: mascara CPF/CNPJ (cru ou formatado) nas mensagens de erro antes de persistir/logar — rejeições
# da SEFAZ/Shopee ecoam o documento do comprador. Paridade com o "loga sem PII" do fluxo manual.
_DOC_PATTERNS = (
    re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}"),  # CNPJ formatado
    re.compile(r"\d{3}\.\d{3}\.\d{3}-\d{2}"),        # CPF formatado
    re.compile(r"\d{11,14}"),                        # CPF/CNPJ cru
)


def sanitize_fiscal_msg(msg) -> str:
    out = str(msg or "")
    for p in _DOC_PATTERNS:
        out = p.sub("***", out)
    return out[:500]


def _light_eligible(order: Order, account: MarketplaceAccount) -> bool:
    """Checagem BARATA (sem I/O) usada no hook de transição para decidir se arma o pedido.

    As checagens que exigem I/O (CPF por-pedido, ambiente de produção, rastreável) rodam no JOB,
    antes do ato fiscal — se o pedido for inelegível lá, vira 'error' VISÍVEL (falha alto)."""
    from services.fiscal.emission_router import is_full_order

    if not account or not getattr(account, "nfe_auto_emit", False):
        return False
    if (account.platform or "") not in ("mercadolivre", "shopee"):
        return False
    if is_full_order(order):
        return False
    # Já tem nota (ou em curso) → nada a emitir.
    if (order.nfe_status or "") in ("authorized", "pending", "in_process"):
        return False
    # Já está numa lane automática (armado/terminado) → não re-arma.
    if (order.auto_fiscal_status or "") != "":
        return False
    return True


async def arm_if_eligible(db, order: Order, account: MarketplaceAccount) -> bool:
    """CLAIM ATÔMICO: marca `auto_fiscal_status='emitting'` SOMENTE se ainda está livre e sem nota.

    Chamado pelos hooks de transição (webhook_service, ML e Shopee). O UPDATE…WHERE condicional é o
    compare-and-set — se outro tick já armou/emitiu, o rowcount é 0 e não faz nada. Barato: não emite
    nada aqui (o trabalho fiscal pesado é do job)."""
    if not _light_eligible(order, account):
        return False
    stmt = (
        update(Order)
        .where(
            Order.id == order.id,
            Order.auto_fiscal_status.is_(None),
            # NULL NOT IN (...) é UNKNOWN no Oracle → excluía o pedido SEM NF-e (nfe_status NULL),
            # que é justamente o que precisa emitir. Trata NULL explicitamente (espelha _light_eligible,
            # que já usa `(nfe_status or "") in (...)`). Sem isto o claim nunca armava e o job ficava ocioso.
            or_(
                Order.nfe_status.is_(None),
                Order.nfe_status.notin_(["authorized", "pending", "in_process"]),
            ),
        )
        .values(auto_fiscal_status=_ST_EMITTING)
    )
    res = await db.execute(stmt)
    armed = (getattr(res, "rowcount", 0) or 0) > 0
    if armed:
        order.auto_fiscal_status = _ST_EMITTING
        await db.commit()
        logger.info("[auto_fiscal] armado order=%s (%s)", order.id, account.platform)
    return armed


async def _fiscal_is_production(db, order: Order) -> bool:
    """True se a CMIG do pedido emite em PRODUÇÃO (gate de homologação)."""
    if not order.cmig_id:
        return False
    try:
        from models.fiscal import CMIGFiscalConfig

        cfg = (
            await db.execute(
                select(CMIGFiscalConfig).where(CMIGFiscalConfig.cmig_id == order.cmig_id)
            )
        ).scalar_one_or_none()
        return (getattr(cfg, "environment", None) or "homolog").lower() == "production"
    except Exception:  # noqa: BLE001
        return False


async def _set_error(db, order: Order, msg: str) -> None:
    safe = sanitize_fiscal_msg(msg)
    order.auto_fiscal_status = _ST_ERROR
    order.auto_fiscal_error = safe
    await db.commit()
    logger.warning("[auto_fiscal] order=%s ERRO: %s", order.id, safe)


async def _finalize_wait(db, order: Order, note: str) -> None:
    """Nota ainda não resolveu: reagenda (permanece 'emitted') com TETO — ao estourar, vira 'error'
    VISÍVEL (falhar alto, nunca em silêncio). Usa `auto_fiscal_attempts` zerado ao entrar em 'emitted'."""
    order.auto_fiscal_attempts = (order.auto_fiscal_attempts or 0) + 1
    if order.auto_fiscal_attempts >= _MAX_FINALIZE_TICKS:
        await _set_error(db, order, f"NF-e não resolveu a tempo — verifique no marketplace/Fiscal. ({note})")
    else:
        await db.commit()
        logger.info("[auto_fiscal] order=%s aguardando (%s/%s): %s",
                    order.id, order.auto_fiscal_attempts, _MAX_FINALIZE_TICKS, sanitize_fiscal_msg(note))


async def _do_emit(db, order: Order, account: MarketplaceAccount) -> None:
    """Etapa de EMISSÃO (auto_fiscal_status='emitting'). Reusa o roteador único como ator de sistema.

    Ordem dos gates (espelha o manual + corrige o Invoice Issuer): CPF → Shopee Invoice Issuer →
    gate de produção (SÓ p/ emissão própria `own`; no ML marketplace/Faturador a nota é real do MKT) →
    unicidade → recuperação N-6 (não re-transmitir 'processing') → ato fiscal."""
    from routers.orders import _order_issuer_type
    from services.fiscal.emission_router import account_nfe_mode

    mode = account_nfe_mode(account)

    # CPF (por-PEDIDO) fora da emissão própria automática (ML→DC-e, Shopee→Invoice Issuer).
    if await _order_issuer_type(db, order) == "cpf":
        await _set_error(db, order, "Conta/pedido CPF não usa emissão própria automática (ML→DC-e, Shopee→Invoice Issuer).")
        return

    # Shopee 'marketplace' = Invoice Issuer: a Shopee emite SOZINHA — não comandamos NEM gateamos por
    # produção (a nota é real, da Shopee). Segue direto p/ finalização (aguarda a chave).
    if account.platform == "shopee" and mode == "marketplace":
        order.auto_fiscal_status = _ST_EMITTED
        order.auto_fiscal_attempts = 0
        await db.commit()
        logger.info("[auto_fiscal] order=%s Shopee Invoice Issuer — aguardando a Shopee emitir", order.id)
        return

    # Gate de homologação: SÓ p/ emissão PRÓPRIA (own). No ML 'marketplace' (Faturador) a nota é real
    # do ML — não depende do nosso ambiente SEFAZ.
    if mode == "own" and not await _fiscal_is_production(db, order):
        await _set_error(db, order, "Emissão própria automática só em PRODUÇÃO — habilite o ambiente na Configuração Fiscal da CMIG.")
        return

    # Re-checagem imediata de unicidade ANTES do ato fiscal (converge nas travas existentes).
    await db.refresh(order)
    if (order.nfe_status or "") in ("authorized", "pending", "in_process"):
        order.auto_fiscal_status = _ST_EMITTED  # já tem nota em curso → segue p/ finalização
        order.auto_fiscal_attempts = 0
        await db.commit()
        return

    # Recuperação N-6: se já há invoice em 'processing' (número reservado, talvez já na SEFAZ), NÃO
    # re-transmitir (duplicaria a NF-e) — consultar o status pela chave.
    if order.invoice_id:
        from models.fiscal import Invoice

        inv = (
            await db.execute(select(Invoice).where(Invoice.id == order.invoice_id))
        ).scalar_one_or_none()
        if inv and inv.status == "processing":
            await _recover_processing(db, order)
            return

    # Ato fiscal: reusa o roteador único (own → SEFAZ+informa; ML marketplace → Faturador; Shopee own
    # → emite+anexa). current_user=None = ator de sistema.
    try:
        from routers.orders import emit_order_nfe

        await emit_order_nfe(order.id, {"confirm": True}, current_user=None, db=db)
        order.auto_fiscal_status = _ST_EMITTED
        order.auto_fiscal_error = None
        order.auto_fiscal_attempts = 0  # zera p/ a finalização ter contador próprio (teto distinto)
        await db.commit()
        logger.info("[auto_fiscal] order=%s emitida/comandada (modo %s)", order.id, mode)
    except Exception as e:  # noqa: BLE001 — classifica por tentativas (erro de prontidão reincide)
        detail = sanitize_fiscal_msg(getattr(e, "detail", None) or str(e))
        try:
            order.auto_fiscal_attempts = (order.auto_fiscal_attempts or 0) + 1
            order.auto_fiscal_error = detail
            if order.auto_fiscal_attempts >= _MAX_ATTEMPTS:
                order.auto_fiscal_status = _ST_ERROR
                logger.warning("[auto_fiscal] order=%s ERRO (teto): %s", order.id, detail)
            else:
                logger.info("[auto_fiscal] order=%s falha %s/%s: %s",
                            order.id, order.auto_fiscal_attempts, _MAX_ATTEMPTS, detail)
            await db.commit()
        except Exception:  # noqa: BLE001 — a exceção pode ter ENVENENADO a sessão (erro de flush no
            # Oracle, ex.: ORA-12899): gravar attempts/error na mesma sessão falha de novo e o pedido
            # ficaria preso em 'emitting' com attempts=0, re-tentando pra sempre. Rollback, re-carrega o
            # pedido numa sessão limpa e registra o erro (falhar alto, nunca em silêncio).
            await db.rollback()
            fresh = (await db.execute(select(Order).where(Order.id == order.id))).scalar_one_or_none()
            if fresh is not None:
                fresh.auto_fiscal_attempts = (fresh.auto_fiscal_attempts or 0) + 1
                fresh.auto_fiscal_error = detail
                if (fresh.auto_fiscal_attempts or 0) >= _MAX_ATTEMPTS:
                    fresh.auto_fiscal_status = _ST_ERROR
                logger.warning("[auto_fiscal] order=%s erro registrado após rollback: %s", order.id, detail)
                await db.commit()


async def _recover_processing(db, order: Order) -> None:
    """NF-e própria presa em 'processing' (timeout de rede na transmissão): recupera pela consulta N-6
    (pela chave) em vez de re-transmitir (que duplicaria). Reusa `routers.invoices.refresh_status`
    como ator de sistema (current_user=None)."""
    from models.fiscal import Invoice
    from routers.invoices import refresh_status

    try:
        await refresh_status(order.invoice_id, db=db, current_user=None)
    except Exception as e:  # noqa: BLE001 — SEFAZ/rede fora: tenta no próximo tick (com teto)
        order.auto_fiscal_attempts = (order.auto_fiscal_attempts or 0) + 1
        if order.auto_fiscal_attempts >= _MAX_ATTEMPTS:
            await _set_error(db, order, "NF-e presa em 'processamento' na SEFAZ — use 'Atualizar status' na tela Fiscal.")
        else:
            order.auto_fiscal_error = sanitize_fiscal_msg(getattr(e, "detail", None) or str(e))
            await db.commit()
        return
    inv = (
        await db.execute(select(Invoice).where(Invoice.id == order.invoice_id))
    ).scalar_one_or_none()
    if inv and inv.status == "authorized":
        order.nfe_status = "authorized"
        order.nfe_key = inv.access_key
        order.auto_fiscal_status = _ST_EMITTED
        order.auto_fiscal_attempts = 0
        order.auto_fiscal_error = None
        await db.commit()
        logger.info("[auto_fiscal] order=%s recuperada por N-6 (autorizada)", order.id)
    elif inv and inv.status in ("rejected", "error", "cancelled"):
        await _set_error(db, order, f"NF-e própria ficou '{inv.status}'.")
    else:
        order.auto_fiscal_attempts = (order.auto_fiscal_attempts or 0) + 1
        if order.auto_fiscal_attempts >= _MAX_ATTEMPTS:
            await _set_error(db, order, "NF-e presa em 'processamento' na SEFAZ — use 'Atualizar status' na tela Fiscal.")
        else:
            await db.commit()


async def _do_finalize(db, order: Order, account: MarketplaceAccount) -> None:
    """Etapa de FINALIZAÇÃO (auto_fiscal_status='emitted'): aguarda a nota resolver e, no ML,
    reaquece a etiqueta com a DANFE. É o ÚNICO branch-por-plataforma (naturalmente ramificado)."""
    if account.platform == "mercadolivre":
        await _finalize_ml(db, order, account)
    elif account.platform == "shopee":
        await _finalize_shopee(db, order, account)


async def _finalize_ml(db, order: Order, account: MarketplaceAccount) -> None:
    """ML: destrava a nota (reusa fetch_and_cache) e, quando autorizada, reaquece a etiqueta com a
    DANFE (refresh=True) p/ a próxima leitura sair com a chave. NÃO despacha (o despacho físico segue
    no fluxo de Separação)."""
    from routers.orders import fetch_and_cache_order_invoices

    if (order.nfe_status or "") in ("pending", "in_process"):
        try:
            await fetch_and_cache_order_invoices(db, order, account)
        except Exception as e:  # noqa: BLE001 — rede/ML indisponível: reagenda COM TETO
            await _finalize_wait(db, order, f"ML ainda processando: {e}")
            return
    st = order.nfe_status or ""
    if st == "authorized":
        # Reaquece a etiqueta com a DANFE (best-effort; 'não liberada ainda' NÃO é erro — reagenda).
        try:
            from routers.orders import _ml_label_fmt_bytes

            await _ml_label_fmt_bytes(db, order, None, "pdf", refresh=True)
        except Exception as e:  # noqa: BLE001 — ready_to_print pode ainda não ter chegado
            logger.info("[auto_fiscal] order=%s etiqueta DANFE ainda não liberada: %s", order.id, e)
        order.auto_fiscal_status = _ST_DONE
        order.auto_fiscal_error = None
        await db.commit()
        logger.info("[auto_fiscal] order=%s ML DONE (nota autorizada)", order.id)
    elif st in ("rejected", "error", "cancelled"):
        await _set_error(db, order, f"NF-e do ML ficou '{st}'.")
    else:
        await _finalize_wait(db, order, "NF-e do ML ainda não resolveu.")


async def _finalize_shopee(db, order: Order, account: MarketplaceAccount) -> None:
    """Shopee: confirma que a NF-e está VALIDADA na Shopee (own: a que anexamos; marketplace: a que a
    Shopee emitiu). Quando validada → DONE. O ship_order/etiqueta segue no fluxo de Separação (não
    auto-despacha). Reagenda enquanto não valida."""
    try:
        from services import shopee_dispatch
        from services.shopee_auth import get_valid_shopee_token

        token = await get_valid_shopee_token(account, db)
        validated = await shopee_dispatch.invoice_is_validated(order, token, account.shop_id, db)
    except Exception as e:  # noqa: BLE001 — Shopee/rede indisponível: reagenda COM TETO
        await _finalize_wait(db, order, f"Shopee probe falhou: {e}")
        return
    if validated:
        order.auto_fiscal_status = _ST_DONE
        order.auto_fiscal_error = None
        await db.commit()
        logger.info("[auto_fiscal] order=%s Shopee DONE (NF-e validada)", order.id)
    else:
        await _finalize_wait(db, order, "NF-e ainda não validada pela Shopee.")


async def process_order(db, order: Order) -> None:
    """Driver por pedido (chamado pelo job). Roteia por auto_fiscal_status. Idempotente/best-effort."""
    account = (
        await db.execute(
            select(MarketplaceAccount).where(MarketplaceAccount.id == order.account_id)
        )
    ).scalar_one_or_none()
    if not account or not account.is_active or not account.nfe_auto_emit:
        return  # conta desligou o auto / foi desativada → não mexe (lane fica como está)
    status = order.auto_fiscal_status or ""
    if status == _ST_EMITTING:
        await _do_emit(db, order, account)
    elif status == _ST_EMITTED:
        await _do_finalize(db, order, account)
