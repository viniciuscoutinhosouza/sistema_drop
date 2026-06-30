"""Camada fiscal pura de emissão própria de NF-e (SEFAZ direto).

Portada e adaptada do projeto NFE_VendasProduto (validado em produção, cStat=100)
para o padrão do Sistema Drop. São funções puras (sem ORM, sem rede além da SEFAZ)
que recebem dataclasses e devolvem dataclasses — o adaptador
`services/fiscal/sefaz_service.py` monta `NotaEmissao` a partir do nosso
Invoice/CMIG/Person/CMIGProduct e persiste o resultado.

Correções fiscais aplicadas (Simples Nacional / e-commerce — Consultor-Fiscal-NFE):
- PIS/COFINS CST 99 zerado (não "49").
- Sem grupo IPI (revendedor não é contribuinte de IPI).
- Sem grupo ICMSUFDest/DIFAL de partilha para CRT 1 (Tema 1093/STF).
- CSOSN 102 (default) e 500 (mercadoria com ICMS-ST já retido).
"""
