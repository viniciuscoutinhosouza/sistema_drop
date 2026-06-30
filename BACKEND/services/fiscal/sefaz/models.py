"""Dataclasses imutáveis que circulam entre as camadas fiscais.

Não são modelos ORM — são objetos de transferência que isolam `xml_builder`/
`signer`/`emitter` de qualquer query SQL. Todas as funções ficam testáveis com
fixtures Python puras (sem banco, sem rede).

Convenções:
- `Decimal` para qualquer valor monetário/quantidade (nunca float).
- Strings com formato fiscal (CNPJ, CFOP, CSOSN, NCM, UF) validadas no `__post_init__`.
- Datas `datetime` timezone-aware (America/Sao_Paulo na emissão).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Literal

from services.fiscal.sefaz.exceptions import XmlBuildError

Ambiente = Literal["homologacao", "producao"]
Modelo = Literal[55, 65]
IndicadorIE = Literal[1, 2, 9]
TipoPessoa = Literal["PF", "PJ"]
TipoEmissao = Literal[1, 2, 3, 4, 5, 6, 7, 9]


@dataclass(frozen=True, slots=True)
class Endereco:
    logradouro: str
    numero: str
    bairro: str
    municipio_ibge: str
    municipio_nome: str
    uf: str
    cep: str
    complemento: str | None = None
    pais_codigo: str = "1058"
    pais_nome: str = "Brasil"

    def __post_init__(self) -> None:
        if not re.fullmatch(r"\d{7}", self.municipio_ibge):
            raise XmlBuildError(f"municipio_ibge deve ter 7 dígitos, recebido {self.municipio_ibge!r}")
        if not re.fullmatch(r"[A-Z]{2}", self.uf):
            raise XmlBuildError(f"uf deve ter 2 letras maiúsculas, recebido {self.uf!r}")
        if not re.fullmatch(r"\d{8}", self.cep):
            raise XmlBuildError(f"cep deve ter 8 dígitos, recebido {self.cep!r}")


@dataclass(frozen=True, slots=True)
class Estabelecimento:
    """Quem emite a NFe (CMIG emitente)."""

    cnpj: str
    ie: str
    razao_social: str
    endereco: Endereco
    crt: int  # 1=Simples Nacional, 2=Simples Excesso, 3=Regime Normal, 4=MEI
    aliquota_fecp: Decimal = Decimal("0")  # 2.00 para RJ (aplicado por produto da lista RICMS)
    nome_fantasia: str | None = None
    telefone: str | None = None
    ie_st: str | None = None

    def __post_init__(self) -> None:
        if not re.fullmatch(r"\d{14}", self.cnpj):
            raise XmlBuildError(f"cnpj deve ter 14 dígitos, recebido {self.cnpj!r}")
        if not self.ie:
            raise XmlBuildError("ie do emitente é obrigatória (use 'ISENTO' se aplicável)")
        if self.crt not in (1, 2, 3, 4):
            raise XmlBuildError(f"crt deve ser 1, 2, 3 ou 4, recebido {self.crt}")


@dataclass(frozen=True, slots=True)
class Cliente:
    """Destinatário da NFe (PF ou PJ)."""

    tipo: TipoPessoa
    cpf_cnpj: str
    nome_razao_social: str
    indicador_ie: IndicadorIE  # 1=contribuinte, 2=isento, 9=não-contribuinte
    endereco: Endereco
    ie: str | None = None
    email: str | None = None
    telefone: str | None = None

    def __post_init__(self) -> None:
        expected_len = 14 if self.tipo == "PJ" else 11
        if not re.fullmatch(rf"\d{{{expected_len}}}", self.cpf_cnpj):
            raise XmlBuildError(
                f"{self.tipo} exige {expected_len} dígitos em cpf_cnpj, recebido {len(self.cpf_cnpj)} chars"
            )
        if self.tipo == "PF" and self.indicador_ie != 9:
            raise XmlBuildError("PF deve ter indicador_ie=9")
        if self.indicador_ie == 1 and not self.ie:
            raise XmlBuildError("indicador_ie=1 (contribuinte) exige IE")
        if self.indicador_ie == 2 and self.ie != "ISENTO":
            raise XmlBuildError("indicador_ie=2 exige IE='ISENTO' literal")


@dataclass(frozen=True, slots=True)
class Produto:
    """Snapshot cadastral do produto levado pelo item."""

    codigo: str
    descricao: str
    ncm: str
    csosn: str
    origem: str  # '0'..'8'
    unidade: str
    cest: str | None = None
    ean: str | None = None
    aliquota_icms: Decimal = Decimal("18.00")
    # ICMS-ST já retido (CSOSN 500) — valores da retenção anterior.
    vbc_st_ret: Decimal | None = None
    vicms_st_ret: Decimal | None = None
    info_adicional: str | None = None

    def __post_init__(self) -> None:
        if not re.fullmatch(r"\d{8}", self.ncm):
            raise XmlBuildError(f"ncm deve ter 8 dígitos, recebido {self.ncm!r}")
        if not re.fullmatch(r"\d{3}", self.csosn):
            raise XmlBuildError(f"csosn deve ter 3 dígitos, recebido {self.csosn!r}")
        if self.origem not in "012345678":
            raise XmlBuildError(f"origem deve ser '0'..'8', recebido {self.origem!r}")


@dataclass(frozen=True, slots=True)
class ItemEmissao:
    """Item da nota com o CFOP da operação e quantidade/preço da venda."""

    numero_item: int
    produto: Produto
    quantidade: Decimal
    preco_unitario: Decimal  # vUnCom
    cfop: str  # 4 dígitos — CFOP da operação
    valor_frete: Decimal = Decimal("0")
    valor_desconto: Decimal = Decimal("0")
    valor_seguro: Decimal = Decimal("0")
    valor_outras: Decimal = Decimal("0")

    @property
    def valor_produto(self) -> Decimal:
        """vProd = qtd * preço, arredondado a 2 casas (regra SEFAZ)."""
        return (self.quantidade * self.preco_unitario).quantize(Decimal("0.01"))

    def __post_init__(self) -> None:
        if self.numero_item < 1:
            raise XmlBuildError(f"numero_item deve ser >= 1, recebido {self.numero_item}")
        if self.quantidade <= 0:
            raise XmlBuildError(f"quantidade deve ser > 0, recebido {self.quantidade}")
        if not re.fullmatch(r"\d{4}", self.cfop):
            raise XmlBuildError(f"cfop deve ter 4 dígitos, recebido {self.cfop!r}")


@dataclass(frozen=True, slots=True)
class Pagamento:
    """Bloco <pag> obrigatório na NFe 4.0.

    forma_pag: 01=dinheiro, 03=cartão crédito, 04=cartão débito, 17=PIX, 90=sem pagamento, 99=outros.
    ind_pag: 0=à vista, 1=a prazo.
    """

    forma_pag: str = "01"
    valor: Decimal = Decimal("0")
    ind_pag: int = 0
    troco: Decimal | None = None


@dataclass(frozen=True, slots=True)
class NotaEmissao:
    """Tudo que `montar_xml_nfe()` precisa. serie/numero/chave já reservados pelo adaptador."""

    modelo: Modelo
    serie: int
    numero: int
    ambiente: Ambiente
    chave: str
    c_nf: str
    dh_emi: datetime
    natureza_operacao: str
    finalidade: int  # 1=normal, 2=complementar, 3=ajuste, 4=devolução
    ind_presenca: int  # 0=N/A, 1=presencial, 2=internet, 9=outros
    ind_intermed: int  # 0=sem, 1=com intermediador
    ind_final: int  # 0=normal, 1=consumidor final
    emitente: Estabelecimento
    destinatario: Cliente
    itens: tuple[ItemEmissao, ...]
    pagamentos: tuple[Pagamento, ...] = field(default_factory=tuple)
    transporte_modalidade: int = 9  # 9=sem frete
    info_complementar: str | None = None
    info_fisco: str | None = None
    chave_referenciada: str | None = None  # devolução (finalidade=4) referencia a NF-e original
    ver_proc: str = "sistemadrop_nfe_1.0"
    tp_emis: TipoEmissao = 1

    def __post_init__(self) -> None:
        if not self.itens:
            raise XmlBuildError("NotaEmissao precisa de pelo menos 1 item")
        if self.modelo not in (55, 65):
            raise XmlBuildError(f"modelo deve ser 55 ou 65, recebido {self.modelo}")
        if self.ambiente not in ("homologacao", "producao"):
            raise XmlBuildError(f"ambiente inválido: {self.ambiente!r}")
        if len(self.chave) != 44:
            raise XmlBuildError(f"chave deve ter 44 dígitos, recebido {len(self.chave)}")
        if len(self.ver_proc) > 20:
            raise XmlBuildError(f"ver_proc tem max 20 chars, recebido {len(self.ver_proc)}")

    @property
    def valor_total_produtos(self) -> Decimal:
        return sum((item.valor_produto for item in self.itens), start=Decimal("0"))

    @property
    def valor_total_nf(self) -> Decimal:
        total = Decimal("0")
        for item in self.itens:
            total += item.valor_produto
            total += item.valor_frete + item.valor_seguro + item.valor_outras
            total -= item.valor_desconto
        return total.quantize(Decimal("0.01"))
