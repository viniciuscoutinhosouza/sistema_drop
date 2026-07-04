"""Orquestração da emissão de DC-e (perfil Marketplace) para um pedido de conta CPF.

Fluxo: carrega pedido/CMIG/cert central → valida autorização → monta `dados` → gera chave
(modelo 99, CNPJ do assinante) → monta XML → assina (A1 da MIG) → transmite à SVRS → parseia
o retorno → persiste em `order_dce`.

Reaproveita a infra de NF-e: `signer.assinar_xml` (XMLDSig A1) e `sefaz_client.extract_cert_pem`
(PFX→PEM p/ mTLS). O transporte é o `dce_client`.
"""

from __future__ import annotations

import contextlib
import json
import os
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select

from config import get_settings
from services.datetime_br import BR_TZ
from services.fiscal.dce import dce_client
from services.fiscal.dce.chave_dce import gerar_cdc, montar_chave_dce
from services.fiscal.dce.exceptions import DceError
from services.fiscal.dce.ibge import resolve_municipio
from services.fiscal.dce.signer_cert import resolve_platform_signer_cert
from services.fiscal.dce.xml_builder_dce import montar_xml_dce
from services.fiscal.dce.dce_signer import assinar_xml_dce
from services.fiscal.sefaz.sefaz_client import extract_cert_pem

# UF → código IBGE (cUF). Vendedores em SP/RJ; mapa completo p/ robustez do destinatário.
_UF_CODIGO = {
    "RO": "11", "AC": "12", "AM": "13", "RR": "14", "PA": "15", "AP": "16", "TO": "17",
    "MA": "21", "PI": "22", "CE": "23", "RN": "24", "PB": "25", "PE": "26", "AL": "27",
    "SE": "28", "BA": "29", "MG": "31", "ES": "32", "RJ": "33", "SP": "35", "PR": "41",
    "SC": "42", "RS": "43", "MS": "50", "MT": "51", "GO": "52", "DF": "53",
}

_NAT_OP_DCE = "remessa de venda em marketplace sem nota fiscal"


@dataclass
class RetornoDce:
    autorizado: bool
    chave: str | None
    protocolo: str | None
    cstat: str | None
    xmotivo: str | None
    xml_assinado: str | None


def _so_digitos(v: str | None) -> str:
    return "".join(c for c in (v or "") if c.isdigit())


async def _endereco_dest(db, order) -> dict:
    """Extrai o endereço do comprador do pedido + resolve o código IBGE do município."""
    raw = order.shipping_address
    end = {}
    if raw:
        try:
            end = json.loads(raw) if isinstance(raw, str) else dict(raw)
        except (ValueError, TypeError):
            end = {}
    cidade = end.get("city") or end.get("cidade") or end.get("municipio") or ""
    uf = (end.get("state") or end.get("uf") or "").upper()[:2]
    if not cidade or not uf:
        raise DceError("Endereço do comprador sem cidade/UF — necessário para o município (IBGE) da DC-e.")
    c_mun, x_mun = await resolve_municipio(db, uf, cidade)
    return {
        "x_lgr": end.get("street") or end.get("logradouro") or end.get("address_line") or "",
        "nro": end.get("number") or end.get("numero") or "S/N",
        "x_cpl": end.get("complement") or end.get("comment") or "",
        "x_bairro": end.get("neighborhood") or end.get("bairro") or "",
        "c_mun": c_mun, "x_mun": x_mun, "uf": uf,
        "cep": _so_digitos(end.get("zip_code") or end.get("zip") or end.get("cep")),
    }


async def build_dce_dados(db, order, cmig, mkt_cfg, *, tp_amb: int, serie: int, numero: int) -> dict:
    """Monta o dict de `dados` para `montar_xml_dce` a partir do pedido + config."""
    from models.order import OrderItem

    cnpj_assinante = _so_digitos(mkt_cfg.cnpj)
    c_uf = (cmig.ibge_code or "")[:2] or _UF_CODIGO.get((cmig.state or "").upper())
    if not c_uf:
        raise DceError("UF/código IBGE do remetente (CMIG) não configurado.")

    dh = datetime.now(BR_TZ)
    aamm = dh.strftime("%y%m")
    c_dc = gerar_cdc()
    chave = montar_chave_dce(
        c_uf=c_uf, aamm=aamm, cnpj_assinante=cnpj_assinante,
        serie=serie, n_dc=numero, tp_emis=1, c_dc=c_dc,
    )

    itens_rows = (
        await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))
    ).scalars().all()
    if not itens_rows:
        raise DceError("Pedido sem itens — não há conteúdo a declarar na DC-e.")
    itens = [
        {
            "x_prod": (it.title or "Item")[:120],
            "q_com": float(it.quantity or 1),
            "v_un_com": float(it.unit_price or 0),
            "v_prod": float((it.unit_price or 0) * (it.quantity or 1)),
        }
        for it in itens_rows
    ]

    dest_doc = _so_digitos(order.buyer_document)
    dest = {
        "x_nome": order.buyer_name or "Consumidor",
        "ender": await _endereco_dest(db, order),
    }
    if len(dest_doc) == 14:
        dest["cnpj"] = dest_doc
    else:
        dest["cpf"] = dest_doc

    return {
        "chave": chave,
        "tp_amb": tp_amb,
        "ide": {
            "c_uf": c_uf, "c_dc": c_dc, "nat_op": _NAT_OP_DCE,
            "serie": serie, "n_dc": numero,
            "dh_emi": dh.strftime("%Y-%m-%dT%H:%M:%S%z")[:-2] + ":" + dh.strftime("%z")[-2:],
            "tp_emis": 1, "ver_proc": "SistemaDrop-1.0",
        },
        "emit": {
            "cpf": _so_digitos(cmig.cpf),
            "x_nome": cmig.company_name or cmig.trade_name or "Remetente",
            "ender": {
                "x_lgr": cmig.street or "", "nro": cmig.address_number or "S/N",
                "x_cpl": cmig.complement or "", "x_bairro": cmig.neighborhood or "",
                "c_mun": cmig.ibge_code or "", "x_mun": cmig.city or "",
                "uf": (cmig.state or "").upper(), "cep": _so_digitos(cmig.zip_code),
            },
        },
        "marketplace": {
            "cnpj": cnpj_assinante, "x_nome": mkt_cfg.company_name, "site": mkt_cfg.site,
        },
        "dest": dest,
        "itens": itens,
        "transp": {"mod_trans": "0"},  # 0 = Correios (ajustar por modalidade do envio)
    }


async def emitir_dce_para_pedido(db, order) -> RetornoDce:
    """Emite a DC-e de um pedido de conta CPF. Persiste `OrderDce`. Levanta DceError em falha
    de negócio (autorização ausente, cert ausente, dados faltando)."""
    from models.cmig import CMIG
    from models.fiscal import CMIGFiscalConfig, OrderDce

    # CMIG do pedido + config fiscal
    cmig = (await db.execute(select(CMIG).where(CMIG.id == order.cmig_id))).scalar_one_or_none()
    if not cmig:
        raise DceError("CMIG do pedido não encontrada.")
    if not cmig.cpf:
        raise DceError("A DC-e só se aplica a contas de vendedor pessoa física (CPF).")
    cfg = (
        await db.execute(select(CMIGFiscalConfig).where(CMIGFiscalConfig.cmig_id == cmig.id))
    ).scalar_one_or_none()
    if not cfg or not cfg.dce_authorized:
        raise DceError(
            "Emissão de DC-e não autorizada para este vendedor. Ative a autorização "
            "'por conta e ordem' no cadastro fiscal da CMIG."
        )

    # Cert central do assinante (A1 da MIG) + config marketplace
    from models.fiscal import PlatformCertConfig
    from services.fiscal.dce.signer_cert import PROFILE_MARKETPLACE_DCE

    mkt_cfg = (
        await db.execute(
            select(PlatformCertConfig).where(
                PlatformCertConfig.profile_type == PROFILE_MARKETPLACE_DCE
            )
        )
    ).scalar_one_or_none()
    if not mkt_cfg:
        raise DceError("Certificado do marketplace (A1 da MIG) não configurado.")

    settings = get_settings()
    tp_amb = 1 if (cfg.production_released and settings and getattr(settings, "NFE_ENV_PROD", False)) else 2
    ambiente = "production" if tp_amb == 1 else "homolog"

    # Numeração (por ambiente)
    if tp_amb == 1:
        numero = int(cfg.dce_next_number or 1)
        cfg.dce_next_number = numero + 1
    else:
        numero = int(cfg.dce_next_number_homolog or 1)
        cfg.dce_next_number_homolog = numero + 1
    serie = int(cfg.dce_serie or 1)
    await db.flush()

    dados = await build_dce_dados(db, order, cmig, mkt_cfg, tp_amb=tp_amb, serie=serie, numero=numero)
    chave = dados["chave"]

    # Monta + assina (A1 da MIG) + transmite
    pfx_path, senha = await resolve_platform_signer_cert(db)
    xml = montar_xml_dce(dados)
    xml_assinado = assinar_xml_dce(xml, pfx_path, senha, ref_id=f"DCe{chave}")

    cert_pem, key_pem = extract_cert_pem(pfx_path, senha, runtime_dir=settings.NFE_CERTS_DIR)
    try:
        verify = tp_amb == 1  # homologação costuma ter cadeia não-ICP; produção verifica
        resp = dce_client.autorizar(xml_assinado, tp_amb, cert_pem, key_pem, verify_ssl=verify)
    finally:
        for f in (cert_pem, key_pem):
            with contextlib.suppress(OSError):
                os.remove(f)

    ret = dce_client.extrair_retorno(resp.body)
    autorizado = ret["cstat"] == "100"

    row = OrderDce(
        order_id=order.id,
        pack_id=getattr(order, "pack_id", None),
        shipment_id=getattr(order, "shipment_id", None),
        chave=chave,
        protocolo=ret["protocolo"],
        serie=serie,
        numero=numero,
        status="authorized" if autorizado else "rejected",
        cstat=ret["cstat"],
        xmotivo=ret["xmotivo"],
        natureza=_NAT_OP_DCE,
        environment=ambiente,
        signer_cnpj=mkt_cfg.cnpj,
        emit_cpf=_so_digitos(cmig.cpf),
        xml=xml_assinado if autorizado else None,
        emitted_at=datetime.now(BR_TZ) if autorizado else None,
    )
    db.add(row)
    await db.flush()

    return RetornoDce(
        autorizado=autorizado, chave=chave, protocolo=ret["protocolo"],
        cstat=ret["cstat"], xmotivo=ret["xmotivo"],
        xml_assinado=xml_assinado if autorizado else None,
    )
