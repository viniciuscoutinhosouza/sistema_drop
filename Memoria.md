# Memória de Trabalho — Sistema Drop

> Registro das tarefas concluídas, por **local** (CASA / ESCOL / NOTEBOOK), para manter a
> continuidade entre as 3 máquinas do dono. Mantém só os **últimos 5 dias**. Commitado no GitHub a
> cada tarefa concluída. Ao "baixar do github", a última entrada abaixo é a tarefa mais recente.

---

## 2026-10-29 23:46 — ESCOL — Sincronização de produtos da nota (multi-EAN) + reconciliação de entrada

**Pedido:** na tela Compra/Entrada, um ícone que indique que a nota tem produtos não sincronizados;
clicar abre um modal para vincular o produto da nota a um já cadastrado (adicionando o EAN — produto
pode ter 1+ EANs — ou corrigindo), ou cadastrar produto novo.

**Entregue e em produção:**
- **Multi-EAN** (`product_eans`, migration 172, CMIG + PG) consultado nas 3 superfícies de casamento
  de estoque (detector + 2 do replay) — aditivo, zero-regressão (tabela nasce vazia).
- **Bug de ordem corrigido** em `update_stock_from_invoice`: marcava `stock_updated` DEPOIS do
  recompute, então a própria nota não entrava no seu replay e o saldo não creditava na hora. Agora
  marca ANTES (igual `_apply_stock_movement`). **Corrige a contabilização de qualquer nota casada.**
- **Endpoints** (routers/invoices.py, `require_permission estoque_movimentar` + `_check_cmig_access`):
  `GET /{id}/stock-match`, `POST /{id}/items/{item_id}/link-product` (add/replace EAN, seta FK,
  re-contabiliza), `POST .../create-product` (reusa create_cmig_product; PG no galpão da CMIG;
  bloqueia KIT), `GET /product-eans/list`, `DELETE /product-eans/{id}`. `list_invoices` expõe
  `has_unmatched_items`.
- **Frontend:** coluna Estoque com ícone 🔗 vermelho quando `has_unmatched_items` → abre
  `ProductSyncModal` (lista itens, busca produto, vincular/criar, contabilizar). Ícone 📦 laranja =
  pendente de contabilizar; ✓ verde = contabilizado.

**Auditoria (trio):** adr-checker APROVADO; quality-guardian reprovou com 2 CRITICAL + 4 HIGH, TODOS
corrigidos e re-verificados: (C1) recontabilização nunca dá 500 cru; (C2) `replace_product` preserva
o EAN antigo como adicional (não rouba histórico no replay); (HIGH) casamento/deleção de PG por EAN
escopados por galpão (anti-IDOR cross-galpão); link/create PG falham alto sem galpão; ADR-0027
(lotes) espelha multi-EAN.

**Verificado em produção:** 60 testes (stock/invoice/fiscal/trace) passando; fluxo real exercitado
(stock-match → vincular add/replace → credita, com limpeza); migration 172 aplicada; 5 rotas no
OpenAPI; site 200. **10 das últimas 30 entradas** têm produto não sincronizado (inclui a 13001).

**Correção de deploy:** `EntradasView.vue` + `fiscal.js` tinham ficado fora dos commits → o bundle
não tinha a feature. Commitados (`a3380ff`) e rebuildados; bundle agora contém o ícone/modal.

**Follow-up:** criar produto por aqui usa `estoque_movimentar`; quando o follow-up do ADR-0036
fechar uma permissão própria de "criar produto", alinhar. Dono: hard-refresh (Ctrl+Shift+R) p/
carregar o bundle novo.
