"""Cliente HTTP para a API Focus NFe.

Documentação oficial: https://focusnfe.com.br/doc/

Autenticação: HTTP Basic com o token como `username` e senha vazia.
Multi-CNPJ: cada empresa emissora tem seu próprio token (`focus_company_token`),
gerenciado em `cmig_fiscal_config`.
"""
from __future__ import annotations
import json
import re
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any
import httpx

from config import get_settings
from models.fiscal import Invoice, CMIGFiscalConfig
from models.cmig import CMIG
from models.person import Person

log = logging.getLogger(__name__)
settings = get_settings()


# ── Helpers internos ──────────────────────────────────────────────────────────

def _base_url(env: str) -> str:
    return settings.FOCUS_NFE_BASE_PROD if env == "production" else settings.FOCUS_NFE_BASE_HOMOLOG


def _digits(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


def _f(v) -> float:
    """Decimal/None → float (0 se None)."""
    if v is None:
        return 0.0
    return float(v)


def _f_or_none(v) -> float | None:
    if v is None:
        return None
    return float(v)


def _client(token: str) -> httpx.AsyncClient:
    """Cria cliente HTTP autenticado para o Focus."""
    if not token:
        raise FocusError("Token Focus NFe não configurado para esta CMIG")
    return httpx.AsyncClient(
        auth=(token, ""),
        timeout=settings.FOCUS_NFE_TIMEOUT,
        headers={"Accept": "application/json"},
    )


class FocusError(Exception):
    """Erro de comunicação ou de negócio com o Focus NFe."""

    def __init__(self, message: str, status_code: int | None = None, payload: Any = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.payload = payload


def _handle_response(resp: httpx.Response) -> dict:
    """Trata resposta padrão do Focus. Retorna dict; eleva FocusError em erro."""
    try:
        data = resp.json() if resp.content else {}
    except json.JSONDecodeError:
        data = {"raw": resp.text}

    if resp.status_code >= 400:
        # Focus retorna {"codigo": "...", "mensagem": "..."} ou {"erros": [...]}
        msg = (
            data.get("mensagem")
            or data.get("message")
            or (data.get("erros") and data["erros"][0].get("mensagem"))
            or f"Erro HTTP {resp.status_code}"
        )
        raise FocusError(msg, status_code=resp.status_code, payload=data)

    return data


# ── Empresa (cadastro + certificado) ──────────────────────────────────────────

async def register_company(cfg: CMIGFiscalConfig, cmig: CMIG, master_token: str) -> dict:
    """Registra a empresa (CNPJ) no Focus NFe usando o token mestre da conta.

    Após o registro, o Focus retorna um `token_homologacao` ou `token_producao`
    específico daquela empresa, que será usado em todas as chamadas subsequentes.
    """
    if not master_token:
        raise FocusError("Token mestre (FOCUS_NFE_TOKEN_MASTER) não fornecido")

    payload = {
        "cnpj": _digits(cmig.cnpj),
        "nome": cmig.company_name,
        "nome_fantasia": cmig.trade_name or cmig.company_name,
        "email": cmig.email or cfg.fiscal_email_copy or "",
        "telefone": _digits(cmig.phone),
        "regime_tributario": cfg.crt or 1,
        "inscricao_estadual": cfg.ie or "",
        "inscricao_municipal": cfg.im or "",
        "logradouro": cmig.street or "",
        "numero": cmig.address_number or "",
        "complemento": cmig.complement or "",
        "bairro": cmig.neighborhood or "",
        "municipio": cmig.city or "",
        "uf": cmig.state or "",
        "cep": _digits(cmig.zip_code),
        "habilita_nfe": True,
        "habilita_nfce": False,
    }
    url = f"{_base_url(cfg.environment)}/v2/empresas"
    async with _client(master_token) as client:
        resp = await client.post(url, json=payload)
    return _handle_response(resp)


async def upload_certificate(cfg: CMIGFiscalConfig, cmig: CMIG, master_token: str,
                              pfx_bytes: bytes, password: str) -> dict:
    """Faz upload do certificado A1 (.pfx) para o Focus.

    Focus armazena o certificado em cofre próprio; nada fica no servidor local.
    """
    if not master_token:
        raise FocusError("Token mestre (FOCUS_NFE_TOKEN_MASTER) não fornecido")

    cnpj = _digits(cmig.cnpj)
    url = f"{_base_url(cfg.environment)}/v2/empresas/{cnpj}/certificado"
    files = {"arquivo": ("cert.pfx", pfx_bytes, "application/x-pkcs12")}
    data = {"senha": password}
    async with _client(master_token) as client:
        resp = await client.post(url, files=files, data=data)
    return _handle_response(resp)


# ── NFe — emissão / consulta / cancelamento / CCe / email ────────────────────

def _build_nfe_payload(inv: Invoice, cmig: CMIG, cfg: CMIGFiscalConfig,
                       person: Person, items: list, carrier: Person | None = None) -> dict:
    """Monta o JSON de NFe no formato esperado pelo Focus NFe."""
    ide = {
        "natureza_operacao": inv.natureza_operacao or "Venda",
        "data_emissao": (inv.issue_date or datetime.utcnow()).isoformat(),
        "data_entrada_saida": (inv.exit_date or inv.issue_date or datetime.utcnow()).isoformat(),
        "tipo_documento": 1,                    # 0=entrada, 1=saída
        "finalidade_emissao": _finalidade_focus(inv.purpose),
        "presenca_comprador": 9,                # 9 = não se aplica
        "modalidade_frete": int(inv.freight_modality) if inv.freight_modality is not None else 9,
        "local_destino": 1,                     # 1=interna 2=interestadual 3=exterior
    }

    emit_data = {
        "cnpj_emitente": _digits(cmig.cnpj),
        "nome_emitente": cmig.company_name,
        "nome_fantasia_emitente": cmig.trade_name or cmig.company_name,
        "logradouro_emitente": cmig.street or "",
        "numero_emitente": cmig.address_number or "",
        "complemento_emitente": cmig.complement or "",
        "bairro_emitente": cmig.neighborhood or "",
        "municipio_emitente": cmig.city or "",
        "uf_emitente": cmig.state or "",
        "cep_emitente": _digits(cmig.zip_code),
        "inscricao_estadual_emitente": cfg.ie or "",
        "regime_tributario_emitente": cfg.crt or 1,
    }

    dest_doc = _digits(person.document)
    dest_data = {
        "nome_destinatario": person.name,
        "logradouro_destinatario": person.street or "",
        "numero_destinatario": person.address_number or "",
        "complemento_destinatario": person.complement or "",
        "bairro_destinatario": person.neighborhood or "",
        "municipio_destinatario": person.city or "",
        "uf_destinatario": person.state or "",
        "cep_destinatario": _digits(person.zip_code),
        "pais_destinatario": "Brasil",
        "telefone_destinatario": _digits(person.phone) or None,
        "email_destinatario": person.email or None,
    }
    if person.person_type == "PJ" and len(dest_doc) == 14:
        dest_data["cnpj_destinatario"] = dest_doc
        dest_data["inscricao_estadual_destinatario"] = (
            "ISENTO" if person.ie_isento else (person.ie or "ISENTO")
        )
        dest_data["indicador_inscricao_estadual_destinatario"] = 9 if person.ie_isento else 1
    elif len(dest_doc) == 11:
        dest_data["cpf_destinatario"] = dest_doc
        dest_data["indicador_inscricao_estadual_destinatario"] = 9

    payload = {**ide, **emit_data, **dest_data}

    # Itens
    payload["items"] = [_build_item_payload(it) for it in items]

    # Pagamento
    if inv.payment_method:
        payload["formas_pagamento"] = [{
            "forma_pagamento": inv.payment_method,
            "valor_pagamento": _f(inv.total_invoice),
        }]

    # Transporte
    if carrier:
        carrier_doc = _digits(carrier.document)
        payload["transportador_nome"] = carrier.name
        if len(carrier_doc) == 14:
            payload["transportador_cnpj"] = carrier_doc
        elif len(carrier_doc) == 11:
            payload["transportador_cpf"] = carrier_doc
        if carrier.ie:
            payload["transportador_inscricao_estadual"] = carrier.ie

    # Informação adicional
    if inv.additional_info:
        payload["informacoes_adicionais_contribuinte"] = inv.additional_info[:2000]
    if inv.fiscal_info:
        payload["informacoes_adicionais_fisco"] = inv.fiscal_info[:2000]

    return payload


def _finalidade_focus(purpose: str) -> int:
    """Mapeia purpose interno para finNFe do Focus.
    1=Normal 2=Complementar 3=Ajuste 4=Devolução"""
    return {
        "venda": 1, "remessa": 1, "transferencia": 1, "outros": 1, "retorno": 1,
        "complementar": 2, "ajuste": 3, "devolucao": 4,
    }.get(purpose or "venda", 1)


def _build_item_payload(it) -> dict:
    """Monta um item no formato Focus NFe."""
    p = {
        "numero_item": it.item_number,
        "codigo_produto": str(it.cmig_product_id or it.id),
        "descricao": it.description or "",
        "cfop": it.cfop or "5102",
        "ncm": it.ncm or "",
        "unidade_comercial": it.unit or "UN",
        "quantidade_comercial": _f(it.quantity),
        "valor_unitario_comercial": _f(it.unit_value),
        "valor_unitario_tributavel": _f(it.unit_value),
        "unidade_tributavel": it.unit or "UN",
        "quantidade_tributavel": _f(it.quantity),
        "valor_bruto": _f(it.total_value),
        "origem_mercadoria": it.origin or 0,
    }
    if it.cest:
        p["cest"] = it.cest
    if it.ean:
        p["codigo_barras_comercial"] = it.ean
        p["codigo_barras_tributavel"] = it.ean
    else:
        p["codigo_barras_comercial"] = "SEM GTIN"
        p["codigo_barras_tributavel"] = "SEM GTIN"

    # ICMS — CSOSN para Simples (CRT 1/2), CST para Normal (CRT 3)
    if it.icms_csosn:
        p["icms_situacao_tributaria"] = it.icms_csosn
    elif it.icms_cst:
        p["icms_situacao_tributaria"] = it.icms_cst
    else:
        p["icms_situacao_tributaria"] = "102"  # default Simples sem ICMS

    if it.icms_aliquota and float(it.icms_aliquota) > 0:
        p["icms_aliquota"] = _f(it.icms_aliquota)
        p["icms_base_calculo"] = _f(it.icms_base or it.total_value)
        p["icms_valor"] = _f(it.icms_value)
        p["icms_modalidade_base_calculo"] = 0

    # PIS / COFINS
    p["pis_situacao_tributaria"] = it.pis_cst or "07"  # 07 = isenta (Simples)
    p["cofins_situacao_tributaria"] = it.cofins_cst or "07"
    if it.pis_aliquota and float(it.pis_aliquota) > 0:
        p["pis_aliquota_porcentual"] = _f(it.pis_aliquota)
        p["pis_base_calculo"] = _f(it.total_value)
        p["pis_valor"] = _f(it.pis_value)
    if it.cofins_aliquota and float(it.cofins_aliquota) > 0:
        p["cofins_aliquota_porcentual"] = _f(it.cofins_aliquota)
        p["cofins_base_calculo"] = _f(it.total_value)
        p["cofins_valor"] = _f(it.cofins_value)

    # Informação adicional do item
    if it.additional_info:
        p["informacoes_adicionais_item"] = it.additional_info[:2000]

    return p


async def emit_nfe(cfg: CMIGFiscalConfig, payload: dict, ref: str) -> dict:
    """Emite NFe assíncrona. Retorna {status, ref, ...}."""
    url = f"{_base_url(cfg.environment)}/v2/nfe?ref={ref}"
    async with _client(cfg.focus_company_token) as client:
        resp = await client.post(url, json=payload)
    return _handle_response(resp)


async def consult_nfe(cfg: CMIGFiscalConfig, ref: str, complete: bool = True) -> dict:
    """Consulta status de uma NFe pela referência."""
    url = f"{_base_url(cfg.environment)}/v2/nfe/{ref}"
    if complete:
        url += "?completa=1"
    async with _client(cfg.focus_company_token) as client:
        resp = await client.get(url)
    return _handle_response(resp)


async def cancel_nfe(cfg: CMIGFiscalConfig, ref: str, justificativa: str) -> dict:
    """Cancela NFe autorizada (até 24h após autorização)."""
    if not justificativa or len(justificativa) < 15:
        raise FocusError("Justificativa de cancelamento deve ter no mínimo 15 caracteres")
    url = f"{_base_url(cfg.environment)}/v2/nfe/{ref}"
    async with _client(cfg.focus_company_token) as client:
        resp = await client.delete(url, params={"justificativa": justificativa})
    return _handle_response(resp)


async def correction_letter(cfg: CMIGFiscalConfig, ref: str, correction: str) -> dict:
    """Carta de Correção Eletrônica (CCe). 15-1000 caracteres."""
    if not correction or len(correction) < 15:
        raise FocusError("Carta de correção deve ter no mínimo 15 caracteres")
    if len(correction) > 1000:
        raise FocusError("Carta de correção deve ter no máximo 1000 caracteres")
    url = f"{_base_url(cfg.environment)}/v2/nfe/{ref}/carta_correcao"
    async with _client(cfg.focus_company_token) as client:
        resp = await client.post(url, json={"correcao": correction})
    return _handle_response(resp)


async def send_email(cfg: CMIGFiscalConfig, ref: str, emails: list[str]) -> dict:
    """Envia XML+DANFE para os e-mails informados."""
    if not emails:
        raise FocusError("Informe ao menos um e-mail")
    url = f"{_base_url(cfg.environment)}/v2/nfe/{ref}/email"
    async with _client(cfg.focus_company_token) as client:
        resp = await client.post(url, json={"emails": emails})
    return _handle_response(resp)


def absolutize_focus_url(cfg: CMIGFiscalConfig, path_or_url: str) -> str:
    """Focus retorna paths relativos (ex: /arquivos/...) — concatena base."""
    if not path_or_url:
        return ""
    if path_or_url.startswith("http"):
        return path_or_url
    return f"{_base_url(cfg.environment)}{path_or_url}"


# ── DFe — NFes recebidas pelo CNPJ ────────────────────────────────────────────

async def list_received(cfg: CMIGFiscalConfig, cnpj: str,
                        per_page: int = 50, since_nsu: int | None = None) -> list[dict]:
    """Lista NFes recebidas pelo CNPJ (paginado).

    Focus retorna até `per_page` registros por chamada. Quando há mais,
    percorremos todas as páginas usando `proximo_nsu` retornado.
    """
    base = _base_url(cfg.environment)
    url = f"{base}/v2/nfes_recebidas"
    params: dict = {"cnpj": _digits(cnpj), "qtd": per_page}
    if since_nsu is not None:
        params["nsu"] = since_nsu

    all_items: list[dict] = []
    async with _client(cfg.focus_company_token) as client:
        while True:
            resp = await client.get(url, params=params)
            data = _handle_response(resp)
            # Resposta: {ultimo_nsu, proximo_nsu, documentos: [{chave, ...}, ...]}
            items = data.get("documentos") if isinstance(data, dict) else (data if isinstance(data, list) else [])
            if not items:
                break
            all_items.extend(items)
            next_nsu = data.get("proximo_nsu") if isinstance(data, dict) else None
            if not next_nsu or next_nsu == params.get("nsu"):
                break
            params["nsu"] = next_nsu
            # Limite de segurança
            if len(all_items) >= 1000:
                break
    return all_items


async def get_received(cfg: CMIGFiscalConfig, chave: str) -> dict:
    """Detalhe de uma NFe recebida (resumo + URLs)."""
    url = f"{_base_url(cfg.environment)}/v2/nfes_recebidas/{chave}"
    async with _client(cfg.focus_company_token) as client:
        resp = await client.get(url)
    return _handle_response(resp)


async def download_received_xml(cfg: CMIGFiscalConfig, chave: str) -> bytes:
    """Baixa XML completo de uma NFe recebida."""
    url = f"{_base_url(cfg.environment)}/v2/nfes_recebidas/{chave}/xml"
    async with _client(cfg.focus_company_token) as client:
        resp = await client.get(url)
    if resp.status_code >= 400:
        try:
            data = resp.json()
            msg = data.get("mensagem") or f"Erro HTTP {resp.status_code}"
        except Exception:
            msg = f"Erro HTTP {resp.status_code}"
        raise FocusError(msg, status_code=resp.status_code)
    return resp.content


async def manifest(cfg: CMIGFiscalConfig, chave: str, tipo: str,
                   justificativa: str | None = None) -> dict:
    """Manifesta uma NFe recebida.

    tipo: 'ciencia' | 'confirmacao' | 'desconhecimento' | 'nao_realizada'
    justificativa: obrigatório para 'desconhecimento' e 'nao_realizada' (15-255 chars)
    """
    if tipo not in ("ciencia", "confirmacao", "desconhecimento", "nao_realizada"):
        raise FocusError(f"Tipo de manifestação inválido: {tipo}")
    if tipo in ("desconhecimento", "nao_realizada"):
        if not justificativa or len(justificativa) < 15:
            raise FocusError("Justificativa de 15+ caracteres obrigatória")
        if len(justificativa) > 255:
            raise FocusError("Justificativa deve ter no máximo 255 caracteres")

    url = f"{_base_url(cfg.environment)}/v2/nfes_recebidas/{chave}/manifestacao"
    payload: dict = {"tipo": tipo}
    if justificativa:
        payload["justificativa"] = justificativa

    async with _client(cfg.focus_company_token) as client:
        resp = await client.post(url, json=payload)
    return _handle_response(resp)
