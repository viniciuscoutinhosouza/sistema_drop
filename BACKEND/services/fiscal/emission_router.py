"""Roteamento de emissão de NF-e POR CONTA (migration 151): 'own' (emissão própria SEFAZ,
ADR-0015/0028) × 'marketplace' (Faturador do Mercado Livre).

Funções PURAS (sem I/O / sem router) — a orquestração 1-clique vive em routers/orders.py
(`_emit_own_nfe`), que reusa os endpoints oficiais de invoices (create/transmit) e mapeia as
exceções SEFAZ para HTTP. Aqui ficam só: resolução do modo, detecção de FULL e o RESUMO
irretratável mostrado antes de transmitir (decisão do dono: 1 clique + confirmação).
"""


def account_nfe_mode(account) -> str:
    """'own' se a conta foi configurada para emissão própria; senão 'marketplace' (padrão)."""
    return "own" if (getattr(account, "nfe_emission_mode", None) == "own") else "marketplace"


def is_full_order(order) -> bool:
    """Pedido FULL (logística ML): a NF-e de venda é do ML — fica FORA da emissão própria por conta
    (ADR-0010/0022). Checa o modo canônico e o método cru como rede de segurança."""
    if (getattr(order, "shipping_mode", None) or "") == "full":
        return True
    return "fulfillment" in (getattr(order, "shipping_method", None) or "")


def _mask_doc(doc) -> str | None:
    """Mascara CPF/CNPJ no resumo (LGPD) — mostra só o suficiente p/ conferência."""
    if not doc:
        return None
    digits = "".join(ch for ch in str(doc) if ch.isdigit())
    if len(digits) <= 4:
        return "***"
    return f"{digits[:2]}***{digits[-2:]}"


def build_emission_summary(inv, person, cfg, ambiente: str) -> dict:
    """Resumo IRRETRATÁVEL mostrado antes de transmitir à SEFAZ (ato irreversível): destinatário,
    natureza, CFOP/CST/NCM por item e totais, mais o AMBIENTE (homolog não tem valor fiscal)."""
    itens = []
    for it in sorted(inv.items, key=lambda x: x.item_number or 0):
        cst = getattr(it, "icms_cst", None) or getattr(it, "csosn", None)
        itens.append(
            {
                "item": it.item_number,
                "descricao": it.description,
                "ncm": it.ncm,
                "cfop": it.cfop,
                "cst_csosn": cst,
                "quantidade": float(it.quantity or 0),
                "valor_unit": float(it.unit_value or 0),
                "valor_total": float(it.total_value or 0),
            }
        )
    return {
        "ambiente": ambiente,  # 'production' | 'homolog'
        "serie": getattr(cfg, "manual_nfe_serie", None),
        "natureza_operacao": inv.natureza_operacao,
        "destinatario": {
            "nome": getattr(person, "name", None),
            "documento": _mask_doc(getattr(person, "document", None)),
            "uf": getattr(person, "state", None),
        },
        "itens": itens,
        "total_produtos": float(inv.total_products or 0),
        "total_nota": float(inv.total_invoice or 0),
    }
