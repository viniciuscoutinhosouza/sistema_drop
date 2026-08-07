# ADR-0023 — Estoque de produto composto (kit) é derivado dos componentes, nunca materializado

**Data:** 2026-08-07
**Status:** ✅ Aceita
**Decisores:** Vinicius (proprietário) — regra enunciada por ele

## Contexto

Produto composto (`is_composite=True`, componentes em `CatalogProductComponent` / `CMIGProductComponent`) não tem estoque físico próprio: quem tem estoque são os componentes. O sistema convivia com **duas** representações do mesmo número — a coluna `stock_quantity` do kit (materializada em alguns caminhos) e o cálculo `MIN(floor(estoque_componente ÷ quantidade))` — e cada tela escolhia uma.

Sintoma que originou a decisão: o kit aparecia **sem estoque no Catálogo e não permitia publicar**, embora a tela PG mostrasse o valor correto. Medido em produção: 3 dos 6 kits ativos com coluna 0 e disponível real 25, 25 e 7.

A investigação mostrou que o problema não era de exibição. Ao publicar, `_refresh_product_stock` devolvia 0 e **gravava 0** no kit; `_build_ml_payload` fazia `available_quantity or 1`, então o kit iria ao marketplace com **1 unidade fantasma, em silêncio**; e `available_to_push` o auto-pausaria no ciclo seguinte (ADR-0014). Corrigir só a vitrine teria desbloqueado o botão para publicar errado.

## Decisão

Regra do dono, adotada como invariante:

> "O estoque de composto deve apresentar sempre o calculado. Qualquer venda ou alteração em um dos itens do composto ou no próprio composto deve atualizar o cálculo."

1. **Ponto único de cálculo:** `services/fiscal/stock_calculator.composite_stock(components, *, discount_reserved=False)`. Clampa negativo em 0 e tolera FK pendurada. Existiam 4 cópias da fórmula; todas passaram a delegar.
2. **Sempre derivado na leitura, nunca materializado.** `catalog_products.stock_quantity` / `cmig_products.stock_quantity` do kit é **sempre 0**; nenhum caminho escreve nele. Um valor materializado envelhece e passa a discordar do calculado.
3. **Propagação nos dois sentidos:**
   - *componente → kit*: automática (o kit é derivado; não há valor guardado para ficar velho). A propagação para os **anúncios** do kit já existe em `stock_sync_service`, que expande componente → kits.
   - *venda do kit → componentes*: reserva, liberação e baixa atingem os **componentes** (`_kit_components` em `stock_reservation_service`), não o kit.
4. **Kit fora do snapshot contábil** (`daily_stock_reconcile`): snapshotar o kit somaria as mesmas unidades duas vezes (kit + componentes).
5. **Falhar alto:** publicar com quantidade 0 é erro explícito (422), nunca anúncio de 1 unidade. Antes de recusar, o modo `product` cai para o saldo do FULL (ADR-0008 §2).

### Leitores que derivam (paridade verificada em produção)

`/catalog` (lista e detalhe), `/pg`, `/cmigs`, publicação (`_refresh_product_stock`), `available_to_push` (job de 30 min + Shopee, que consome o mesmo número antes de ramificar por plataforma), botão manual "Sincronizar estoque", card de Controle de Estoque e extrato (`stock_view.card_from_product`), tela de Anúncios (`_serialize_listing`).

## Consequências

- **Positivas:** um número só, em todas as telas e no marketplace (verificado: os 6 kits batem em calculado/catálogo/card/anúncio/publicar). O kit publicável. Fim da janela de oversell entre a venda do kit e o despacho — reservar nos componentes derruba o disponível deles na hora, e o anúncio do componente re-sincroniza.
- **Custo:** o cálculo roda por leitura. Os relacionamentos são `lazy="selectin"`, então não há lazy-load em contexto async nem N+1 por linha; mas `available_to_push` passou a carregar a entidade inteira por anúncio no job de sync (era um SELECT de 2 colunas). Otimizar se o volume crescer.
- **Oversell residual aceito:** kit e componente podem estar anunciados ao mesmo tempo, lastreados nas mesmas unidades físicas. A reserva nos componentes fecha a janela **após a venda**; ela não impede que ambos anunciem o mesmo saldo antes. Mitigar exigiria rateio ou trava de publicação simultânea — não decidido.

## Alternativa considerada

**Materializar** o estoque do kit em `stock_quantity` via `calculate_pg_product_stock`. Consertaria de graça publicação, sync e todas as telas, com um leitor só. Rejeitada: o kit passaria a somar como estoque físico ao lado dos próprios componentes na tela de Estoque e no inventário — dupla contagem na trilha contábil (ADR-0004).

## Relação com outras ADRs

- **ADR-0004** (estoque SSOT): esta ADR define que, para composto, a SSOT é o **cálculo**, não a coluna; e exclui o kit do snapshot para não duplicar.
- **ADR-0014** (pausa automática): com o disponível correto, o kit deixa de ser auto-pausado; kits pausados pelo bug se auto-curam na reativação.
- **ADR-0008 §2** (anúncio não-FULL anuncia o FULL quando LOCAL=0): preservado — o gate de publicação consulta o FULL antes de recusar.
- **ADR-0020** (regra de ouro Shopee): a correção entrou em código agnóstico (`if is_composite`, nunca `if platform == ...`), então a Shopee herdou pelo `available_to_push`.

## Pendências

1. `listings.py` publica com `available_quantity: 1` / `seller_stock: [{"stock": 1}]` fixos (ML e Shopee). Se for caminho vivo, ainda cria anúncio fantasma — não deriva estoque nem falha alto.
2. `or 1` sobrevive no form dos caminhos de **update** (`sync_listing_to_ml`): re-push de anúncio auto-pausado ainda pode mandar 1 ao ML.
3. Política de oversell kit ⇄ componente (ver Consequências).
