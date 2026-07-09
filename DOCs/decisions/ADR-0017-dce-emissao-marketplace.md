# ADR-0017 — Emissão de DC-e (modelo 99) no perfil Marketplace, direto na SVRS

**Data:** 2026-07-04
**Status:** ⛔ **SUPERSEDED (2026-07-09)** — a emissão própria via SEFAZ foi **desativada** (código
dormente) em favor do **emissor de DC-e do próprio Mercado Livre** (link `emissor/omni/emitir/dce`).
Motivo: a emissão própria em produção exige credenciamento SEFAZ-PR + cadeia **ICP-Brasil** (o
handshake TLS de produção falhou: `unable to get local issuer certificate` contra
`dce.fazenda.pr.gov.br`) + `NFE_ICP_CABUNDLE` não estava wired. O ML emite a DC-e e libera a etiqueta
sem nada disso do nosso lado. Ver o adendo "Virada para o emissor do ML" abaixo.
**Decisores:** Vinicius (proprietário) + contador

## Contexto

Contas de vendedor configuradas como **pessoa física (CPF)** não emitem NF-e; desde 06/04/2026 o
transporte exige a **DC-e (Declaração de Conteúdo Eletrônica)**. O botão "Emitir DC-e" apenas abria
o painel do ML (stub 501 → `window.open`), exigindo sessão logada. O Mercado Livre **não expõe API**
de emissão de DC-e (verificado ao vivo). O contador confirmou que a **MIG pode emitir a DC-e no
perfil "Marketplace"** (por conta e ordem do vendedor CPF), sem credenciamento prévio.

## Decisão

A **MIG emite a DC-e direto na SVRS** (Ambiente Nacional, SEFAZ-PR), assinando com o **A1 do CNPJ da
MIG** (perfil Marketplace, `tpEmit=1`), reaproveitando a infra de NF-e (`services/fiscal/sefaz`).

- **Certificado central:** `PlatformCertConfig` (perfil `marketplace_dce`) — cert único da MIG,
  separado do cert-por-CMIG. Upload em `marketplace-settings/platform-certificate` (Super Admin).
- **Autorização por conta e ordem:** flag `CMIGFiscalConfig.dce_authorized` (default 0 = bloqueado).
  Sem ela, o endpoint mantém o comportamento antigo (501). Formalização = autorização no cadastro.
- **Chave (modelo 99):** `cUF AAMM CNPJ(assinante) mod serie nDC(9) tpEmis tpEmit nSiteAutoriz cDC(6)
  cDV`. Inclui `tpEmit` (diferente da NF-e) — descoberto decompondo um DACE real.
- **Assinatura:** XMLDSig SHA-1 **sem prefixo `ds:`** (a SEFAZ-PR rejeita com cStat 587) — signer
  próprio `dce_signer`.
- **SOAP:** cliente `dce_client` (mTLS reaproveitado do NF-e) com `soapAction` obrigatório e elemento
  `dceDadosMsg` / `consStatServDCe` / `enviDCe` (SOAP 1.2).
- **Remetente (emit):** CPF do vendedor + **endereço do Galpão** (as CMIGs CPF não têm endereço
  próprio); código IBGE do município resolvido por cidade+UF (`ibge_municipios`, seed da API IBGE).
- **Destinatário:** CPF/CNPJ do comprador quando houver; senão **`idOutros`** (o ML não expõe o CPF).
- **Persistência:** tabela própria `order_dce` (não reusa `invoices`). Homologação (`tpAmb=2`) força
  o nome do destinatário para "DCE EMITIDA EM AMBIENTE DE HOMOLOGACAO" (cStat 598).
- **DACE:** PDF com QR-Code gerado por `services/fiscal/dce/dace.py` (reportlab nativo);
  `GET /orders/{id}/dace.pdf` regenera do XML autorizado.
- **Ambiente:** `tpAmb=2` (homologação) enquanto `production_released`/`NFE_ENV_PROD` não estiverem
  ligados; produção com `tpAmb=1` após validação.

## Virada para o emissor de DC-e do Mercado Livre — adendo 2026-07-09 (SUPERSEDE esta ADR)

Ao ligar a emissão própria em **produção**, o handshake TLS com a SEFAZ-PR falhou
(`SefazError: TLS handshake falhou contra dce.fazenda.pr.gov.br: unable to get local issuer
certificate`): o Ubuntu não confia na raiz **ICP-Brasil "Autoridade Certificadora Raiz Brasileira
v10"** (a folha da SEFAZ encadeia por `AC SOLUTI SSL EV G4` → AC-Raiz v10) e o `NFE_ICP_CABUNDLE`
era **config morta** (declarado mas nunca carregado no `_build_ssl_context`).

Em vez de resolver credenciamento + ICP-Brasil, adotou-se o **emissor de DC-e do próprio ML**: o
botão "Emitir DC-e" abre
`https://www.mercadolivre.com.br/emissor/omni/emitir/dce/sale/SALE_ML_DCE/{platform_order_id}?source=ml&callbackWording=Vendas&callbackUrl=<lista de vendas>`
(rota real do ML, reconstruível por venda). O **ML emite a DC-e e libera a etiqueta** — sem SEFAZ,
ICP-Brasil ou certificado do nosso lado.

- **Frontend** (`OrderListView.vue`): o botão vira um link (`dceEmitterUrl`) que abre o emissor do ML.
- **Backend** (`emit_order_dce`): **neutralizado** — devolve `{ml_emitter, emitter_url}` (helper
  `_ml_dce_emitter_url`), sem tocar na SEFAZ. O fluxo da etiqueta CPF volta a instruir via
  `_DCE_PENDING_MSG`.
- **Dormente (não removido):** `services/fiscal/dce/*`, `report_dce_invoice`, `_report_dce_to_ml`,
  `_cpf_label_invoice_pending`, e as tabelas/migrations (120/121/124 já rodaram). Reversível.
- **Produção revertida:** `NFE_ENV_PROD=false` + `production_released=0` (CMIG 101).

Se um dia a emissão própria for retomada, além de reverter o acima, **corrigir** o `NFE_ICP_CABUNDLE`
(carregá-lo em `_build_ssl_context` via `load_verify_locations`) e instalar a cadeia ICP-Brasil.

## Notificação ao Mercado Livre (libera a etiqueta) — adendo 2026-07-09 (histórico; superseded)

A emissão na SVRS autoriza a DC-e, mas o **ML não libera a etiqueta** enquanto o shipment está em
`substatus=invoice_pending` — ele precisa **receber o documento fiscal**. Isso valia para NF-e
(reportada via `invoice_data`) e ficou de fora do escopo original da DC-e (o `ml_service.emit_dce`
era um stub 501). Fechado agora:

- **Report ao ML:** após a autorização (cStat 100), envia-se o `procDCe` via
  `POST /shipments/{id}/invoice_data?siteId=MLB`, `Content-Type: application/xml`, com o **XML CRU**
  (bytes UTF-8, **sem reserializar** — preserva a assinatura XMLDSig). Mesmo endpoint que recebe a
  NF-e modelo 55; aqui envia-se a Declaração de Conteúdo (modelo 99). Função
  `ml_service.report_dce_invoice`.
- **Gate de ambiente:** só DC-e de **produção** é reportada (o ML recusa homologação), decidido pela
  coluna `OrderDce.environment` da própria linha emitida — não pelo toggle global no momento do envio.
- **Idempotência:** coluna `order_dce.ml_reported_at` (migration 124) evita reenvio a cada reclique
  na etiqueta.
- **Wiring:** `orders._report_dce_to_ml` é chamado (a) best-effort no fim de `emit-dce`
  (`ml_notified`/`ml_warning` no retorno, sem desfazer a emissão se o ML falhar) e (b) no fluxo da
  etiqueta (`_cpf_label_invoice_pending`), que reporta a DC-e já autorizada e orienta o usuário a
  reclicar. Se o ML recusar o documento, a mensagem do ML propaga.
- **Toggle de produção corrigido:** `NFE_ENV_PROD` era lido em `dce_service.py` mas **não existia**
  no `Settings` (sempre `False` → produção inalcançável). Agora declarado (`config.py`), mantendo o
  gate composto `NFE_ENV_PROD` (global) **E** `production_released` (por CMIG).
- **Pendente:** smoke em **produção** — o report só dispara com `environment="production"`; a
  aceitação do **modelo 99** pelo `invoice_data` do ML precisa ser confirmada na 1ª emissão real
  (a doc antiga do ML falava só em modelo 55).

## Consequências

- **Positivas:** DC-e emitida por API, sem sessão logada no ML; DACE próprio com QR; reaproveita
  assinatura/mTLS da NF-e; gated por vendedor (`dce_authorized`) → rollout seguro. Fluxo agora
  **fecha o loop** e libera a etiqueta ML fim-a-fim (report via `invoice_data`).
- **Negativas / pendências:**
  - Endereço do Galpão precisa estar completo (cidade/UF/CEP) — pré-requisito de cadastro.
  - CPF do comprador não vem do ML → `idOutros` (poderia buscar via `billing_info` no futuro).
  - Migrations 120 (order_dce, platform_cert_configs, flags) e 121 (ibge_municipios).

## Referências
- `BACKEND/services/fiscal/dce/` (chave_dce, xml_builder_dce, dce_signer, dce_client, dce_service, dace, ibge, signer_cert)
- `BACKEND/routers/orders.py` (`emit-dce`, `dace.pdf`, `_dce_feature_ready`), `routers/marketplace_settings.py` (cert central), `routers/fiscal_config.py` (`dce_authorized`)
- `Scripts SQL/120_dce_emissao.sql`, `121_ibge_municipios.sql`
- Ajuste SINIEF 05/2021 (DC-e), Manual DC-e (Anexo I/II/III), FAQ SVRS ("emitida por Marketplace")
