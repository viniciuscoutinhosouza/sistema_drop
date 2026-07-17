"""Adaptador entre o banco (Invoice/CMIG/Person/CMIGProduct) e a camada fiscal pura.

Substitui o papel do `focus_service` na emissão MANUAL via SEFAZ: monta o
`NotaEmissao`, reserva o número da série manual de forma atômica (NFE_NEXTVAL_MANUAL),
decifra a senha do certificado, chama o `emitter`/`cancelamento`/`consulta` (que são
bloqueantes → `asyncio.to_thread`) e persiste o resultado no Invoice + log SEFAZ.

Correções fiscais (Simples Nacional) já vêm do `xml_builder`: PIS/COFINS CST 99,
sem IPI, sem ICMSUFDest, CSOSN 102/500.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models.cmig import CMIG
from models.fiscal import CMIGFiscalConfig, Invoice, InvoiceSefazLog
from models.person import Person
from services.datetime_br import to_br
from services.fiscal import cert_crypto
from services.fiscal.sefaz import cancelamento, consulta
from services.fiscal.sefaz.sefaz_client import SEFAZ_EVENTO_AN
from services.fiscal.sefaz.chave import gerar_cnf, montar_chave
from services.fiscal.sefaz.emitter import RetornoEmissao, emitir_nfe
from services.fiscal.sefaz.exceptions import FiscalError
from services.fiscal.sefaz.models import (
    Cliente,
    Endereco,
    Estabelecimento,
    ItemEmissao,
    NotaEmissao,
    Pagamento,
    Produto,
)
from services.fiscal.sefaz.xml_builder import codigo_uf

logger = logging.getLogger(__name__)

# Mapa do nosso environment ('homolog'/'production') para o da camada fiscal.
_AMB = {"homolog": "homologacao", "production": "producao"}

_FINALIDADE = {
    "venda": 1, "remessa": 1, "transferencia": 1, "outros": 1, "retorno": 1,
    "complementar": 2, "ajuste": 3, "devolucao": 4,
}


class SefazServiceError(Exception):
    """Erro de configuração/negócio antes ou depois da SEFAZ (vira 4xx/5xx no router)."""


def _digits(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


def _dec(v) -> Decimal:
    return Decimal(str(v)) if v is not None else Decimal("0")


def _runtime_dir() -> str:
    return str(Path(get_settings().NFE_CERTS_DIR) / "runtime")


def _verify_ssl(environment: str) -> bool:
    """TLS sempre verificado em produção (anti-MITM no mTLS); configurável em homologação."""
    return True if environment == "production" else bool(get_settings().NFE_VERIFY_SSL)


def resolve_cert(cfg: CMIGFiscalConfig) -> tuple[str, str]:
    """Retorna (pfx_path, senha_em_claro). A senha é decifrada da master key."""
    if not cfg.cert_path or not cfg.cert_pass_encrypted:
        raise SefazServiceError(
            "Certificado A1 não configurado para esta CMIG (envie o .pfx em Configuração Fiscal)."
        )
    if not Path(cfg.cert_path).exists():
        raise SefazServiceError(f"Arquivo do certificado não encontrado no servidor: {cfg.cert_path}")
    try:
        senha = cert_crypto.decrypt(cfg.cert_pass_encrypted)
    except cert_crypto.CertCryptoError as e:
        raise SefazServiceError(str(e)) from e
    return cfg.cert_path, senha


# ── Montagem do NotaEmissao ───────────────────────────────────────────────────


def _estabelecimento(cmig: CMIG, cfg: CMIGFiscalConfig) -> Estabelecimento:
    if not cmig.ibge_code:
        raise SefazServiceError("CMIG sem código IBGE do município — atualize o cadastro da empresa.")
    if not cfg.ie:
        raise SefazServiceError("CMIG sem Inscrição Estadual na Configuração Fiscal.")
    end = Endereco(
        logradouro=cmig.street or "", numero=cmig.address_number or "S/N",
        complemento=cmig.complement or None, bairro=cmig.neighborhood or "",
        municipio_ibge=cmig.ibge_code, municipio_nome=cmig.city or "",
        uf=(cmig.state or "").upper(), cep=_digits(cmig.zip_code),
    )
    return Estabelecimento(
        cnpj=_digits(cmig.cnpj), ie=_digits(cfg.ie) or cfg.ie, razao_social=cmig.company_name or "",
        nome_fantasia=cmig.trade_name or None, endereco=end, crt=cfg.crt or 1,
        aliquota_fecp=_dec(cfg.aliquota_fecp),
    )


def _cliente(person: Person) -> Cliente:
    if not person.ibge_code:
        raise SefazServiceError(
            f"Destinatário '{person.name}' sem código IBGE do município — atualize o cadastro."
        )
    doc = _digits(person.document)
    tipo = "PJ" if len(doc) == 14 else "PF"
    if tipo == "PJ":
        if getattr(person, "ie_isento", False):
            indicador, ie = 2, "ISENTO"
        elif person.ie:
            indicador, ie = 1, _digits(person.ie) or person.ie
        else:
            indicador, ie = 9, None
    else:
        indicador, ie = 9, None
    end = Endereco(
        logradouro=person.street or "", numero=person.address_number or "S/N",
        complemento=person.complement or None, bairro=person.neighborhood or "",
        municipio_ibge=person.ibge_code, municipio_nome=person.city or "",
        uf=(person.state or "").upper(), cep=_digits(person.zip_code),
    )
    return Cliente(
        tipo=tipo, cpf_cnpj=doc, nome_razao_social=person.name or "",
        indicador_ie=indicador, ie=ie, email=person.email or None,
        telefone=_digits(person.phone) or None, endereco=end,
    )


def _item(it) -> ItemEmissao:
    csosn = (it.icms_csosn or "102").strip()
    ncm = _digits(it.ncm)
    if len(ncm) != 8:
        raise SefazServiceError(f"Item '{it.description}': NCM inválido ({it.ncm!r}) — corrija o produto.")
    prod = Produto(
        codigo=(it.sku or str(it.cmig_product_id or it.id)), descricao=it.description or "",
        ncm=ncm, csosn=csosn, origem=str(it.origin if it.origin is not None else 0),
        unidade=it.unit or "UN", cest=(_digits(it.cest) or None) if it.cest else None,
        ean=it.ean or None,
        vbc_st_ret=_dec(it.icms_st_base) if csosn == "500" else None,
        vicms_st_ret=_dec(it.icms_st_value) if csosn == "500" else None,
        info_adicional=(it.additional_info or None),
    )
    return ItemEmissao(
        numero_item=it.item_number, produto=prod, quantidade=_dec(it.quantity),
        preco_unitario=_dec(it.unit_value), cfop=(it.cfop or "5102"),
        valor_frete=_dec(it.freight_value), valor_desconto=_dec(it.discount),
        valor_seguro=_dec(it.insurance_value), valor_outras=_dec(it.other_value),
    )


def build_nota_emissao(
    inv: Invoice, cmig: CMIG, cfg: CMIGFiscalConfig, person: Person, items: list,
    *, serie: int, numero: int, ambiente: str,
) -> NotaEmissao:
    """Monta o NotaEmissao (chave/cNF congelados aqui — snapshot N-2 / regra N-6)."""
    if not items:
        raise SefazServiceError("NF-e sem itens.")
    emit = _estabelecimento(cmig, cfg)
    dest = _cliente(person)
    itens = tuple(_item(it) for it in sorted(items, key=lambda x: x.item_number))

    # ADR-0013: trata naive como UTC e converte para a borda (America/Sao_Paulo).
    dh = to_br(inv.issue_date) or to_br(datetime.now(UTC))
    aamm = f"{dh.year % 100:02d}{dh.month:02d}"
    c_nf = gerar_cnf()
    chave = montar_chave(
        c_uf=codigo_uf(emit.endereco.uf), aamm=aamm, cnpj=emit.cnpj,
        modelo=55, serie=serie, n_nf=numero, tp_emis=1, c_nf=c_nf,
    )

    finalidade = _FINALIDADE.get(inv.purpose or "venda", 1)
    ind_final = 1 if dest.tipo == "PF" else 0
    pagamentos: tuple[Pagamento, ...] = ()
    if inv.payment_method:
        pagamentos = (Pagamento(forma_pag=inv.payment_method, valor=_dec(inv.total_invoice), ind_pag=0),)

    return NotaEmissao(
        modelo=55, serie=serie, numero=numero, ambiente=ambiente, chave=chave, c_nf=c_nf,
        dh_emi=dh, natureza_operacao=inv.natureza_operacao or "Venda de mercadoria",
        finalidade=finalidade, ind_presenca=9, ind_intermed=0, ind_final=ind_final,
        emitente=emit, destinatario=dest, itens=itens, pagamentos=pagamentos,
        transporte_modalidade=int(inv.freight_modality) if inv.freight_modality is not None else 9,
        info_complementar=(inv.additional_info or None), info_fisco=(inv.fiscal_info or None),
    )


# ── Numeração atômica ─────────────────────────────────────────────────────────


async def reservar_numero(db: AsyncSession, cmig_id: int, environment: str) -> int:
    """Reserva o próximo número da série manual via PL/SQL (lock de linha curto)."""
    res = await db.execute(
        text("SELECT NFE_NEXTVAL_MANUAL(:cmig, :amb) AS n FROM dual"),
        {"cmig": cmig_id, "amb": environment},
    )
    numero = res.scalar()
    if numero is None:
        raise SefazServiceError("Falha ao reservar número da NF-e manual (config fiscal ausente?).")
    return int(numero)


# ── Persistência de log ───────────────────────────────────────────────────────


async def _log(db: AsyncSession, *, invoice_id, cmig_id, operation, cstat, xmotivo, req, resp) -> None:
    db.add(InvoiceSefazLog(
        invoice_id=invoice_id, cmig_id=cmig_id, operation=operation,
        cstat=cstat, xmotivo=(xmotivo or "")[:255], payload_request=req, payload_response=resp,
    ))


def _store_xml(cmig_id: int, chave: str, xml_proc: str) -> str:
    """Grava o XML autorizado (procNFe) em diretório restrito FORA de static/.

    Contém CPF/CNPJ/endereço do destinatário (LGPD) e é documento fiscal — nunca
    deve ser servido por HTTP sem auth; o download é só via GET /invoices/{id}/xml."""
    base = Path(get_settings().NFE_XML_DIR) / str(cmig_id)
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{chave}.xml"
    path.write_text(xml_proc, encoding="utf-8")
    return str(path)


class _PersonComIbgeFallback:
    """Proxy de leitura sobre `Person` que responde um `ibge_code` de fallback — SÓ na prévia."""

    def __init__(self, person: Person, ibge_fallback: str):
        self._person = person
        self._ibge = ibge_fallback

    def __getattr__(self, name):
        if name == "ibge_code":
            return self._ibge
        return getattr(self._person, name)


def montar_xml_previa(
    inv: Invoice, cmig: CMIG, cfg: CMIGFiscalConfig, person: Person, items: list,
) -> str:
    """XML NFe de PRÉVIA — para o DANFE "SEM VALOR FISCAL" de nota AINDA NÃO autorizada.

    Diferenças deliberadas em relação à emissão real (`emitir`):
    - **NÃO reserva número** (não queima a numeração fiscal): usa o número já gravado na nota,
      se houver, senão 0 — e o DANFE sai com a marca d'água, então não há como confundir.
    - **NÃO assina** e não fala com a SEFAZ.
    As validações de cadastro (IBGE/IE/NCM/destinatário) são as MESMAS da emissão —
    a prévia falha alto com a lista do que falta, em vez de imprimir um documento capenga.
    """
    from services.fiscal.sefaz.xml_builder import montar_xml_nfe

    if person is None:
        raise SefazServiceError("Selecione o destinatário antes de gerar o PDF da nota.")
    if not items:
        raise SefazServiceError("A nota não tem itens — adicione itens antes de gerar o PDF.")

    # Endereço mínimo para imprimir algo que preste: o XML valida UF/CEP, e o renderizador do
    # DANFE quebra com logradouro/bairro vazios. Sem eles → mensagem clara com a LISTA completa,
    # em vez do erro críptico do builder (uma falta por vez seria tortura).
    faltando = []
    if not (person.street or "").strip():
        faltando.append("Logradouro")
    if not (person.neighborhood or "").strip():
        faltando.append("Bairro")
    if not (person.city or "").strip():
        faltando.append("Cidade")
    if not (person.state or "").strip():
        faltando.append("UF")
    if len(_digits(person.zip_code)) != 8:
        faltando.append("CEP")
    if faltando:
        raise SefazServiceError(
            f"Destinatário '{person.name}' sem {', '.join(faltando)} no endereço — "
            "atualize em Fiscal > Pessoas."
        )

    # Na PRÉVIA o código IBGE do destinatário é opcional: o DANFE imprime o NOME do município
    # (xMun), não o código — o fallback é invisível no papel. A emissão real continua exigindo
    # (`_cliente` valida), porque lá o cMun vai para a SEFAZ. Proxy em vez de mutar `person`:
    # o objeto é ORM vivo, e um commit posterior do chamador persistiria o fallback.
    if not person.ibge_code:
        person = _PersonComIbgeFallback(person, cmig.ibge_code or "9999999")

    environment = cfg.environment or "homolog"
    ambiente = _AMB.get(environment, "homologacao")
    serie = cfg.manual_nfe_serie or 1
    # 999.999.999 = número-sentinela da prévia: a chave exige 1..999_999_999 (0 é rejeitado) e a
    # numeração real jamais chega lá — impossível colidir ou parecer nota emitida.
    nota = build_nota_emissao(
        inv, cmig, cfg, person, items,
        serie=serie, numero=inv.nfe_number or 999_999_999, ambiente=ambiente,
    )
    return montar_xml_nfe(nota)


# ── Emissão ───────────────────────────────────────────────────────────────────


async def emitir(
    db: AsyncSession, inv: Invoice, cmig: CMIG, cfg: CMIGFiscalConfig, person: Person, items: list,
) -> dict:
    """Reserva número, monta, transmite e persiste. Atualiza `inv` in-place.

    Retorna {autorizada, cstat, motivo, protocolo, chave}. SefazServiceError em
    config/negócio; a camada de rede levanta SefazError (router → 502, mantém retry)."""
    settings = get_settings()
    environment = cfg.environment or "homolog"
    ambiente = _AMB.get(environment, "homologacao")
    if ambiente == "producao" and not cfg.production_released:
        raise SefazServiceError("Produção não liberada para esta CMIG — emita em homologação primeiro.")

    serie = cfg.manual_nfe_serie
    if not serie:
        raise SefazServiceError("Série da NF-e manual (SEFAZ) não configurada na Configuração Fiscal.")

    pfx_path, senha = resolve_cert(cfg)  # falha cedo se cert ausente/master key errada

    # Pré-valida cadastros (IBGE, IE, NCM) ANTES de consumir um número fiscal —
    # evita "queimar" numeração por erro de cadastro corrigível.
    _estabelecimento(cmig, cfg)
    _cliente(person)
    for it in items:
        _item(it)

    # Reserva número sob lock curto e congela chave/cNF ANTES de falar com a SEFAZ.
    numero = await reservar_numero(db, cmig.id, environment)
    nota = build_nota_emissao(inv, cmig, cfg, person, items, serie=serie, numero=numero, ambiente=ambiente)

    inv.serie = serie
    inv.nfe_number = numero
    inv.access_key = nota.chave
    inv.environment = environment
    inv.emission_provider = "sefaz"
    inv.model = "55"
    inv.status = "processing"
    await db.commit()  # libera o lock da numeração; SEFAZ é chamada fora da transação

    retorno: RetornoEmissao = await asyncio.to_thread(
        emitir_nfe, nota,
        pfx_path=pfx_path, pfx_password=senha,
        timeout=int(settings.NFE_SEFAZ_TIMEOUT), verify_ssl=_verify_ssl(environment),
        runtime_dir=_runtime_dir(),
    )

    await _log(
        db, invoice_id=inv.id, cmig_id=cmig.id, operation="autorizacao",
        cstat=retorno.cstat_final, xmotivo=retorno.motivo_final,
        req=retorno.envelope_soap, resp=retorno.response.body,
    )
    inv.sefaz_cstat = retorno.cstat_final
    inv.sefaz_xmotivo = (retorno.motivo_final or "")[:255]
    inv.focus_message = retorno.motivo_final  # campo de exibição reutilizado

    if retorno.autorizada:
        inv.status = "authorized"
        inv.auth_protocol = retorno.nprot
        # Empacota procNFe (NFe assinada + protNFe) para DANFE/XML autorizado.
        from services.fiscal.sefaz.danfe import empacotar_nfeproc, extrair_protNFe

        prot = extrair_protNFe(retorno.response.body)
        try:
            xml_proc = empacotar_nfeproc(retorno.xml_signed, prot)
        except Exception:  # noqa: BLE001 — fallback: guarda a NFe assinada
            xml_proc = retorno.xml_signed
        try:
            inv.xml_local_path = _store_xml(cmig.id, nota.chave, xml_proc)
        except OSError:
            logger.warning("[nfe] falha ao gravar XML da nota %s", inv.id, exc_info=True)
    else:
        inv.status = "rejected"

    await db.commit()
    return {
        "autorizada": retorno.autorizada,
        "cstat": retorno.cstat_final,
        "motivo": retorno.motivo_final,
        "protocolo": retorno.nprot,
        "chave": nota.chave,
        "status": inv.status,
    }


# ── Eventos ───────────────────────────────────────────────────────────────────


async def cancelar(db: AsyncSession, inv: Invoice, cmig: CMIG, cfg: CMIGFiscalConfig, justificativa: str) -> dict:
    if not inv.access_key or not inv.auth_protocol:
        raise SefazServiceError("NF-e sem chave/protocolo de autorização — não há o que cancelar.")
    settings = get_settings()
    environment = cfg.environment or "homolog"
    pfx_path, senha = resolve_cert(cfg)
    ret = await asyncio.to_thread(
        cancelamento.cancelar_nfe,
        chave=inv.access_key, cnpj_emitente=_digits(cmig.cnpj), uf_emitente=(cmig.state or "").upper(),
        ambiente=_AMB.get(environment, "homologacao"), protocolo_autorizacao=inv.auth_protocol,
        justificativa=justificativa, pfx_path=pfx_path, pfx_password=senha,
        timeout=int(settings.NFE_SEFAZ_TIMEOUT), verify_ssl=_verify_ssl(environment),
        runtime_dir=_runtime_dir(),
    )
    await _log(db, invoice_id=inv.id, cmig_id=cmig.id, operation="cancelamento",
               cstat=ret.cstat, xmotivo=ret.motivo, req=ret.envelope_soap, resp=ret.response.body)
    if ret.ok:
        inv.status = "cancelled"
        inv.cancelled_at = datetime.now(UTC)
        inv.cancel_reason = justificativa
        inv.cancel_protocol = ret.protocolo
    await db.commit()
    return {"cancelada": ret.ok, "cstat": ret.cstat, "motivo": ret.motivo, "protocolo": ret.protocolo}


async def carta_correcao(
    db: AsyncSession, inv: Invoice, cmig: CMIG, cfg: CMIGFiscalConfig, correcao: str, n_seq: int,
) -> dict:
    if not inv.access_key:
        raise SefazServiceError("NF-e sem chave de acesso — não há o que corrigir.")
    settings = get_settings()
    environment = cfg.environment or "homolog"
    pfx_path, senha = resolve_cert(cfg)
    ret = await asyncio.to_thread(
        cancelamento.carta_correcao,
        chave=inv.access_key, cnpj_emitente=_digits(cmig.cnpj), uf_emitente=(cmig.state or "").upper(),
        ambiente=_AMB.get(environment, "homologacao"), correcao=correcao, n_seq_evento=n_seq,
        pfx_path=pfx_path, pfx_password=senha,
        timeout=int(settings.NFE_SEFAZ_TIMEOUT), verify_ssl=_verify_ssl(environment),
        runtime_dir=_runtime_dir(),
    )
    await _log(db, invoice_id=inv.id, cmig_id=cmig.id, operation="cce",
               cstat=ret.cstat, xmotivo=ret.motivo, req=ret.envelope_soap, resp=ret.response.body)
    await db.commit()
    return {"ok": ret.ok, "cstat": ret.cstat, "motivo": ret.motivo, "protocolo": ret.protocolo}


async def consultar(db: AsyncSession, inv: Invoice, cmig: CMIG, cfg: CMIGFiscalConfig) -> dict:
    """Regra N-6: consulta a situação da nota pela chave (antes de reenviar / refresh-status)."""
    if not inv.access_key:
        raise SefazServiceError("NF-e sem chave de acesso para consultar.")
    settings = get_settings()
    environment = cfg.environment or "homolog"
    pfx_path, senha = resolve_cert(cfg)
    ret = await asyncio.to_thread(
        consulta.consultar_nfe,
        inv.access_key, ambiente=_AMB.get(environment, "homologacao"),
        uf=(cmig.state or "").upper(), pfx_path=pfx_path, pfx_password=senha,
        timeout=int(settings.NFE_SEFAZ_TIMEOUT), verify_ssl=_verify_ssl(environment),
        runtime_dir=_runtime_dir(),
    )
    await _log(db, invoice_id=inv.id, cmig_id=cmig.id, operation="consulta",
               cstat=ret.cstat, xmotivo=ret.motivo, req="", resp=ret.response.body)
    inv.sefaz_cstat = ret.cstat
    inv.sefaz_xmotivo = (ret.motivo or "")[:255]
    if ret.autorizada and inv.status != "authorized":
        inv.status = "authorized"
        inv.auth_protocol = ret.nprot or inv.auth_protocol
    elif ret.cstat in ("101", "151", "135"):
        inv.status = "cancelled"
    await db.commit()
    return {"cstat": ret.cstat, "motivo": ret.motivo, "protocolo": ret.nprot, "status": inv.status}


async def manifestar(
    db: AsyncSession, inv: Invoice, cmig: CMIG, cfg: CMIGFiscalConfig, tipo: str,
    justificativa: str | None = None,
) -> dict:
    """Manifestação do destinatário sobre NF-e recebida (vai ao Ambiente Nacional)."""
    if inv.direction != "in" or not inv.access_key:
        raise SefazServiceError("Manifestação só se aplica a NF-e de entrada com chave de acesso.")
    settings = get_settings()
    environment = cfg.environment or "homolog"
    ambiente = _AMB.get(environment, "homologacao")
    pfx_path, senha = resolve_cert(cfg)
    ret = await asyncio.to_thread(
        cancelamento.manifestar,
        chave=inv.access_key, cnpj_destinatario=_digits(cmig.cnpj), tipo=tipo, ambiente=ambiente,
        endpoint_url=SEFAZ_EVENTO_AN[ambiente], pfx_path=pfx_path, pfx_password=senha,
        justificativa=justificativa,
        timeout=int(settings.NFE_SEFAZ_TIMEOUT), verify_ssl=_verify_ssl(environment),
        runtime_dir=_runtime_dir(),
    )
    await _log(db, invoice_id=inv.id, cmig_id=cmig.id, operation="manifestacao",
               cstat=ret.cstat, xmotivo=ret.motivo, req=ret.envelope_soap, resp=ret.response.body)
    if ret.ok:
        inv.manifestation = tipo
        inv.manifestation_at = datetime.now(UTC)
        inv.manifestation_protocol = ret.protocolo
    await db.commit()
    return {"ok": ret.ok, "cstat": ret.cstat, "motivo": ret.motivo, "tipo": tipo}


async def inutilizar(
    db: AsyncSession, cmig: CMIG, cfg: CMIGFiscalConfig, *, serie: int, n_ini: int, n_fim: int,
    ano: int, justificativa: str,
) -> dict:
    """Inutiliza faixa de numeração nunca emitida (evita gap fiscal)."""
    from services.fiscal.sefaz import inutilizacao

    settings = get_settings()
    environment = cfg.environment or "homolog"
    pfx_path, senha = resolve_cert(cfg)
    ret = await asyncio.to_thread(
        inutilizacao.inutilizar_nfe,
        cnpj=_digits(cmig.cnpj), uf=(cmig.state or "").upper(),
        ambiente=_AMB.get(environment, "homologacao"), ano=ano, modelo=55, serie=serie,
        n_ini=n_ini, n_fim=n_fim, justificativa=justificativa, pfx_path=pfx_path, pfx_password=senha,
        timeout=int(settings.NFE_SEFAZ_TIMEOUT), verify_ssl=_verify_ssl(environment),
        runtime_dir=_runtime_dir(),
    )
    await _log(db, invoice_id=None, cmig_id=cmig.id, operation="inutilizacao",
               cstat=ret.cstat, xmotivo=ret.motivo, req=ret.xml_assinado, resp=ret.response.body)
    await db.commit()
    return {"ok": ret.ok, "cstat": ret.cstat, "motivo": ret.motivo, "protocolo": ret.protocolo}


# Evita warning de import não usado (FiscalError é parte do contrato exportado)
_ = FiscalError
