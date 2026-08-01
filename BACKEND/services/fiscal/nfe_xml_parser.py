"""Parse de XML de NFe (modelo 55, layouts 4.00 e 5.00) recebido de fornecedor.

Extrai dados estruturados do XML para criar um Invoice de entrada (direction='in').
Suporta tanto o XML "puro" (raiz <NFe>) quanto o XML do protocolo (<nfeProc>).
Usa xmltodict para parsing tolerante.

Layout 5.0: quando publicado pela SEFAZ, detect_nfe_version() identificará
automaticamente; o parser usará o mesmo dict normalizado de saída.
Diferenças esperadas (a implementar conforme publicação):
  - Namespace alterado: nfe5:NFe
  - Novos campos IBS/CBS/IS nos itens
  - Campo <cIBS> e <cCBS> no ICMS/PIS/COFINS
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import xmltodict


def _clean_doc(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


def _to_dec(v: Any, default: Decimal = Decimal("0")) -> Decimal:
    if v is None or v == "":
        return default
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return default


def _to_int(v: Any, default: int | None = None) -> int | None:
    if v is None or v == "":
        return default
    try:
        return int(str(v))
    except (ValueError, TypeError):
        return default


def _ensure_list(v: Any) -> list:
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return [v]


def detect_nfe_version(xml_content: str | bytes) -> str:
    """Detecta versão do layout NFe a partir do atributo versao na tag infNFe.

    Retorna '4.00' (padrão vigente), '5.00' (futuro) ou o valor bruto encontrado.
    """
    if isinstance(xml_content, bytes):
        xml_content = xml_content.decode("utf-8", errors="replace")
    m = re.search(r'versao=["\']([^"\']+)["\']', xml_content)
    if m:
        return m.group(1)
    return "4.00"


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    # Layout 4.00: formato ISO com timezone, ex: "2024-01-15T10:30:00-03:00"
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        try:
            # Fallback para formato sem timezone
            return datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")
        except (ValueError, TypeError):
            return None


def parse_nfe_xml(xml_content: str | bytes) -> dict:
    """Parseia um XML de NFe e retorna dict normalizado.

    Estrutura retornada:
    {
      "access_key": "...",
      "model": "55",
      "serie": int,
      "nfe_number": int,
      "issue_date": datetime,
      "exit_date": datetime | None,
      "natureza_operacao": str,
      "emit": {  # emitente (= fornecedor para entradas)
        "cnpj": str, "name": str, "trade_name": str, "ie": str, "im": str,
        "street": str, "address_number": str, "complement": str,
        "neighborhood": str, "city": str, "state": str, "zip_code": str,
        "ibge_code": str, "phone": str,
      },
      "dest": {  # destinatário (= a CMIG)
        "cnpj": str, "name": str, ...
      },
      "items": [
        {
          "item_number": int, "description": str, "ncm": str, "cest": str,
          "cfop": str, "ean": str, "unit": str,
          "quantity": Decimal, "unit_value": Decimal, "total_value": Decimal,
          "discount": Decimal, "freight_value": Decimal, "insurance_value": Decimal,
          "other_value": Decimal, "origin": int,
          "icms_cst": str, "icms_csosn": str,
          "icms_base": Decimal, "icms_aliquota": Decimal, "icms_value": Decimal,
          "icms_st_base": Decimal, "icms_st_aliquota": Decimal, "icms_st_value": Decimal,
          "ipi_cst": str, "ipi_aliquota": Decimal, "ipi_value": Decimal,
          "pis_cst": str, "pis_aliquota": Decimal, "pis_value": Decimal,
          "cofins_cst": str, "cofins_aliquota": Decimal, "cofins_value": Decimal,
          "additional_info": str,
        },
      ],
      "totals": {
        "total_products": Decimal, "total_freight": Decimal, "total_insurance": Decimal,
        "total_discount": Decimal, "total_other": Decimal,
        "total_icms": Decimal, "total_icms_st": Decimal, "total_pis": Decimal,
        "total_cofins": Decimal, "total_ipi": Decimal, "total_invoice": Decimal,
      },
      "transport": {
        "freight_modality": int | None,
        "carrier_cnpj": str | None, "carrier_name": str | None,
      },
      "additional_info": str,
    }

    Raises:
      ValueError: se o XML não puder ser interpretado como NFe.
    """
    try:
        parsed = xmltodict.parse(xml_content, process_namespaces=False)
    except Exception as e:
        raise ValueError(f"XML inválido: {e}")

    # Aceita tanto <nfeProc><NFe>... quanto <NFe>...
    nfe = None
    if "nfeProc" in parsed:
        nfe = parsed["nfeProc"].get("NFe")
    elif "NFe" in parsed:
        nfe = parsed["NFe"]

    if not nfe:
        raise ValueError("XML não é uma NFe válida (esperado elemento <NFe> ou <nfeProc>)")

    inf = nfe.get("infNFe")
    if not inf:
        raise ValueError("Elemento <infNFe> não encontrado")

    # Chave de acesso (atributo Id="NFe<44 dígitos>")
    inf_id = inf.get("@Id", "")
    access_key = inf_id.replace("NFe", "") if inf_id else ""

    ide = inf.get("ide", {}) or {}
    emit = inf.get("emit", {}) or {}
    dest = inf.get("dest", {}) or {}
    total = (inf.get("total", {}) or {}).get("ICMSTot", {}) or {}
    transp = inf.get("transp", {}) or {}
    inf_adic = inf.get("infAdic", {}) or {}
    det_list = _ensure_list(inf.get("det"))

    return {
        "access_key": access_key,
        "model": str(ide.get("mod") or "55"),
        "tp_nf": _to_int(ide.get("tpNF")),  # 0=entrada, 1=saída (canônico p/ direção — MOC B11)
        "serie": _to_int(ide.get("serie"), 1),
        "nfe_number": _to_int(ide.get("nNF")),
        "issue_date": _parse_dt(ide.get("dhEmi") or ide.get("dEmi")),
        "exit_date": _parse_dt(ide.get("dhSaiEnt") or ide.get("dSaiEnt")),
        "natureza_operacao": ide.get("natOp") or "",
        "referenced_keys": _parse_nfref(ide),  # chaves de NF-e referenciadas (ex.: venda na devolução)
        "emit": _parse_party(emit),
        "dest": _parse_party(dest),
        "items": [_parse_item(d) for d in det_list],
        "totals": _parse_totals(total),
        "transport": _parse_transport(transp),
        "additional_info": (inf_adic.get("infCpl") or "")[:2000],
    }


def _parse_nfref(ide: dict) -> list[str]:
    """Extrai as chaves de NF-e referenciadas (ide/NFref/refNFe) — 44 dígitos cada.
    Na devolução, é a chave da NF-e de venda original."""
    keys: list[str] = []
    for ref in _ensure_list(ide.get("NFref")):
        if not isinstance(ref, dict):
            continue
        k = (ref.get("refNFe") or "").strip()
        if len(k) == 44:
            keys.append(k)
    return keys


def _parse_party(party: dict) -> dict:
    """Extrai dados de emit ou dest (PJ ou PF)."""
    if not party:
        return {}
    cnpj = _clean_doc(party.get("CNPJ"))
    cpf = _clean_doc(party.get("CPF"))
    document = cnpj or cpf
    person_type = "PJ" if cnpj else "PF"

    end = party.get("enderEmit") or party.get("enderDest") or {}

    return {
        "person_type": person_type,
        "document": document,
        "name": party.get("xNome") or "",
        "trade_name": party.get("xFant") or "",
        "ie": party.get("IE") or "",
        "im": party.get("IM") or "",
        "phone": end.get("fone") or "",
        "street": end.get("xLgr") or "",
        "address_number": end.get("nro") or "",
        "complement": end.get("xCpl") or "",
        "neighborhood": end.get("xBairro") or "",
        "city": end.get("xMun") or "",
        "state": end.get("UF") or "",
        "zip_code": _format_cep(end.get("CEP") or ""),
        "ibge_code": end.get("cMun") or "",
        "country_code": end.get("cPais") or "1058",
    }


def _format_cep(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 8:
        return f"{digits[:5]}-{digits[5:]}"
    return raw or ""


def _parse_item(det: dict) -> dict:
    """Extrai dados de um <det> (item)."""
    item_number = _to_int(det.get("@nItem"), 1)
    prod = det.get("prod", {}) or {}
    imposto = det.get("imposto", {}) or {}

    icms_data = _extract_icms(imposto.get("ICMS", {}) or {})
    ipi_data = _extract_ipi(imposto.get("IPI", {}) or {})
    pis_data = _extract_pis(imposto.get("PIS", {}) or {})
    cofins_data = _extract_cofins(imposto.get("COFINS", {}) or {})

    inf_adic = det.get("infAdProd") or ""

    return {
        "item_number": item_number,
        "cfop": prod.get("CFOP") or "",
        "ncm": prod.get("NCM") or "",
        "cest": prod.get("CEST") or "",
        "description": prod.get("xProd") or "",
        "sku": (prod.get("cProd") or "").strip(),  # código do produto (SKU do emitente)
        "ean": (prod.get("cEAN") or "").replace("SEM GTIN", "") or "",
        "unit": prod.get("uCom") or "UN",
        "quantity": _to_dec(prod.get("qCom"), Decimal("1")),
        "unit_value": _to_dec(prod.get("vUnCom")),
        "total_value": _to_dec(prod.get("vProd")),
        "discount": _to_dec(prod.get("vDesc")),
        "freight_value": _to_dec(prod.get("vFrete")),
        "insurance_value": _to_dec(prod.get("vSeg")),
        "other_value": _to_dec(prod.get("vOutro")),
        "origin": icms_data["origin"],
        "icms_cst": icms_data["cst"],
        "icms_csosn": icms_data["csosn"],
        "icms_base": icms_data["base"],
        "icms_aliquota": icms_data["aliquota"],
        "icms_value": icms_data["value"],
        "icms_st_base": icms_data["st_base"],
        "icms_st_aliquota": icms_data["st_aliquota"],
        "icms_st_value": icms_data["st_value"],
        "ipi_cst": ipi_data["cst"],
        "ipi_aliquota": ipi_data["aliquota"],
        "ipi_value": ipi_data["value"],
        "pis_cst": pis_data["cst"],
        "pis_aliquota": pis_data["aliquota"],
        "pis_value": pis_data["value"],
        "cofins_cst": cofins_data["cst"],
        "cofins_aliquota": cofins_data["aliquota"],
        "cofins_value": cofins_data["value"],
        "additional_info": (inf_adic or "")[:2000],
    }


def _extract_icms(icms: dict) -> dict:
    """ICMS vem dentro de uma sub-tag variável (ICMS00, ICMS10, ICMSSN101, etc)."""
    out = {
        "origin": 0,
        "cst": None,
        "csosn": None,
        "base": Decimal("0"),
        "aliquota": Decimal("0"),
        "value": Decimal("0"),
        "st_base": Decimal("0"),
        "st_aliquota": Decimal("0"),
        "st_value": Decimal("0"),
    }
    if not icms:
        return out
    # Pega o primeiro filho (qualquer ICMS00/ICMS10/.../ICMSSN101/...)
    for _key, val in icms.items():
        if not isinstance(val, dict):
            continue
        out["origin"] = _to_int(val.get("orig"), 0) or 0
        out["cst"] = val.get("CST")
        out["csosn"] = val.get("CSOSN")
        out["base"] = _to_dec(val.get("vBC"))
        out["aliquota"] = _to_dec(val.get("pICMS"))
        out["value"] = _to_dec(val.get("vICMS"))
        out["st_base"] = _to_dec(val.get("vBCST"))
        out["st_aliquota"] = _to_dec(val.get("pICMSST"))
        out["st_value"] = _to_dec(val.get("vICMSST"))
        break
    return out


def _extract_ipi(ipi: dict) -> dict:
    out = {"cst": None, "aliquota": Decimal("0"), "value": Decimal("0")}
    if not ipi:
        return out
    trib = ipi.get("IPITrib") or ipi.get("IPINT") or {}
    if isinstance(trib, dict):
        out["cst"] = trib.get("CST")
        out["aliquota"] = _to_dec(trib.get("pIPI"))
        out["value"] = _to_dec(trib.get("vIPI"))
    return out


def _extract_pis(pis: dict) -> dict:
    out = {"cst": None, "aliquota": Decimal("0"), "value": Decimal("0")}
    if not pis:
        return out
    for key in ("PISAliq", "PISQtde", "PISNT", "PISOutr", "PISSN"):
        v = pis.get(key)
        if isinstance(v, dict):
            out["cst"] = v.get("CST")
            out["aliquota"] = _to_dec(v.get("pPIS"))
            out["value"] = _to_dec(v.get("vPIS"))
            return out
    return out


def _extract_cofins(cofins: dict) -> dict:
    out = {"cst": None, "aliquota": Decimal("0"), "value": Decimal("0")}
    if not cofins:
        return out
    for key in ("COFINSAliq", "COFINSQtde", "COFINSNT", "COFINSOutr", "COFINSSN"):
        v = cofins.get(key)
        if isinstance(v, dict):
            out["cst"] = v.get("CST")
            out["aliquota"] = _to_dec(v.get("pCOFINS"))
            out["value"] = _to_dec(v.get("vCOFINS"))
            return out
    return out


def _parse_totals(total: dict) -> dict:
    return {
        "total_products": _to_dec(total.get("vProd")),
        "total_freight": _to_dec(total.get("vFrete")),
        "total_insurance": _to_dec(total.get("vSeg")),
        "total_discount": _to_dec(total.get("vDesc")),
        "total_other": _to_dec(total.get("vOutro")),
        "total_icms": _to_dec(total.get("vICMS")),
        "total_icms_st": _to_dec(total.get("vST")),
        "total_pis": _to_dec(total.get("vPIS")),
        "total_cofins": _to_dec(total.get("vCOFINS")),
        "total_ipi": _to_dec(total.get("vIPI")),
        "total_invoice": _to_dec(total.get("vNF")),
    }


def _parse_transport(transp: dict) -> dict:
    transporta = transp.get("transporta") or {}
    return {
        "freight_modality": _to_int(transp.get("modFrete")),
        "carrier_cnpj": _clean_doc(transporta.get("CNPJ")) or _clean_doc(transporta.get("CPF")),
        "carrier_name": transporta.get("xNome"),
    }
