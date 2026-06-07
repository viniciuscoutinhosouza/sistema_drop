# ADR-0005 — Separação NÃO-FULL: Carrinho Gaiola + estados separated/shipped do pedido

**Data:** 2026-06-06
**Status:** Aceito (implementado)
**Decisores:** Vinicius (proprietário)

## Contexto

Pedidos **não-FULL** (entregues pelo Galpão — flex, agência, correios, coletado,
combinado) chegam de várias CMIGs e marketplaces, mas não havia tela operacional
para o Operador Logístico (role `ugo` / perfil "Gestor Logístico") separar,
etiquetar e despachar esses pedidos. O fluxo era feito fora do sistema, sem
rastreio de quem separou/despachou nem ponto definido de baixa de estoque.

## Decisões tomadas

### 1. Entidade "Carrinho Gaiola" (PickingCart) com máquina de estados

Três tabelas novas (migrations 85):
- `picking_carts` — cabeçalho. Estados: `open → separated → delivered` (+ `cancelled`).
  `cart_mode` define o fluxo: `manual` ou `scan` (bipagem).
- `picking_cart_orders` — vínculo pedido↔gaiola, com `item_status` (`pending → separated`).
- `picking_cart_items` — linhas esperadas por unidade (kits expandidos em componentes),
  com `expected_qty`/`scanned_qty` para conferência por bipagem (modo `scan`).

Regra do modo `scan`: o pedido só pode ser marcado separado após bipar 100% das
unidades (SKU ou EAN). O incremento de `scanned_qty` é **atômico e condicional**
(`UPDATE ... WHERE scanned_qty < expected_qty`) para tolerar leitores que disparam
em rajada.

### 2. Extensão da máquina de estados de Order

Migration 86 adiciona em `orders`: `separated_at/by`, `dispatched_at/by`,
`picking_cart_id`. Ciclo do pedido não-FULL:
`paid → separated` (gaiola concluída) `→ shipped` (entregue à transportadora).
Elegível para separação: `status ∈ {downloaded, paid, label_generated, label_printed}`,
`payment_status='paid'`, `shipping_mode != 'full'`, `picking_cart_id IS NULL`.

### 3. Ponto único de baixa de estoque (interação com ADR-0004)

A baixa física de estoque ocorre **somente** na entrega à transportadora
(`POST /carts/{id}/deliver`), reusando `confirm_dispatch` do
`stock_reservation_service` — **idempotente** por `stock_movements(movement_type='dispatch')`.
NÃO há baixa na separação nem na conclusão da gaiola. Isso preserva o SSOT do
ADR-0004 e evita dupla baixa. Falhas de `confirm_dispatch` são retornadas em
`failed_dispatch` na resposta e logadas em nível `error` (pedido fica `shipped`
sem baixa → requer reprocesso manual; não há job automático).

### 4. Cancelamento devolve os pedidos

`POST /carts/{id}/cancel` reverte `order.picking_cart_id=NULL` e, se já estava
`separated`, volta para `paid` (limpando carimbos), removendo os vínculos. Garante
que nenhum pedido fique órfão fora da lista de separação. A FK
`orders.picking_cart_id` usa `ON DELETE SET NULL`, mas a integridade de fluxo é
feita em código (não confiar no SET NULL para reverter status).

### 5. Autorização e escopo

Permissão por `menu_key='separacao'` (migration 87 nos perfis `admin` e `gl`).
Escopo por galpão: operador só vê/manipula pedidos e gaiolas do seu
`warehouse_id` (mesmo predicado de `orders.py`). Operador não-admin **sem**
galpão é bloqueado (NULL-safe).

### 6. Resolução de produto via ponte canônica

`_resolve_base` usa o vínculo direto do item e, na ausência, faz fallback para
`resolve_order_item_link` (ProductListing/DP/SKU) — cobre pedidos ML vinculados
só pelo anúncio. Kits expandidos via `CatalogProductComponent`/`CMIGProductComponent`.

### 7. Etiquetas com layout configurável

`label_service.LABEL_LAYOUTS` é um registry extensível; inicia com `10x15`
(térmica, 1 etiqueta por volume) e `a4_4up` (A4, 4 por página). NF-e: apenas
abre a DANFE já existente do marketplace (`nfe_url`/`nfe_key`), sem emitir.

## Consequências

- 3 tabelas novas + 5 colunas em `orders` (migrations 85/86), menu_key em 87.
- Novo router `routers/separation.py` (15 rotas) + serviços `picking_service`
  (lógica pura testável), `picking_list_service` (PDF).
- Janela de inconsistência se `confirm_dispatch` falhar após `shipped` — mitigada
  por idempotência + `failed_dispatch` na resposta; reprocesso é manual por ora.
- Numeração de gaiola `G-AAAAMMDD-NNN` por galpão/dia (UTC); sem UNIQUE em
  `cart_number` (corrida de numeração possível, cosmética).
