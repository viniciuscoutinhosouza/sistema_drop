# Documentação do Banco de Dados — MIG ECOMMERCE / Sistema Drop

> **Banco:** Oracle ATP (Autonomous Transaction Processing)
> **Versão do schema:** v3.0 (scripts 01–22)
> **Última atualização:** Abril 2026

---

## Índice

1. [Visão Geral da Arquitetura](#1-visão-geral-da-arquitetura)
2. [Diagrama de Relacionamentos](#2-diagrama-de-relacionamentos)
3. [Módulo: Usuários e Autenticação](#3-módulo-usuários-e-autenticação)
4. [Módulo: Financeiro](#4-módulo-financeiro)
5. [Módulo: Catálogo de Produtos (PG)](#5-módulo-catálogo-de-produtos-pg)
6. [Módulo: Kits](#6-módulo-kits)
7. [Módulo: Produtos do Dropshipper (legado)](#7-módulo-produtos-do-dropshipper-legado)
8. [Módulo: Pedidos](#8-módulo-pedidos)
9. [Módulo: Contas de Marketplace](#9-módulo-contas-de-marketplace)
10. [Módulo: Devoluções](#10-módulo-devoluções)
11. [Módulo: Notificações](#11-módulo-notificações)
12. [Módulo: Webhooks](#12-módulo-webhooks)
13. [Módulo: Galpão (Warehouse)](#13-módulo-galpão-warehouse)
14. [Módulo: Gestores Operacionais (GO / UGO)](#14-módulo-gestores-operacionais-go--ugo)
15. [Módulo: CMIG — Conta MIG](#15-módulo-cmig--conta-mig)
16. [Módulo: Anúncios (Product Listings)](#16-módulo-anúncios-product-listings)
17. [Resumo de Papéis e Permissões](#17-resumo-de-papéis-e-permissões)
18. [Fluxos Principais](#18-fluxos-principais)

---

## 1. Visão Geral da Arquitetura

O sistema opera com quatro perfis de usuário principais:

| Role | Nome | Responsabilidade |
|------|------|-----------------|
| `admin` | Administrador da Plataforma | Acesso total ao sistema |
| `ugo` | Gestor Operacional (UGO) | Gerencia o Galpão, estoque PG, importa produtos |
| `ac` | Administrador de Conta (AC) | Cria CMIGs, gerencia Contas de Marketplace, publica anúncios |
| `go` | Gestor Operacional (GO) | Perfil empresa do UGO (dados CNPJ/fiscal) |

**Hierarquia organizacional:**

```
Platform (admin)
└── GO / Warehouse (UGO)
    ├── Catálogo PG (catalog_products)  ← produtos do galpão
    └── CMIG (Conta MIG do AC)
        ├── Produtos CMIG (cmig_products)
        ├── Contas de Marketplace (marketplace_accounts)
        └── Anúncios (product_listings)
```

---

## 2. Diagrama de Relacionamentos

```
users ─────────────────────────────────────────┐
  │                                             │
  ├── ac_profiles (1:1)                        │
  ├── financial_transactions (1:N)             │
  ├── notifications (1:N)                      │
  ├── refresh_tokens (1:N)                     │
  ├── goes (1:1, role=ugo)                     │
  │     └── warehouses (1:N)                   │
  │           ├── catalog_products (1:N)        │
  │           │     ├── catalog_product_images  │
  │           │     └── catalog_product_variants│
  │           └── cmigs (1:N) ──────────────────┘
  │
  ├── cmig_administrators (M:N com cmigs)
  │
  └── cmigs (owner_ac_id)
        ├── cmig_products (1:N)
        │     ├── cmig_product_images
        │     └── cmig_product_variants
        └── marketplace_accounts (1:N)
              ├── account_balances (1:1)
              ├── account_transactions (1:N)
              ├── account_administrators (M:N com users)
              ├── otp_verifications (1:N)
              └── product_listings (1:N)
                    ├── → cmig_products (FK)
                    └── → catalog_products (FK)

orders (1:N via dropshipper_id)
  └── order_items (1:N)

returns (1:N)
webhook_events (standalone)
```

---

## 3. Módulo: Usuários e Autenticação

### Tabela: `users`
**Propósito:** Tabela central de todos os usuários do sistema. Um único registro representa qualquer perfil (admin, ugo, ac, go).

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `id` | NUMBER IDENTITY | PK | Identificador único |
| `email` | VARCHAR2(255) | Sim | Login do usuário (único) |
| `password_hash` | VARCHAR2(255) | Sim | Hash bcrypt da senha |
| `role` | VARCHAR2(20) | Sim | Papel: `ugo`, `ac`, `admin`, `go` |
| `full_name` | VARCHAR2(255) | Sim | Nome completo |
| `whatsapp` | VARCHAR2(20) | Não | Número WhatsApp |
| `cpf_cnpj` | VARCHAR2(18) | Não | CPF ou CNPJ (único) |
| `is_active` | NUMBER(1) | Sim | 1 = ativo, 0 = bloqueado |
| `dark_mode` | NUMBER(1) | Não | Preferência de tema |
| `warehouse_id` | NUMBER | Não | FK → `warehouses` (preenchido para UGO) |
| `go_id` | NUMBER | Não | FK → `goes` (empresa do UGO) |
| `created_at` | TIMESTAMP TZ | Auto | Data de criação |
| `updated_at` | TIMESTAMP TZ | Auto | Data da última atualização (trigger) |

**Relacionamentos:**
- Um usuário `role=ugo` possui `warehouse_id` preenchido → gerencia um galpão
- Um usuário `role=ac` administra CMIGs via `cmig_administrators`
- Um usuário `role=ac` pode co-administrar Contas de Marketplace via `account_administrators`

---

### Tabela: `access_plans`
**Propósito:** Define os planos de assinatura disponíveis para o AC. O faturamento é baseado no número de Contas de Marketplace ativas.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | NUMBER IDENTITY | PK |
| `name` | VARCHAR2(100) | Nome do plano (Ex: "Starter", "Pro") |
| `max_accounts` | NUMBER | Máximo de Contas de Marketplace; -1 = ilimitado |
| `monthly_price` | NUMBER(10,2) | Preço mensal em R$ |
| `is_active` | NUMBER(1) | 1 = plano disponível para venda |
| `created_at` | TIMESTAMP TZ | Data de criação |

**Planos padrão cadastrados:**
- Starter: 3 contas / R$ 99,90
- Pro: 10 contas / R$ 199,90
- Enterprise: ilimitado / R$ 399,90

---

### Tabela: `ac_profiles`
**Propósito:** Perfil estendido do AC com endereço e assinatura ativa. Relação 1:1 com `users`.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | NUMBER IDENTITY | PK |
| `user_id` | NUMBER | FK → `users` (único) |
| `zip_code` | VARCHAR2(9) | CEP |
| `street` | VARCHAR2(255) | Logradouro |
| `address_number` | VARCHAR2(20) | Número |
| `complement` | VARCHAR2(100) | Complemento |
| `neighborhood` | VARCHAR2(100) | Bairro |
| `city` | VARCHAR2(100) | Cidade |
| `state` | VARCHAR2(2) | UF |
| `plan_id` | NUMBER | FK → `access_plans` (plano atual) |
| `subscription_status` | VARCHAR2(20) | `active`, `overdue`, `suspended` |
| `subscription_due_date` | DATE | Vencimento da assinatura |

---

### Tabela: `ac_subscriptions`
**Propósito:** Histórico de períodos de assinatura do AC. Cada renovação ou troca de plano cria um novo registro.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | NUMBER IDENTITY | PK |
| `profile_id` | NUMBER | FK → `ac_profiles` |
| `plan_id` | NUMBER | FK → `access_plans` |
| `status` | VARCHAR2(20) | `active`, `overdue`, `cancelled` |
| `period_start` | DATE | Início do período |
| `period_end` | DATE | Fim do período |
| `created_at` | TIMESTAMP TZ | Data de criação |

---

### Tabela: `refresh_tokens`
**Propósito:** Armazena tokens de renovação JWT. Permite logout em todos os dispositivos (revogação) e renovação silenciosa de sessão.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | NUMBER IDENTITY | PK |
| `user_id` | NUMBER | FK → `users` (cascade delete) |
| `token` | VARCHAR2(500) | Token único (UUID ou JWT) |
| `expires_at` | TIMESTAMP TZ | Expiração (30 dias padrão) |
| `revoked` | NUMBER(1) | 1 = revogado (logout) |
| `created_at` | TIMESTAMP TZ | Data de emissão |

---

## 4. Módulo: Financeiro

### Tabela: `financial_transactions`
**Propósito:** Extrato financeiro do AC/Dropshipper na plataforma MIG. Cada crédito ou débito gera um registro com saldo anterior e posterior (auditoria completa).

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | NUMBER IDENTITY | PK |
| `dropshipper_id` | NUMBER | FK → `users` (o AC dono da transação) |
| `type` | VARCHAR2(20) | `credit` = entrada, `debit` = saída |
| `amount` | NUMBER(15,2) | Valor em R$ |
| `description` | VARCHAR2(500) | Texto explicativo |
| `reference_type` | VARCHAR2(50) | Tipo da origem: `order`, `pix_deposit`, `subscription`, `return` |
| `reference_id` | NUMBER | ID do registro de origem (ex: order.id) |
| `balance_before` | NUMBER(15,2) | Saldo antes da transação |
| `balance_after` | NUMBER(15,2) | Saldo após a transação |
| `pix_key` | VARCHAR2(255) | Chave PIX (para depósitos/saques) |
| `pix_txid` | VARCHAR2(255) | ID da transação PIX |
| `status` | VARCHAR2(20) | `pending`, `completed`, `failed`, `reversed` |
| `created_at` | TIMESTAMP TZ | Data da transação |

**Quando é gerada uma transação:**
- `debit`: ao fechar um pedido (produto_cost + platform_fee + shipping_cost debitados)
- `credit`: ao receber depósito PIX; ao estornar uma devolução
- `debit`: cobrança de assinatura mensal

---

## 5. Módulo: Catálogo de Produtos (PG)

> **PG = Produto Geral.** Catálogo master do Galpão (UGO). Todos os produtos físicos armazenados são registrados aqui.

### Tabela: `categories`
**Propósito:** Árvore hierárquica de categorias de produto. Permite subcategorias (auto-referência). Armazena também os IDs de categoria do Mercado Livre e Shopee para mapeamento direto na publicação.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | NUMBER IDENTITY | PK |
| `name` | VARCHAR2(200) | Nome da categoria |
| `parent_id` | NUMBER | FK → `categories` (própria tabela; NULL = raiz) |
| `ml_category_id` | VARCHAR2(50) | ID correspondente no Mercado Livre (ex: `MLB1051`) |
| `shopee_category_id` | NUMBER | ID correspondente na Shopee |

**Exemplo de hierarquia:**
```
Moda (id=1, parent=null)
  └── Calçados (id=2, parent=1)
        └── Tênis Masculino (id=3, parent=2, ml_category_id=MLB1051)
```

---

### Tabela: `catalog_products`
**Propósito:** Produto físico cadastrado no Galpão. É o "produto mestre" da plataforma. Um produto PG pode originar múltiplos Produtos CMIG e múltiplos anúncios.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | NUMBER IDENTITY | PK |
| `warehouse_id` | NUMBER | FK → `warehouses` (galpão proprietário) |
| `sku` | VARCHAR2(100) | SKU único global |
| `title` | VARCHAR2(500) | Título do produto |
| `description` | CLOB | Descrição detalhada |
| `cost_price` | NUMBER(15,2) | Custo de aquisição (R$) |
| `suggested_price` | NUMBER(15,2) | Preço sugerido de venda |
| `weight_kg` | NUMBER(8,3) | Peso em kg (para frete) |
| `height_cm` | NUMBER(8,2) | Altura em cm |
| `width_cm` | NUMBER(8,2) | Largura em cm |
| `length_cm` | NUMBER(8,2) | Comprimento em cm |
| `ncm` | VARCHAR2(10) | Código NCM fiscal (8 dígitos) |
| `cest` | VARCHAR2(7) | Código CEST fiscal (7 dígitos) |
| `brand` | VARCHAR2(100) | Marca |
| `model` | VARCHAR2(200) | Modelo do produto *(adicionado script 22)* |
| `ean` | VARCHAR2(14) | Código EAN/GTIN/barcode *(adicionado script 22)* |
| `origin` | NUMBER(1) | 0=Nacional, 1=Importação Direta, 2=Mercado Interno |
| `category_id` | NUMBER | FK → `categories` |
| `stock_quantity` | NUMBER | Estoque disponível no galpão |
| `is_active` | NUMBER(1) | 1 = ativo |
| `created_at` | TIMESTAMP TZ | Data de criação |
| `updated_at` | TIMESTAMP TZ | Atualizado pelo trigger |

---

### Tabela: `catalog_product_images`
**Propósito:** Imagens do produto PG. Ordenadas por `sort_order`. A imagem com `is_primary=1` é a capa.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | NUMBER IDENTITY | PK |
| `product_id` | NUMBER | FK → `catalog_products` (cascade delete) |
| `url` | VARCHAR2(1000) | URL pública da imagem |
| `sort_order` | NUMBER | Ordem de exibição (0 = primeira) |
| `is_primary` | NUMBER(1) | 1 = imagem principal/capa |

---

### Tabela: `catalog_product_variants`
**Propósito:** Variantes de um produto PG. Um tênis tamanho 38 azul e um tênis tamanho 42 preto são variantes do mesmo produto base. Cada variante tem SKU próprio, estoque independente e modificador de preço.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | NUMBER IDENTITY | PK |
| `product_id` | NUMBER | FK → `catalog_products` (cascade delete) |
| `sku` | VARCHAR2(100) | SKU único da variante |
| `variant_name` | VARCHAR2(255) | Nome descritivo (ex: "Azul Tamanho 42") |
| `color` | VARCHAR2(100) | Cor |
| `size_label` | VARCHAR2(100) | Tamanho (P/M/G/42 etc.) |
| `voltage` | VARCHAR2(50) | Voltagem (110V/220V/Bivolt) *(adicionado script 22)* |
| `stock_quantity` | NUMBER | Estoque desta variante |
| `price_modifier` | NUMBER(15,2) | Acréscimo/desconto sobre o preço base |
| `attributes_json` | VARCHAR2(2000) | Atributos extras em JSON (ex: `{"material":"algodão"}`) *(script 22)* |

> **Nota:** O campo se chama `size_label` (não `size`) porque `SIZE` é palavra reservada no Oracle.

---

## 6. Módulo: Kits

### Tabela: `kits`
**Propósito:** Agrupamento de múltiplos produtos PG vendidos juntos como um único item. Ex: "Kit Churrasco" = 3 produtos diferentes. O SKU obedece o prefixo `KITB2-` por convenção de aplicação.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | NUMBER IDENTITY | PK |
| `dropshipper_id` | NUMBER | FK → `users` (AC dono do kit) |
| `sku` | VARCHAR2(100) | SKU do kit (único por AC) |
| `title` | VARCHAR2(500) | Título do kit |
| `description` | CLOB | Descrição |
| `color` | VARCHAR2(100) | Cor do kit (se aplicável) |
| `size_label` | VARCHAR2(100) | Tamanho do kit |
| `width_cm` / `height_cm` / `length_cm` | NUMBER | Dimensões da embalagem do kit |
| `weight_kg` | NUMBER(8,3) | Peso total |
| `ncm` | VARCHAR2(10) | NCM fiscal |
| `cest` | VARCHAR2(7) | CEST fiscal |
| `origin` | NUMBER(1) | Origem fiscal |
| `category_id` | NUMBER | FK → `categories` |
| `is_active` | NUMBER(1) | 1 = ativo |
| `created_at` | TIMESTAMP TZ | Data de criação |

---

### Tabela: `kit_components`
**Propósito:** Define quais produtos (e variantes) compõem um kit e em que quantidade.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | NUMBER IDENTITY | PK |
| `kit_id` | NUMBER | FK → `kits` (cascade delete) |
| `product_id` | NUMBER | FK → `catalog_products` (produto base) |
| `variant_id` | NUMBER | FK → `catalog_product_variants` (variante específica, nullable) |
| `quantity` | NUMBER | Quantidade deste item no kit |

---

## 7. Módulo: Produtos do Dropshipper (legado)

> **Atenção:** Este módulo é do fluxo legado, anterior à introdução das CMIGs (v3). Mantido para compatibilidade com pedidos e anúncios já existentes.

### Tabela: `dropshipper_products`
**Propósito:** Anúncio personalizado criado pelo AC/Dropshipper a partir de um produto PG ou kit. Continha as configurações específicas de cada marketplace (título ML, título Shopee, preços, IDs). Substituído pelo fluxo moderno via `product_listings` + `cmig_products`.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | NUMBER IDENTITY | PK |
| `dropshipper_id` | NUMBER | FK → `users` (o AC) |
| `catalog_product_id` | NUMBER | FK → `catalog_products` (produto base, nullable) |
| `kit_id` | NUMBER | FK → `kits` (kit base, nullable) |
| `title` | VARCHAR2(500) | Título genérico |
| `title_ml` | VARCHAR2(60) | Título para o ML (máx 60 chars) |
| `title_shopee` | VARCHAR2(100) | Título para Shopee |
| `sale_price_ml` | NUMBER(15,2) | Preço no ML |
| `sale_price_shopee` | NUMBER(15,2) | Preço na Shopee |
| `ml_item_id` | VARCHAR2(100) | ID do anúncio no ML (MLB...) |
| `ml_category_id` | VARCHAR2(50) | Categoria ML |
| `ml_listing_type` | VARCHAR2(20) | Tipo de anúncio ML |
| `shopee_item_id` | NUMBER | ID do anúncio na Shopee |
| `shopee_category_id` | NUMBER | Categoria Shopee |
| `bling_product_id` | NUMBER | ID no Bling ERP |
| `status` | VARCHAR2(20) | `draft`, `active`, `paused`, `closed` |
| `created_at` / `updated_at` | TIMESTAMP TZ | Controle temporal |

---

### Tabela: `dropshipper_product_images`
**Propósito:** Imagens personalizadas do anúncio do AC (podendo diferir das imagens do PG).

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | NUMBER IDENTITY | PK |
| `dropshipper_product_id` | NUMBER | FK → `dropshipper_products` (cascade delete) |
| `url` | VARCHAR2(1000) | URL da imagem |
| `sort_order` | NUMBER | Ordem de exibição |
| `is_primary` | NUMBER(1) | 1 = imagem principal |

---

## 8. Módulo: Pedidos

### Tabela: `orders`
**Propósito:** Registra cada pedido recebido dos marketplaces (ML, Shopee) ou manualmente. Contém todo o ciclo de vida do pedido: do download até entrega ou cancelamento.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | NUMBER IDENTITY | PK |
| `dropshipper_id` | NUMBER | FK → `users` (AC responsável) |
| `integration_id` | NUMBER | FK → `marketplace_accounts` (CM que recebeu o pedido) |
| `cmig_id` | NUMBER | FK → `cmigs` (CMIG faturante) |
| `platform` | VARCHAR2(20) | `mercadolivre`, `shopee`, `manual` |
| `platform_order_id` | VARCHAR2(200) | ID do pedido no marketplace (ex: `2000000000000`) |
| `platform_order_ref` | VARCHAR2(200) | Referência visível ao comprador |
| `platform_status` | VARCHAR2(50) | Status original do marketplace (ex: `paid`, `delivered`) |
| `status` | VARCHAR2(30) | Status interno: `downloaded`, `paid`, `label_generated`, `label_printed`, `separated`, `shipped`, `cancelled`, `returned` |
| `payment_status` | VARCHAR2(20) | `pending`, `paid`, `failed` |
| `buyer_name` | VARCHAR2(255) | Nome do comprador |
| `buyer_email` | VARCHAR2(255) | E-mail do comprador |
| `buyer_document` | VARCHAR2(20) | CPF do comprador |
| `shipping_address` | CLOB | JSON com endereço completo de entrega |
| `shipping_method` | VARCHAR2(100) | Método de envio (ex: `me2`, `sedex`) |
| `tracking_code` | VARCHAR2(100) | Código de rastreio |
| `tracking_url` | VARCHAR2(500) | URL de rastreio |
| `label_url` | VARCHAR2(1000) | URL da etiqueta de envio |
| `sale_amount` | NUMBER(15,2) | Valor total da venda (quanto o comprador pagou) |
| `product_cost` | NUMBER(15,2) | Custo dos produtos ao fornecedor |
| `platform_fee` | NUMBER(15,2) | Taxa da plataforma MIG (R$ 2,00 por pedido padrão) |
| `shipping_cost` | NUMBER(15,2) | Custo do frete |
| `total_debit` | NUMBER(15,2) | Total debitado do saldo do AC = product_cost + platform_fee + shipping_cost |
| `is_hidden` | NUMBER(1) | 1 = oculto na listagem (pedidos cancelados antigos) |
| `notes` | CLOB | Observações internas |
| `paid_at` | TIMESTAMP TZ | Data do pagamento confirmado |
| `shipped_at` | TIMESTAMP TZ | Data de envio |
| `created_at` / `updated_at` | TIMESTAMP TZ | Controle temporal |

**Ciclo de vida do pedido:**
```
downloaded → paid → label_generated → label_printed → separated → shipped
                                                               ↓
                                                          (cancelled / returned)
```

---

### Tabela: `order_items`
**Propósito:** Itens de cada pedido. Um pedido pode ter múltiplos produtos. Armazena snapshot do preço e custo no momento da venda (independente de alterações futuras no catálogo).

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | NUMBER IDENTITY | PK |
| `order_id` | NUMBER | FK → `orders` (cascade delete) |
| `dropshipper_product_id` | NUMBER | FK → `dropshipper_products` (fluxo legado) |
| `catalog_product_id` | NUMBER | FK → `catalog_products` (fluxo moderno) |
| `catalog_variant_id` | NUMBER | FK → variante específica (se aplicável) |
| `sku` | VARCHAR2(100) | SKU snapshot no momento da venda |
| `title` | VARCHAR2(500) | Título snapshot no momento da venda |
| `quantity` | NUMBER | Quantidade comprada |
| `unit_price` | NUMBER(15,2) | Preço de venda unitário |
| `unit_cost` | NUMBER(15,2) | Custo unitário ao fornecedor |

---

## 9. Módulo: Contas de Marketplace

> **CM = Conta de Marketplace.** Representa uma conta real em um marketplace (ML, Shopee, Bling). Uma CMIG pode ter múltiplas CMs. Múltiplos ACs podem co-administrar a mesma CM.

### Tabela: `marketplace_accounts`
**Propósito:** Credenciais e metadados de cada conta conectada a um marketplace. Armazena tokens OAuth para chamadas à API.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | NUMBER IDENTITY | PK |
| `owner_id` | NUMBER | FK → `users` (AC criador da conta) |
| `cmig_id` | NUMBER | FK → `cmigs` (CMIG proprietária desta CM) |
| `platform` | VARCHAR2(20) | `mercadolivre`, `shopee`, `bling` |
| `description` | VARCHAR2(200) | Apelido da conta (ex: "Loja Principal") |
| `email` | VARCHAR2(255) | E-mail da conta no marketplace |
| `phone` | VARCHAR2(20) | Celular associado |
| `access_token` | VARCHAR2(2000) | Token OAuth de acesso (expira em ~6h no ML) |
| `refresh_token` | VARCHAR2(2000) | Token para renovar o access_token |
| `token_expires_at` | TIMESTAMP TZ | Expiração do access_token |
| `platform_user_id` | VARCHAR2(200) | ID do vendedor na plataforma (ex: `123456789` no ML) |
| `platform_username` | VARCHAR2(200) | Nickname/username na plataforma |
| `shop_id` | NUMBER | ID da loja (Shopee) |
| `api_key` | VARCHAR2(500) | Chave de API (Bling) |
| `is_active` | NUMBER(1) | 1 = conta ativa |
| `otp_verified` | NUMBER(1) | 1 = vínculo verificado por OTP |
| `last_sync_at` | TIMESTAMP TZ | Última sincronização de pedidos/anúncios |
| `created_at` | TIMESTAMP TZ | Data de conexão |

**Fluxo OAuth ML:**
1. AC clica "Conectar ML" → sistema gera URL de autorização
2. ML redireciona para callback com `code`
3. Backend troca `code` por `access_token` + `refresh_token`
4. Tokens armazenados aqui; renovados automaticamente quando expiram

---

### Tabela: `account_administrators`
**Propósito:** Tabela M:N — permite que múltiplos ACs co-administrem a mesma Conta de Marketplace. O `is_owner=1` identifica quem criou a conta.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | NUMBER IDENTITY | PK |
| `user_id` | NUMBER | FK → `users` (AC co-administrador) |
| `account_id` | NUMBER | FK → `marketplace_accounts` |
| `is_owner` | NUMBER(1) | 1 = proprietário (criador da conta) |
| `created_at` | TIMESTAMP TZ | Data de adição como admin |

---

### Tabela: `account_balances`
**Propósito:** Saldo operacional de cada CM (para pagar etiquetas, NFs, taxas). Relação 1:1 com `marketplace_accounts`. `balance_reserved` é o valor já comprometido em operações pendentes.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | NUMBER IDENTITY | PK |
| `account_id` | NUMBER | FK → `marketplace_accounts` (único) |
| `balance` | NUMBER(15,2) | Saldo disponível (R$) |
| `balance_reserved` | NUMBER(15,2) | Saldo reservado/bloqueado (R$) |
| `updated_at` | TIMESTAMP TZ | Última atualização |

---

### Tabela: `account_transactions`
**Propósito:** Extrato de movimentações do saldo operacional da CM. Cada crédito ou débito é registrado com saldo anterior e posterior.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | NUMBER IDENTITY | PK |
| `account_balance_id` | NUMBER | FK → `account_balances` |
| `type` | VARCHAR2(10) | `credit` ou `debit` |
| `amount` | NUMBER(15,2) | Valor em R$ |
| `description` | VARCHAR2(500) | Descrição da transação |
| `reference_type` | VARCHAR2(50) | `order`, `pix_deposit`, `label`, `nfe`, `fee` |
| `reference_id` | NUMBER | ID do registro de origem |
| `pix_key` | VARCHAR2(100) | Chave PIX utilizada |
| `pix_txid` | VARCHAR2(200) | ID da transação PIX |
| `status` | VARCHAR2(20) | `pending`, `completed`, `failed` |
| `balance_before` | NUMBER(15,2) | Saldo antes |
| `balance_after` | NUMBER(15,2) | Saldo após |
| `created_at` | TIMESTAMP TZ | Data |

---

### Tabela: `otp_verifications`
**Propósito:** Códigos OTP gerados para verificar que o AC realmente controla a conta do marketplace que está tentando vincular (anti-fraude).

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | NUMBER IDENTITY | PK |
| `account_id` | NUMBER | FK → `marketplace_accounts` |
| `code` | VARCHAR2(6) | Código de 6 dígitos |
| `channel` | VARCHAR2(10) | `email` ou `whatsapp` |
| `destination` | VARCHAR2(255) | E-mail ou número que recebeu o código |
| `is_used` | NUMBER(1) | 1 = código já utilizado |
| `expires_at` | TIMESTAMP TZ | Expiração (geralmente 10 minutos) |
| `created_at` | TIMESTAMP TZ | Data de geração |

---

## 10. Módulo: Devoluções

### Tabela: `returns`
**Propósito:** Registra devoluções de pedidos. O UGO (fornecedor) analisa a devolução e decide se aprova crédito ao AC.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | NUMBER IDENTITY | PK |
| `dropshipper_id` | NUMBER | FK → `users` (AC que solicitou devolução) |
| `order_id` | NUMBER | FK → `orders` (pedido devolvido) |
| `reason` | VARCHAR2(50) | `defeito`, `produto_errado`, `desistencia`, `outro` |
| `description` | CLOB | Descrição detalhada do problema |
| `tracking_code` | VARCHAR2(100) | Código de rastreio do retorno |
| `tracking_url` | VARCHAR2(500) | URL de rastreio |
| `carrier` | VARCHAR2(100) | Transportadora |
| `expected_date` | DATE | Data esperada de chegada ao galpão |
| `security_code` | VARCHAR2(100) | Código de segurança gerado pelo marketplace |
| `status` | VARCHAR2(20) | `analyzing`, `returned`, `rejected` |
| `supplier_notes` | CLOB | Notas do UGO ao analisar |
| `credit_amount` | NUMBER(15,2) | Valor creditado de volta ao AC (se aprovado) |
| `created_at` / `updated_at` | TIMESTAMP TZ | Controle temporal |

---

## 11. Módulo: Notificações

### Tabela: `notifications`
**Propósito:** Central de notificações do sistema. Exibidas no sino (topbar) do painel. Cada evento relevante gera uma linha aqui.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | NUMBER IDENTITY | PK |
| `dropshipper_id` | NUMBER | FK → `users` (destinatário) |
| `type` | VARCHAR2(50) | Tipo: `stock_alert`, `price_change`, `new_order`, `order_cancelled`, `return_*`, `subscription_overdue` |
| `title` | VARCHAR2(200) | Título curto (exibido na lista) |
| `body` | VARCHAR2(1000) | Corpo da notificação |
| `reference_type` | VARCHAR2(50) | Tipo do objeto relacionado: `order`, `return`, `product` |
| `reference_id` | NUMBER | ID do objeto relacionado (para link direto) |
| `is_read` | NUMBER(1) | 0 = não lida (mostra no sino), 1 = lida |
| `created_at` | TIMESTAMP TZ | Data de geração |

---

## 12. Módulo: Webhooks

### Tabela: `webhook_events`
**Propósito:** Registro de todos os eventos recebidos dos marketplaces via webhook. Garante **idempotência**: o mesmo evento processado duas vezes (por retry do marketplace) não gera duplicidade de pedidos.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | NUMBER IDENTITY | PK |
| `platform` | VARCHAR2(20) | `mercadolivre`, `shopee` |
| `event_id` | VARCHAR2(200) | ID único do evento na plataforma (ex: `o_` + order_id) |
| `event_type` | VARCHAR2(100) | Tipo do evento (ex: `orders`, `items`) |
| `payload` | CLOB | JSON completo recebido |
| `processed` | NUMBER(1) | 0 = pendente, 1 = processado |
| `error_message` | VARCHAR2(1000) | Erro se processamento falhou |
| `received_at` | TIMESTAMP TZ | Quando o webhook chegou |
| `processed_at` | TIMESTAMP TZ | Quando foi processado |

**Constraint chave:** `UNIQUE(platform, event_id)` — impede duplo processamento.

---

## 13. Módulo: Galpão (Warehouse)

### Tabela: `warehouses`
**Propósito:** Representa o galpão físico do UGO. É a entidade central que agrupa todos os produtos PG e CMIGs vinculadas. Um UGO gerencia um galpão.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | NUMBER IDENTITY | PK |
| `go_id` | NUMBER | FK → `goes` (empresa GO dona do galpão) |
| `name` | VARCHAR2(200) | Nome do galpão |
| `cnpj` | VARCHAR2(18) | CNPJ da empresa |
| `company_name` | VARCHAR2(255) | Razão social |
| `trade_name` | VARCHAR2(255) | Nome fantasia |
| `phone` / `whatsapp` | VARCHAR2(20) | Contatos |
| `email` | VARCHAR2(255) | E-mail operacional |
| `zip_code` | VARCHAR2(9) | CEP |
| `street` / `address_number` / `complement` | VARCHAR2 | Endereço |
| `neighborhood` / `city` / `state` | VARCHAR2 | Localização |
| `pix_key_type` | VARCHAR2(20) | Tipo da chave PIX: `cpf`, `cnpj`, `email`, `phone`, `random` |
| `pix_key` | VARCHAR2(255) | Chave PIX para recebimentos |
| `notes` | VARCHAR2(2000) | Observações |
| `created_at` / `updated_at` | TIMESTAMP TZ | Controle temporal |

---

## 14. Módulo: Gestores Operacionais (GO / UGO)

### Tabela: `goes`
**Propósito:** Dados da pessoa jurídica (empresa) do Gestor Operacional. Um UGO tem exatamente uma `go` (1:1 com `users`). Separa os dados da empresa dos dados de login do usuário.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | NUMBER IDENTITY | PK |
| `user_id` | NUMBER | FK → `users` (único — um user, uma empresa GO) |
| `cnpj` | VARCHAR2(18) | CNPJ único da empresa |
| `company_name` | VARCHAR2(255) | Razão social |
| `trade_name` | VARCHAR2(255) | Nome fantasia |
| `phone` | VARCHAR2(20) | Telefone |
| `email` | VARCHAR2(255) | E-mail da empresa |
| `is_active` | NUMBER(1) | 1 = ativo |
| `created_at` / `updated_at` | TIMESTAMP TZ | Controle temporal |

---

## 15. Módulo: CMIG — Conta MIG

> **CMIG = Conta MIG.** Representa o CNPJ fiscal do AC — a pessoa jurídica sob a qual o AC opera no marketplace (emite NF-e, detém as Contas de Marketplace).

### Tabela: `cmigs`
**Propósito:** Entidade fiscal do AC. Uma CMIG agrupa as Contas de Marketplace (CM) e os Produtos CMIG que o AC comercializa. Pertence a um Galpão (UGO) mas é de propriedade de um AC.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | NUMBER IDENTITY | PK |
| `owner_ac_id` | NUMBER | FK → `users` (AC proprietário) |
| `warehouse_id` | NUMBER | FK → `warehouses` (galpão operacional) |
| `cnpj` | VARCHAR2(18) | CNPJ único da CMIG |
| `company_name` | VARCHAR2(255) | Razão social |
| `trade_name` | VARCHAR2(255) | Nome fantasia |
| `email` / `phone` | VARCHAR2 | Contatos |
| `zip_code` ... `state` | VARCHAR2 | Endereço completo |
| `is_active` | NUMBER(1) | 1 = ativa |
| `created_at` / `updated_at` | TIMESTAMP TZ | Controle temporal |

---

### Tabela: `cmig_administrators`
**Propósito:** M:N — múltiplos ACs podem co-administrar a mesma CMIG. O AC que criou é `is_owner=1`.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | NUMBER IDENTITY | PK |
| `user_id` | NUMBER | FK → `users` |
| `cmig_id` | NUMBER | FK → `cmigs` |
| `is_owner` | NUMBER(1) | 1 = proprietário da CMIG |
| `created_at` | TIMESTAMP TZ | Data de adição |

---

### Tabela: `cmig_products`
**Propósito:** Catálogo de produtos específico de cada CMIG. Diferente do PG (Produto Geral do galpão), o Produto CMIG tem SKU e preço de custo próprios, podendo ou não estar vinculado a um produto PG correspondente.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | NUMBER IDENTITY | PK |
| `cmig_id` | NUMBER | FK → `cmigs` (cascade delete) |
| `sku_cmig` | VARCHAR2(100) | SKU único dentro da CMIG |
| `title` | VARCHAR2(255) | Título do produto |
| `description` | CLOB | Descrição |
| `brand` | VARCHAR2(100) | Marca |
| `model` | VARCHAR2(200) | Modelo *(adicionado script 22)* |
| `ean` | VARCHAR2(14) | Código EAN/GTIN *(adicionado script 22)* |
| `cost_price` | NUMBER(10,2) | Custo do AC para este produto |
| `stock_quantity` | NUMBER | Estoque disponível |
| `weight_kg` / `height_cm` / `width_cm` / `length_cm` | NUMBER | Dimensões para cálculo de frete |
| `ncm` | VARCHAR2(8) | NCM fiscal (8 dígitos) |
| `cest` | VARCHAR2(7) | CEST fiscal |
| `origin` | NUMBER(1) | 0=Nacional, 1=Importação Direta, 2=Mercado Interno |
| `pg_product_id` | NUMBER | FK → `catalog_products` (vínculo com PG, nullable) |
| `is_active` | NUMBER(1) | 1 = ativo |
| `created_at` / `updated_at` | TIMESTAMP TZ | Controle temporal |

**Relação com PG:**
- `pg_product_id = NULL` → produto criado independentemente pelo AC
- `pg_product_id = X` → produto CMIG importado/vinculado ao produto PG X do galpão

---

### Tabela: `cmig_product_images`
**Propósito:** Imagens dos produtos CMIG. Mesma estrutura das imagens PG.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | NUMBER IDENTITY | PK |
| `cmig_product_id` | NUMBER | FK → `cmig_products` (cascade delete) |
| `url` | VARCHAR2(1000) | URL da imagem |
| `sort_order` | NUMBER | Ordem de exibição |
| `is_primary` | NUMBER(1) | 1 = imagem principal |

---

### Tabela: `cmig_product_variants`
**Propósito:** Variantes de um produto CMIG (cor, tamanho, voltagem). Criada no script 22 para espelhar a funcionalidade das variantes PG. Cada variante tem SKU único, estoque independente e modificador de preço.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | NUMBER IDENTITY | PK |
| `cmig_product_id` | NUMBER | FK → `cmig_products` (cascade delete) |
| `sku` | VARCHAR2(100) | SKU único da variante |
| `variant_name` | VARCHAR2(255) | Nome descritivo (ex: "Azul P") |
| `color` | VARCHAR2(100) | Cor |
| `size_label` | VARCHAR2(100) | Tamanho (P/M/G/42 etc.) |
| `voltage` | VARCHAR2(50) | Voltagem (110V/220V/Bivolt) |
| `stock_quantity` | NUMBER(6) | Estoque desta variante |
| `price_modifier` | NUMBER(15,2) | Acréscimo/desconto sobre o preço base |
| `attributes_json` | VARCHAR2(2000) | Atributos extras em JSON livre |

---

### Tabela: `nfe_configs`
**Propósito:** Regras de emissão de NF-e por método de envio de uma CM. Define quem emite a nota: o marketplace (ex: ML emite NF para Mercado Envios) ou o próprio sistema MIG.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | NUMBER IDENTITY | PK |
| `cm_id` | NUMBER | FK → `marketplace_accounts` (cascade delete) |
| `shipping_method` | VARCHAR2(100) | Método de envio (ex: `me2`, `sedex`, `pac`) |
| `issuer` | VARCHAR2(20) | `marketplace` = ML emite; `system` = MIG emite |
| `notes` | VARCHAR2(500) | Observações |
| `created_at` / `updated_at` | TIMESTAMP TZ | Controle temporal |

---

## 16. Módulo: Anúncios (Product Listings)

### Tabela: `product_listings`
**Propósito:** Tabela central do fluxo moderno de anúncios. Representa um anúncio publicado (ou a publicar) em uma Conta de Marketplace. Pode estar vinculado a um Produto CMIG OU a um Produto PG OU sem vínculo (recém-importado, aguardando classificação).

Esta tabela passou por múltiplas evoluções:
- **Script 11** (original): vinculava obrigatoriamente a `dropshipper_products`
- **Script 16**: adicionou `cmig_product_id`
- **Script 19**: tornou `product_id` opcional (nullable); adicionou `catalog_product_id`; adicionou permalink e thumbnail
- **Script 20**: adicionou `permalink`
- **Script 21**: adicionou campos completos para publicação ML

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | NUMBER IDENTITY | PK |
| `product_id` | NUMBER | FK → `dropshipper_products` (legado, nullable) |
| `account_id` | NUMBER | FK → `marketplace_accounts` (CM publicadora) |
| `cmig_product_id` | NUMBER | FK → `cmig_products` (vínculo moderno, nullable) |
| `catalog_product_id` | NUMBER | FK → `catalog_products` (vínculo PG, nullable) |
| `platform_item_id` | VARCHAR2(200) | ID do anúncio no marketplace (ex: `MLB5419465712`) |
| `permalink` | VARCHAR2(1000) | URL pública do anúncio no marketplace |
| `thumbnail` | VARCHAR2(1000) | URL da foto principal (cache da importação) |
| `sale_price` | NUMBER(15,2) | Preço de venda atual |
| `title_override` | VARCHAR2(500) | Título personalizado (sobrescreve o do produto) |
| `category_id` | VARCHAR2(100) | ID da categoria no marketplace (ex: `MLB1051`) |
| `listing_type` | VARCHAR2(20) | Tipo de anúncio ML: `gold_special`, `gold_pro`, `gold_premium`, `silver`, `bronze`, `free` |
| `status` | VARCHAR2(20) | `draft`, `published`, `paused`, `error` |
| `error_message` | VARCHAR2(2000) | Mensagem de erro da publicação |
| `published_at` | TIMESTAMP TZ | Data de publicação no marketplace |
| `last_sync_at` | TIMESTAMP TZ | Última sincronização com a API do marketplace |
| `description_override` | CLOB | Descrição completa do anúncio *(script 21)* |
| `attributes_json` | VARCHAR2(4000) | Atributos da categoria em JSON (ex: `[{"id":"BRAND","value_name":"Nike"}]`) *(script 21)* |
| `available_quantity` | NUMBER(6) | Quantidade disponível para venda *(script 21)* |
| `item_condition` | VARCHAR2(20) | `new`, `used`, `not_specified` *(script 21)* |
| `warranty_type` | VARCHAR2(50) | `Garantia do fabricante`, `Garantia do vendedor`, vazio = sem garantia *(script 21)* |
| `warranty_time` | VARCHAR2(20) | Prazo: `3 meses`, `6 meses`, `12 meses`, `24 meses` etc. *(script 21)* |
| `shipping_mode` | VARCHAR2(20) | `me2` = Mercado Envios, `custom`, `not_specified` *(script 21)* |
| `free_shipping` | NUMBER(1,0) | 1 = frete grátis *(script 21)* |
| `video_id` | VARCHAR2(100) | ID do vídeo YouTube (sem URL completa) *(script 21)* |
| `created_at` / `updated_at` | TIMESTAMP TZ | Controle temporal |

**Regras de vínculo:**
| Situação | cmig_product_id | catalog_product_id | product_id |
|----------|----------------|-------------------|------------|
| Anúncio importado (sem classificar) | NULL | NULL | NULL |
| Vinculado a Produto CMIG | preenchido | NULL | NULL |
| Vinculado a Produto PG | NULL | preenchido | NULL |
| Legado (fluxo antigo) | NULL | NULL | preenchido |

**Constraint de unicidade:** `UNIQUE(account_id, platform_item_id)` — um item do marketplace só pode ter um listing por conta.

---

## 17. Resumo de Papéis e Permissões

| Operação | admin | ugo | ac | go |
|----------|-------|-----|----|----|
| Criar/editar usuários | ✓ | — | — | — |
| Gerenciar Galpão/Warehouse | ✓ | ✓ | — | — |
| Gerenciar Catálogo PG | ✓ | ✓ | — | — |
| Criar/editar CMIG | ✓ | — | ✓ | — |
| Gerenciar Produtos CMIG | ✓ | — | ✓ | — |
| Conectar Conta de Marketplace | ✓ | — | ✓ | — |
| Importar/publicar Anúncios | ✓ | — | ✓ | — |
| Visualizar Pedidos | ✓ | ✓ | ✓ | — |
| Aprovar Devoluções | ✓ | ✓ | — | — |
| Visualizar Financeiro | ✓ | — | ✓ | — |

---

## 18. Fluxos Principais

### Fluxo 1 — Cadastro de Produto e Publicação no ML

```
1. UGO cadastra produto em catalog_products
   └── adiciona imagens em catalog_product_images
   └── adiciona variantes em catalog_product_variants

2. AC cria cmig_products (ou importa do PG via pg_product_id)
   └── adiciona imagens em cmig_product_images
   └── adiciona variantes em cmig_product_variants

3. AC conecta conta ML → marketplace_accounts (OAuth)

4. AC acessa "Gestão de Anúncios" e clica "Novo Anúncio"
   └── Wizard 5 abas:
       Aba 1: seleciona cmig_product
       Aba 2: define título, preço, tipo, quantidade
       Aba 3: seleciona categoria ML → carrega attributes
       Aba 4: seleciona fotos do produto
       Aba 5: descrição, frete, garantia

5. Sistema faz POST /items na API do ML
   └── cria product_listings com platform_item_id + todos os campos
   └── faz POST /items/{id}/description (separado, conforme exigência ML)
```

---

### Fluxo 2 — Importação de Anúncios Existentes

```
1. AC clica "Importar" na página de Anúncios
2. Sistema consulta GET /users/{seller_id}/items/search (todos os statuses)
3. Para cada item: GET /items?ids=MLB1,MLB2... (bulk, 20 por vez)
4. Upsert em product_listings (atualiza se já existe, cria se novo)
5. Auto-match: compara título do anúncio com cmig_products da CMIG
   - Similaridade Jaccard > 60% → vincula automaticamente
   - Abaixo → fica com is_linked = false (badge ⚠)
6. AC pode vincular manualmente ou criar produto CMIG a partir do anúncio
```

---

### Fluxo 3 — Pedido Chegando (Webhook)

```
1. ML envia POST /webhooks/mercadolivre com payload do pedido
2. Sistema verifica webhook_events (idempotência)
3. Busca product_listings pelo platform_item_id
4. Busca cmig_products ou catalog_products vinculado
5. Cria orders + order_items
6. Cria financial_transactions (débito: product_cost + platform_fee)
7. Cria notifications para o AC ("Novo pedido!")
8. Baixa estoque de cmig_products.stock_quantity
```

---

### Fluxo 4 — Devolução

```
1. AC cria returns vinculado ao order
2. UGO analisa retorno físico no galpão
3. Se aprovado:
   └── returns.status = 'returned'
   └── returns.credit_amount = valor a restituir
   └── financial_transactions (crédito) criada para o AC
   └── Estoque incrementado em catalog_products ou cmig_products
4. Se rejeitado:
   └── returns.status = 'rejected'
   └── notifications criada para o AC explicando motivo
```

---

*Documento gerado em Abril/2026 — Sistema Drop / MIG Ecommerce v3*
