# ADR-0030 — Modo de emissão de NF-e por conta de marketplace (própria × marketplace)

## Status
Aceita (2026-10-16). Emenda operacional das ADR-0015/0021/0022/0027/0028.

## Contexto
O sistema já emitia NF-e por dois caminhos desacoplados e escolhidos **manualmente** pelo
usuário (botões diferentes): (a) **própria**, direto na SEFAZ (ADR-0015/0028), e (b) **Faturador
do Mercado Livre** (ADR-0021). Não havia um ponto de decisão configurável — a escolha própria×ML
só era forçada pelo guard de rastreabilidade (ADR-0027, que bloqueia o ML) e pelo tipo de emissor
CPF→DC-e. Havia ainda um flag inerte `NFeConfig.issuer` (por método de envio) **nunca ligado** à
decisão de emissão.

O dono pediu: **em Pedidos (não-FULL), gerar a NF-e pelo sistema** quando a conta tiver certificado
+ dados de produto, configurável **por conta de marketplace** (própria × marketplace), com o
comando de emissão **roteado** por essa configuração.

Verificado com `mercado-livre-especialista`: o Faturador ML é **opt-in** (não emite sozinho para
CNPJ); e há o endpoint `POST /shipments/{id}/invoice_data?siteId=MLB` para **informar ao ML a NF-e
própria** (o ML libera etiqueta/despacho quando existe uma NF-e informada — não precisa ter sido
emitida por ele). Validado com `Consultor-Fiscal-NFE`: legítimo escolher por conta, mas o 1-clique
sem revisão e a ausência de trava de unicidade geram risco de passivo (nota duplicada/errada é
irreversível) → exige confirmação, unicidade e gate de homologação.

## Decisão
1. **Eixo por conta (SSOT):** nova coluna `marketplace_accounts.nfe_emission_mode`
   (`'marketplace'` padrão | `'own'`), **CNPJ-only** (migration 151, com CHECK). O
   `NFeConfig.issuer` **não** é usado no roteamento e seu quadro "Configurações de NF-e por CM"
   foi **aposentado na UI** (`CmigDetailView`, substituído por aviso que aponta para o novo ajuste
   por conta) — evita duas superfícies que "parecem" controlar a emissão; o CRUD backend fica inerte.
   Marcar `'own'` exige papel fiscal (ac/admin) + certificado A1 + série na `CMIGFiscalConfig`
   (falha alto, 422). CPF segue sempre DC-e própria (ADR-0017); rastreável segue forçando própria
   (ADR-0027) — o toggle não os afeta.
2. **Roteador único:** `POST /orders/{id}/emit-nfe` decide: **FULL → 400** (nota de venda é do ML,
   ADR-0010/0022); Shopee → própria + anexo; ML CPF → DC-e; ML CNPJ `own` → emissão própria 1-clique;
   ML CNPJ `marketplace` → Faturador (inalterado). O caminho da etiqueta (`_emit_nfe_for_label`)
   respeita o mesmo flag: conta `own` **não** auto-emite ML — exige a própria antes.
3. **Própria 1-clique com confirmação:** reusa os endpoints oficiais (`create-from-order` +
   `transmit`) — não duplica o núcleo fiscal e herda o mapeamento SEFAZ→HTTP. Sem `confirm` devolve
   um **resumo irretratável** (destinatário, CFOP/CST/NCM por item, totais, ambiente); com `confirm`
   transmite. **Writeback** no pedido (`nfe_status`/`nfe_key`) após autorizar (paridade com o fluxo
   ML + idempotência).
4. **Integração ML:** `ml_service.upload_own_invoice_xml` (POST `invoice_data`) informa o XML
   autorizado ao ML **em produção** (libera etiqueta). Shopee: anexa via `upload-invoice`.
5. **Travas anti-duplicação (CRITICAL fiscal):** índice funcional único
   `uq_invoice_order_sale_live` (1 pedido ↔ 1 NF-e de venda viva, qualquer origem) + guard na
   captura do Faturador (`_sync_ml_fiscal_account` ignora e põe em quarentena a nota do ML de um
   pedido que já tem NF-e própria viva) + idempotência do re-clique (já-autorizada não re-emite).
6. **Gate de homologação:** nota emitida com `production_released=false` sai em homologação (sem
   valor fiscal) → **não baixa estoque real** (`_apply_stock_on_authorization` pula `environment=homolog`),
   **não** escreve estado fiscal no pedido, não informa o ML / não anexa Shopee / não libera etiqueta;
   a UI avisa inequivocamente. O ambiente é derivado de `CMIGFiscalConfig.environment` (o mesmo que
   `sefaz_service.emitir` fixa em `inv.environment`), não de `production_released`.
7. **Anti-duplicação nos DOIS sentidos:** além do guard na captura (sentido Faturador), `_emit_own_nfe`
   bloqueia (409 claro) quando o pedido já tem NF-e de venda do Faturador viva (sentido emissão). Um
   rascunho (`draft`) não ocupa a vaga única nem suprime a captura (só nota transmitida/autorizada).

## Consequências
- Pré-requisito operacional (fora da API, sem endpoint): em cada conta CNPJ `own`, garantir no
  painel do ML que o **emissor do ML está desligado / sem emissão automática** — senão o ML pode
  gerar nota além da própria (o guard de captura protege, mas é melhor na origem).
- Validação real só em homologação/produção (DEV não fala com SEFAZ/ML). Habilitar `own` em
  produção por conta exige prova em homologação (cStat 100) + validação do contador.
- Duplicação deliberada de superfície entre própria×ML mantida (ADR-0020/0021); o roteador é o
  ponto único novo.

## Follow-ups
- Pré-voo semântico mais fundo (CFOP×idDest, DIFAL B2C inter-UF, CEST em ST) além do resumo +
  validações atuais + rejeição da SEFAZ.
- Shopee: botão one-click "emitir+anexar" na UI (hoje o backend cobre; a UI mantém emitir+anexar
  em dois passos pela borda do Invoice Issuer/CPF).
- Teste ao vivo do `POST invoice_data` (único elo confirmado por relato de ERP, não testado).
- Segregar série própria × série do Faturador por conta (evitar colisão/furos de numeração).
