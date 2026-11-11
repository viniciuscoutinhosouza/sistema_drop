# ADR-0041 — Emissão AUTOMÁTICA de NF-e + etiqueta com DANFE ao ficar "Pronto p/ Envio"

**Status:** Aceita (Fase 1 implementada — 2026-11-10; **pendente prova em produção** da etiqueta com
a chave da DANFE, por conta CNPJ real ML + Shopee — não testável no DEV).
**Relaciona / emenda:** [ADR-0030](ADR-0030-emissao-nfe-por-conta-own-vs-marketplace.md) (eixo por
conta own×marketplace; esta ADR **substitui a confirmação por-pedido pelo opt-in por conta**),
[ADR-0015/0028](ADR-0015-emissao-propria-nfe-sefaz.md) (emissão própria SEFAZ), [ADR-0021](ADR-0021-captura-completa-nfe-faturador-ml.md)
(Faturador ML), [ADR-0020](ADR-0020-paridade-shopee-por-costuras.md) (regra de ouro Shopee),
[ADR-0027](ADR-0027-rastreabilidade-lote-validade-serial.md) (rastreável = própria), [ADR-0017](ADR-0017-dce-emissao-marketplace.md)
(CPF = DC-e), [ADR-0004/0019] (SSOT de estoque).

## Contexto

O dono pediu: por conta de marketplace, com o campo **"Emissão de NF-e (pedidos não-FULL)"**
(ADR-0030):
- **Própria** → ao ficar "Pronto p/ Envio", o sistema emite a NF-e na SEFAZ, informa ao marketplace
  (ML/Shopee) e a **etiqueta sai com o código da DANFE**.
- **Pelo Marketplace** (texto corrigido: removido "(Faturador do Mercado Livre)" — cada marketplace
  emite a SUA NF-e) → ao ficar "Pronto p/ Envio", o sistema **comanda** o marketplace a emitir a nota
  e recebe a etiqueta com a DANFE.

A emissão nos dois modos **já existia** (ADR-0030), mas **manual** (operador clica "Emitir"). O que
faltava era a **automação** (disparar sozinho no `ready_to_ship`) e o **encadeamento da etiqueta**.

Verificado com `mercado-livre-especialista` e `shopee-especialista`:
- **Sequência (igual nos 2):** pago → `invoice_pending` → [emitir/informar NF-e] → marketplace gera
  CT-e → `ready_to_print`/validada → [baixar etiqueta — **só aí** sai com a DANFE] → despacho. A
  etiqueta com DANFE **só existe DEPOIS da nota** (processo assíncrono de 2 tempos).
- **ML:** marketplace = `POST /users/{seller}/invoices/orders` (Faturador, opt-in, assíncrono);
  own = `POST /shipments/{id}/invoice_data?siteId=MLB` (XML autorizado) — libera a etiqueta; ordem
  nota→etiqueta obrigatória; usar `refresh=True` p/ a DANFE entrar na etiqueta cacheada.
- **Shopee:** `'own'|'marketplace'` **não comanda** a Shopee — espelha o estado da loja (**Invoice
  Issuer** ligado = a Shopee emite sozinha; a gente só lê a chave). own = emite SEFAZ + `upload_invoice_doc`
  + a Shopee valida (gate pré-`ship_order`).
- **Incógnita central (Fase 2, só em produção):** não há prova pela doc de que o PDF/ZPL da etiqueta
  já traz o bloco DANFE embutido — **exige teste com pedido real** em cada marketplace.

Tensão fiscal: a ADR-0030 **exigiu confirmação humana** antes da emissão própria (ato irreversível).
O dono optou por **automático**. Decisão: travar com **opt-in por conta** (não global) + gate de
homologação + travas de unicidade.

## Decisão

1. **Opt-in por conta (`marketplace_accounts.nfe_auto_emit`, migration 184, default OFF).** Ligar
   exige papel fiscal (`cmig_fiscal_config`) + CMIG CNPJ. **O opt-in por conta SUBSTITUI a confirmação
   por-pedido da ADR-0030 como ato de consentimento do dono.** Default OFF = **zero regressão** (o
   deploy sozinho não muda o comportamento de nenhuma conta).
2. **Gatilho no POLL existente** (decisão do dono — sem webhook em tempo real na Fase 1): hooks leves
   de transição em `webhook_service` (ML `_apply_shipment_to_order`; Shopee `_update_shopee_order_stock`)
   — rodam tanto no webhook quanto no poll de 15 min. O hook **só arma** (não faz trabalho fiscal
   pesado no inbound).
3. **Claim ATÔMICO anti dupla-emissão** (`auto_fiscal_dispatch.arm_if_eligible`): `UPDATE orders SET
   auto_fiscal_status='emitting' WHERE auto_fiscal_status IS NULL AND nfe_status NOT IN
   (authorized,pending,in_process)` — compare-and-set por rowcount; dois ticks (poll+webhook) não
   re-armam, e não re-arma estado terminal.
4. **Núcleo fiscal como ATOR DE SISTEMA, reusando o roteador único (regra de ouro ADR-0020):** a etapa
   de emissão chama `routers.orders.emit_order_nfe(..., current_user=None)` — **o MESMO switch** do
   botão manual (own→SEFAZ+informa; ML marketplace→Faturador; Shopee own→emite+anexa), com todas as
   travas. `current_user=None` = sistema: os helpers de escopo (`_check_cmig_access`, `_get_order_checked`,
   `_assert_owner_or_admin`) tornaram-se **None-safe** (pulam o escopo; **inalcançável por rota** —
   `get_current_user` sempre injeta usuário), e `created_by_user_id=NULL` (auditável como sistema).
   **Não** se injeta um admin sintético (burlaria silenciosamente a capacidade) nem se reimplementa a
   decisão fiscal (2º switch quebraria a regra de ouro).
5. **Único branch-por-plataforma = etapa de FINALIZAÇÃO** (`_finalize_ml`/`_finalize_shopee`), que já é
   naturalmente ramificada: ML destrava a nota (reusa `fetch_and_cache_order_invoices`) e, quando
   autorizada, **reaquece a etiqueta com `refresh=True`** (DANFE); Shopee confirma a **validação** na
   Shopee (probe `invoice_data`, cobre own e Invoice Issuer). **Shopee em modo `marketplace` (Invoice
   Issuer) NÃO chama emissão própria** — a Shopee emite sozinha; a gente só aguarda a chave.
6. **Gate de homologação — SÓ para emissão própria (`own`):** o auto só emite própria quando
   `CMIGFiscalConfig.environment=='production'` (homolog não tem valor fiscal → **nenhum ato
   silencioso**; vira `error` VISÍVEL). No modo **marketplace** (ML Faturador / Shopee Invoice Issuer)
   a nota é **real do marketplace** — não depende do nosso ambiente SEFAZ, então **não** é gateada por
   produção (senão o Invoice Issuer, que pode não ter config SEFAZ, ficaria inutilizável). Ordem dos
   gates em `_do_emit`: CPF → Shopee Invoice Issuer → gate-produção(own) → unicidade → N-6 → ato.
7. **Falhar alto, nunca em silêncio:** toda falha vai para `orders.auto_fiscal_error` (com **PII
   mascarada** — `sanitize_fiscal_msg` oculta CPF/CNPJ que a SEFAZ/Shopee ecoam). Teto em **ambas** as
   etapas: emissão (`_MAX_ATTEMPTS=5`) e **finalização** (`_MAX_FINALIZE_TICKS=72` ≈ 6 h) — nota que
   não resolve vira `error` VISÍVEL, não reagenda para sempre. O job também **persiste** o erro no
   pedido (não só log). "Ainda não liberada" **reagenda** dentro do teto (não é erro).
8. **Recuperação N-6 (anti dupla-nota):** se já há invoice própria em `'processing'` (número reservado,
   talvez já na SEFAZ), o auto **não re-transmite** (duplicaria) — reusa `invoices.refresh_status`
   (consulta pela chave, regra N-6) para recuperar.
9. **Lane ≠ verdade fiscal:** `orders.auto_fiscal_status` (emitting|emitted|done|error) é só
   observabilidade; o SSOT da autorização continua em `nfe_status`/`Invoice`.
10. **Job dedicado** `tasks/auto_fiscal.py` (a cada 5 min, `tracked_job`): avança os pedidos armados. A
   convergência de `nfe_status` com `sync_pending_nfe` é benigna (ambos escrevem a MESMA verdade do
   ML); a dupla-EMISSÃO é barrada por (3) + re-checagem de unicidade antes do ato fiscal.
11. **NÃO auto-despacha.** O auto cobre a parte **fiscal** (emitir/informar/validar a NF-e e deixar a
    etiqueta pronta com a DANFE). O **ship físico** (ML: separação/coleta; Shopee: `ship_order`) segue
    no fluxo de **Separação** já existente — evita despacho irreversível sem conferência.

## Elegibilidade (espelha o roteador manual)

FULL → fora (NF-e de venda é do ML). CPF (por-PEDIDO, `_order_issuer_type`) → fora (ML→DC-e,
Shopee→Invoice Issuer). Rastreável em conta `marketplace` → o guard `assert_order_own_emission`
(ADR-0027) **falha alto** (vira 'error' com mensagem clara; o dono muda a conta p/ `own`).

## Consequências

- **Fase 1 = código pronto; Fase 2 = prova em produção** (a chave da DANFE na etiqueta não é
  confirmável pela doc nem testável no DEV — exige 1 pedido CNPJ real ML + 1 Shopee).
- Pré-requisito operacional: conta CNPJ `own` deve ter o emissor do ML **desligado** no painel (o
  guard de captura protege, mas é melhor na origem).
- Latência: até ~5 min (job) após o `ready_to_ship` detectado (webhook ou poll de 15 min). Tempo real
  = **Fase 3** (webhook `shipments` do ML + fix da assinatura do push da Shopee).

## Follow-ups

- **Fase 2 (dono):** prova em produção da etiqueta com DANFE nos 2 marketplaces.
- **Fase 3:** webhook `shipments` (ML) + corrigir assinatura do push Shopee (`hmac(key, url+"|"+body)`)
  p/ latência imediata.
- Confirmar ao vivo o encoding do `upload_invoice_doc` da Shopee (multipart × access_key) e se a
  etiqueta Shopee Xpress (ZPL) traz o bloco fiscal.
- Painel/coluna na UI mostrando `auto_fiscal_status`/`auto_fiscal_error` por pedido (observabilidade).
