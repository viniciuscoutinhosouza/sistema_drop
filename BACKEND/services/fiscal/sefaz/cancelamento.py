"""Eventos da NFe via `RecepcaoEvento4`: Cancelamento (110111) e Carta de Correção (110110).

Cancelamento: até 24h após autorização (prazo nacional; extemporâneo varia por UF,
com multa). Justificativa 15–255 chars. cStat 135 = registrado e vinculado.

Carta de Correção (CC-e): pode a qualquer tempo, vale a última (nSeqEvento). NÃO
pode corrigir valor/base/alíquota/imposto, quantidade, dados que mudem
remetente/destinatário, datas — vedação do Ajuste SINIEF 07/2005 cl. 14-A.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from lxml import etree

from services.fiscal.sefaz.exceptions import FiscalError
from services.fiscal.sefaz.sefaz_client import (
    NFE_NAMESPACE,
    SEFAZ_NFE_ENDPOINTS_POR_UF,
    SefazResponse,
    extract_cert_pem,
    post_sefaz,
    soap_envelope,
)
from services.fiscal.sefaz.signer import assinar_xml

CSTAT_CANCELAMENTO_OK: frozenset[str] = frozenset({"135", "136", "155"})
CSTAT_CCE_OK: frozenset[str] = frozenset({"135", "136"})

# Texto legal obrigatório da CC-e (xCondUso) — exigido pela SEFAZ.
_X_COND_USO = (
    "A Carta de Correcao e disciplinada pelo paragrafo 1o-A do art. 7o do Convenio S/N, "
    "de 15 de dezembro de 1970 e pode ser utilizada para regularizacao de erro ocorrido "
    "na emissao de documento fiscal, desde que o erro nao esteja relacionado com: I - as "
    "variaveis que determinam o valor do imposto tais como: base de calculo, aliquota, "
    "diferenca de preco, quantidade, valor da operacao ou da prestacao; II - a correcao de "
    "dados cadastrais que implique mudanca do remetente ou do destinatario; III - a data de "
    "emissao ou de saida."
)

_CUF: dict[str, str] = {
    "AC": "12", "AL": "27", "AM": "13", "AP": "16", "BA": "29", "CE": "23",
    "DF": "53", "ES": "32", "GO": "52", "MA": "21", "MG": "31", "MS": "50",
    "MT": "51", "PA": "15", "PB": "25", "PE": "26", "PI": "22", "PR": "41",
    "RJ": "33", "RN": "24", "RO": "11", "RR": "14", "RS": "43", "SC": "42",
    "SE": "28", "SP": "35", "TO": "17",
}
_SOAP_ACTION_EVENTO = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeRecepcaoEvento4/nfeRecepcaoEvento"


@dataclass(frozen=True, slots=True)
class RetornoEvento:
    chave: str
    tp_evento: str
    cstat: str | None
    motivo: str | None
    protocolo: str | None
    xml_evento_assinado: str
    envelope_soap: str
    response: SefazResponse

    @property
    def ok(self) -> bool:
        if self.tp_evento == "110111":
            return self.cstat in CSTAT_CANCELAMENTO_OK
        return self.cstat in CSTAT_CCE_OK


def _cuf_por_uf(uf: str) -> str:
    if uf not in _CUF:
        raise FiscalError(f"UF {uf!r} desconhecida")
    return _CUF[uf]


def _fmt_iso(dt: datetime) -> str:
    s = dt.strftime("%Y-%m-%dT%H:%M:%S%z")
    if len(s) >= 5 and s[-5] in "+-":
        s = s[:-2] + ":" + s[-2:]
    return s


def _montar_inf_evento(
    *, tp_evento: str, chave: str, cnpj: str, uf: str, ambiente: str, dh: datetime, n_seq: int,
    c_orgao: str | None = None,
) -> tuple[etree._Element, str]:
    inf_evento_id = f"ID{tp_evento}{chave}{n_seq:02d}"
    nsmap: dict[str | None, str] = {None: NFE_NAMESPACE}
    evento = etree.Element(f"{{{NFE_NAMESPACE}}}evento", nsmap=nsmap)  # type: ignore[arg-type]
    evento.set("versao", "1.00")
    inf = etree.SubElement(evento, f"{{{NFE_NAMESPACE}}}infEvento")
    inf.set("Id", inf_evento_id)
    # Manifestação do destinatário vai ao Ambiente Nacional (cOrgao=91); demais à UF.
    etree.SubElement(inf, f"{{{NFE_NAMESPACE}}}cOrgao").text = c_orgao or _cuf_por_uf(uf)
    etree.SubElement(inf, f"{{{NFE_NAMESPACE}}}tpAmb").text = "2" if ambiente == "homologacao" else "1"
    etree.SubElement(inf, f"{{{NFE_NAMESPACE}}}CNPJ").text = cnpj
    etree.SubElement(inf, f"{{{NFE_NAMESPACE}}}chNFe").text = chave
    etree.SubElement(inf, f"{{{NFE_NAMESPACE}}}dhEvento").text = _fmt_iso(dh)
    etree.SubElement(inf, f"{{{NFE_NAMESPACE}}}tpEvento").text = tp_evento
    etree.SubElement(inf, f"{{{NFE_NAMESPACE}}}nSeqEvento").text = str(n_seq)
    etree.SubElement(inf, f"{{{NFE_NAMESPACE}}}verEvento").text = "1.00"
    det = etree.SubElement(inf, f"{{{NFE_NAMESPACE}}}detEvento")
    det.set("versao", "1.00")
    return evento, inf_evento_id


def _to_xml(evento: etree._Element) -> str:
    xml = etree.tostring(evento, encoding="unicode")
    return f'<?xml version="1.0" encoding="UTF-8"?>{xml}'


def _det(evento: etree._Element) -> etree._Element:
    inf = evento.find(f"{{{NFE_NAMESPACE}}}infEvento")
    return inf.find(f"{{{NFE_NAMESPACE}}}detEvento")  # type: ignore[union-attr,return-value]


def _montar_env_evento(xml_evento_assinado: str, id_lote: int | str = 1) -> str:
    inner = xml_evento_assinado
    if inner.startswith("<?"):
        inner = inner.split("?>", 1)[1].lstrip()
    return f'<envEvento xmlns="{NFE_NAMESPACE}" versao="1.00"><idLote>{id_lote}</idLote>{inner}</envEvento>'


_RE_RETEVENTO = re.compile(r"<retEvento[^>]*>.*?</retEvento>", re.DOTALL)


def _parse_resposta(body: str) -> tuple[str | None, str | None, str | None]:
    m = _RE_RETEVENTO.search(body)
    bloco = m.group(0) if m else body
    cstat_m = re.search(r"<cStat>(\d+)</cStat>", bloco)
    motivo_m = re.search(r"<xMotivo>([^<]+)</xMotivo>", bloco)
    nprot_m = re.search(r"<nProt>(\d+)</nProt>", bloco)
    return (
        cstat_m.group(1) if cstat_m else None,
        motivo_m.group(1) if motivo_m else None,
        nprot_m.group(1) if nprot_m else None,
    )


def _enviar_evento(
    *, evento: etree._Element, inf_evento_id: str, tp_evento: str, chave: str, uf: str,
    ambiente: Literal["homologacao", "producao"], pfx_path: str | Path, pfx_password: str,
    timeout: int, verify_ssl: bool, runtime_dir: str | Path | None,
    endpoint_url: str | None = None,
) -> RetornoEvento:
    if endpoint_url is None:
        if uf not in SEFAZ_NFE_ENDPOINTS_POR_UF:
            raise FiscalError(f"UF {uf!r} sem endpoint (suportado: {sorted(SEFAZ_NFE_ENDPOINTS_POR_UF.keys())})")
        endpoint_url = SEFAZ_NFE_ENDPOINTS_POR_UF[uf][ambiente]["recepcao_evento"]
    xml_assinado = assinar_xml(_to_xml(evento), pfx_path=pfx_path, pfx_password=pfx_password, ref_id=inf_evento_id)
    envelope = soap_envelope("NFeRecepcaoEvento4", _montar_env_evento(xml_assinado))
    cert_pem, key_pem = extract_cert_pem(pfx_path, pfx_password, runtime_dir=runtime_dir)
    try:
        response = post_sefaz(
            endpoint_url, envelope, cert_pem, key_pem,
            timeout=timeout, verify_ssl=verify_ssl, soap_action=_SOAP_ACTION_EVENTO,
        )
    finally:
        Path(cert_pem).unlink(missing_ok=True)
        Path(key_pem).unlink(missing_ok=True)
    cstat, motivo, nprot = _parse_resposta(response.body)
    return RetornoEvento(
        chave=chave, tp_evento=tp_evento, cstat=cstat, motivo=motivo, protocolo=nprot,
        xml_evento_assinado=xml_assinado, envelope_soap=envelope, response=response,
    )


def cancelar_nfe(
    *,
    chave: str,
    cnpj_emitente: str,
    uf_emitente: str,
    ambiente: Literal["homologacao", "producao"],
    protocolo_autorizacao: str,
    justificativa: str,
    pfx_path: str | Path,
    pfx_password: str,
    dh_evento: datetime | None = None,
    timeout: int = 30,
    verify_ssl: bool = True,
    runtime_dir: str | Path | None = None,
) -> RetornoEvento:
    """Cancela NFe autorizada via evento 110111 (justificativa 15–255 chars)."""
    if len(chave) != 44 or not chave.isdigit():
        raise FiscalError(f"chave inválida: {chave!r}")
    if not (15 <= len(justificativa) <= 255):
        raise FiscalError(f"justificativa deve ter 15-255 chars (recebido: {len(justificativa)})")
    dh = dh_evento or datetime.now(UTC)
    evento, inf_id = _montar_inf_evento(
        tp_evento="110111", chave=chave, cnpj=cnpj_emitente, uf=uf_emitente,
        ambiente=ambiente, dh=dh, n_seq=1,
    )
    det = _det(evento)
    etree.SubElement(det, f"{{{NFE_NAMESPACE}}}descEvento").text = "Cancelamento"
    etree.SubElement(det, f"{{{NFE_NAMESPACE}}}nProt").text = protocolo_autorizacao
    etree.SubElement(det, f"{{{NFE_NAMESPACE}}}xJust").text = justificativa
    return _enviar_evento(
        evento=evento, inf_evento_id=inf_id, tp_evento="110111", chave=chave, uf=uf_emitente,
        ambiente=ambiente, pfx_path=pfx_path, pfx_password=pfx_password,
        timeout=timeout, verify_ssl=verify_ssl, runtime_dir=runtime_dir,
    )


def carta_correcao(
    *,
    chave: str,
    cnpj_emitente: str,
    uf_emitente: str,
    ambiente: Literal["homologacao", "producao"],
    correcao: str,
    n_seq_evento: int,
    pfx_path: str | Path,
    pfx_password: str,
    dh_evento: datetime | None = None,
    timeout: int = 30,
    verify_ssl: bool = True,
    runtime_dir: str | Path | None = None,
) -> RetornoEvento:
    """Carta de Correção (evento 110110). xCorrecao 15–1000 chars; nSeqEvento incremental."""
    if len(chave) != 44 or not chave.isdigit():
        raise FiscalError(f"chave inválida: {chave!r}")
    if not (15 <= len(correcao) <= 1000):
        raise FiscalError(f"correção deve ter 15-1000 chars (recebido: {len(correcao)})")
    if n_seq_evento < 1 or n_seq_evento > 20:
        raise FiscalError(f"nSeqEvento deve ser 1..20 (recebido: {n_seq_evento})")
    dh = dh_evento or datetime.now(UTC)
    evento, inf_id = _montar_inf_evento(
        tp_evento="110110", chave=chave, cnpj=cnpj_emitente, uf=uf_emitente,
        ambiente=ambiente, dh=dh, n_seq=n_seq_evento,
    )
    det = _det(evento)
    etree.SubElement(det, f"{{{NFE_NAMESPACE}}}descEvento").text = "Carta de Correcao"
    etree.SubElement(det, f"{{{NFE_NAMESPACE}}}xCorrecao").text = correcao
    etree.SubElement(det, f"{{{NFE_NAMESPACE}}}xCondUso").text = _X_COND_USO
    return _enviar_evento(
        evento=evento, inf_evento_id=inf_id, tp_evento="110110", chave=chave, uf=uf_emitente,
        ambiente=ambiente, pfx_path=pfx_path, pfx_password=pfx_password,
        timeout=timeout, verify_ssl=verify_ssl, runtime_dir=runtime_dir,
    )


# Manifestação do destinatário (NT 2014.002) — vai ao Ambiente Nacional (cOrgao=91).
_MANIFESTACAO_TP = {
    "ciencia": ("210210", "Ciencia da Operacao"),
    "confirmacao": ("210200", "Confirmacao da Operacao"),
    "desconhecimento": ("210220", "Desconhecimento da Operacao"),
    "nao_realizada": ("210240", "Operacao nao Realizada"),
}
CSTAT_MANIFESTACAO_OK: frozenset[str] = frozenset({"135", "136"})


def manifestar(
    *,
    chave: str,
    cnpj_destinatario: str,
    tipo: Literal["ciencia", "confirmacao", "desconhecimento", "nao_realizada"],
    ambiente: Literal["homologacao", "producao"],
    endpoint_url: str,
    pfx_path: str | Path,
    pfx_password: str,
    justificativa: str | None = None,
    dh_evento: datetime | None = None,
    timeout: int = 30,
    verify_ssl: bool = True,
    runtime_dir: str | Path | None = None,
) -> RetornoEvento:
    """Manifestação do destinatário sobre NF-e recebida (vai ao Ambiente Nacional).

    Desconhecimento/Operação não realizada exigem justificativa (15–255 chars).
    """
    if tipo not in _MANIFESTACAO_TP:
        raise FiscalError(f"tipo de manifestação inválido: {tipo!r}")
    if len(chave) != 44 or not chave.isdigit():
        raise FiscalError(f"chave inválida: {chave!r}")
    tp_evento, desc = _MANIFESTACAO_TP[tipo]
    if tipo in ("desconhecimento", "nao_realizada"):
        if not justificativa or not (15 <= len(justificativa) <= 255):
            raise FiscalError("justificativa (15–255 chars) obrigatória para este tipo de manifestação")
    dh = dh_evento or datetime.now(UTC)
    evento, inf_id = _montar_inf_evento(
        tp_evento=tp_evento, chave=chave, cnpj=cnpj_destinatario, uf="RJ",
        ambiente=ambiente, dh=dh, n_seq=1, c_orgao="91",
    )
    det = _det(evento)
    etree.SubElement(det, f"{{{NFE_NAMESPACE}}}descEvento").text = desc
    if justificativa:
        etree.SubElement(det, f"{{{NFE_NAMESPACE}}}xJust").text = justificativa
    return _enviar_evento(
        evento=evento, inf_evento_id=inf_id, tp_evento=tp_evento, chave=chave, uf="RJ",
        ambiente=ambiente, pfx_path=pfx_path, pfx_password=pfx_password,
        timeout=timeout, verify_ssl=verify_ssl, runtime_dir=runtime_dir, endpoint_url=endpoint_url,
    )
