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
   - **Guard de escrita/replay (o invariante kit=0 no cache):** `calculate_pg_product_stock` e `calculate_cmig_product_stock` fazem `if is_composite: return 0` **antes de qualquer evento** — o replay nunca escreve saldo no kit (via `recompute_*_stock`). Complementado pela exclusão de compostos em `create_inventory`/`finalize_inventory` (kit não é item contável). *Regressão real corrigida (2026-09-21): sem o guard, o passo "pedidos diretos no PG" descontava a venda do KIT no id do próprio kit → saldo negativo fantasma, enquanto o componente físico ficava intocado; o componente continua debitado à parte pelo `kit_usage`.*
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
3. **Política de oversell kit ⇄ componente — REVERTIDA (2026-08-07).** A trava de publicação simultânea foi implementada e **removida no mesmo dia**, depois que a medição mostrou que ela contrariava o modelo do sistema.

   **O dado que derrubou a trava:** 36 dos 73 produtos PG com anúncio ativo **já estão anunciados por mais de uma conta** — metade do catálogo, em CMIGs diferentes vendendo do mesmo galpão (ex.: conta #2/MIG e #41/MBS). "As mesmas unidades em mais de uma vitrine" é a **operação normal**, não uma anomalia. Travar o par kit⇄componente aplicava ao kit uma regra que o sistema não aplica ao caso idêntico de dois vendedores anunciando o mesmo produto — e bloqueava operação rotineira (o dono bateu no 409 na prática).

   **O que de fato distinguia o kit era o multiplicador** (kit vende 1, consome 2 do componente), e isso já foi resolvido: a venda do kit reserva e baixa os componentes na hora. Com isso o kit passa a se comportar como qualquer outra vitrine, e o risco residual (vender muito entre dois ciclos de sync) é **o mesmo** que já existe entre duas contas anunciando o mesmo produto.

   **Decisão do dono:** remover a trava, **e recalcular o estoque do kit a cada movimentação de entrada ou saída de kit ou componente**. Como o kit é derivado, o *valor* já está sempre correto na leitura; o que faltava era a **propagação para os anúncios**: `reserve_stock` e `release_reservation` não disparavam `schedule_push` (só o despacho disparava), então reservar deixava o disponível defasado nos anúncios até o ciclo de 30 min. Agora os três caminhos coletam os ids tocados — **incluindo os componentes expandidos do kit** — e propagam na hora; o `stock_sync_service` expande componente → kits, então kit e componente são reavaliados juntos.

   Se um dia for preciso limitar de fato quanto cada vitrine pode vender, o mecanismo correto já existe e não é uma trava: **estoque fixo como teto** (ADR-0014, `min(fixo, disponível)`) — rateio explícito por anúncio.

## Emenda — Montagem (kitting) na remessa ao FULL (2026-09-21)

**Contexto:** ao enviar um KIT ao FULL por **remessa** (NF-e `purpose='remessa'`, "Remessa para Deposito Temporario"), o kit é fisicamente **montado** a partir dos componentes. O sistema movia o KIT ao FULL, mas **não consumia os componentes** (ex.: KIT_501D ia ao FULL e o 501D não baixava).

**Decisão do dono:**
1. **Montagem na remessa:** cada componente **sai** do estoque local na quantidade da composição ("saída para transformação em KIT"); o KIT **entra** montado (1 un por unidade da nota). Localmente o kit fica **líquido 0** (montagem +N, remessa −N) — a ADR-0023 (kit derivado) segue válida no LOCAL. O componente é debitado de fato.
2. **O FULL guarda o KIT como unidade** (não os componentes) — é o que foi enviado e é vendido como kit no ML.
3. **Retorno do FULL:** o KIT volta ao galpão **como unidade montada** (materializada no LOCAL). A **desmontagem** (voltar aos componentes) é uma **ação MANUAL do operador** — não automática. → *Consequência: o kit passa a poder ter `stock_quantity` LOCAL materializado (unidades montadas retornadas). O invariante evolui:* **disponível do kit (LOCAL) = unidades montadas em estoque + montáveis a partir dos componentes**; a venda/remessa consome primeiro a unidade montada, senão monta a partir dos componentes.
4. **Extrato:** a montagem aparece no extrato dos DOIS produtos (`kit_assembly_out` no componente, `kit_assembly_in` no kit).

**Implementação (Fase 1, forward + backfill):** `stock_calculator.calculate_pg_product_stock` passo 3b debita o componente pelo consumo de kit em remessas ao FULL (espelha o `kit_usage` dos pedidos); `affected_products_from_invoice` propaga os componentes; `services/fiscal/kit_assembly.py` grava os movimentos (idempotente) em `recompute_after_invoice_change` e no backfill de todas as remessas de kit. Verificado ao vivo: 501D passou a debitar 20 un (6 remessas, backfill).

**Pendente (Fase 3, próximo incremento):** retorno do FULL materializando o KIT no galpão + ação manual de desmontagem + ajuste do cálculo do disponível do kit para (materializado + derivado). E o **-4 fantasma do espelho CMIG** (CMIGProduct do kit com `is_composite=False`) — alinhar `is_composite` ao PG.

