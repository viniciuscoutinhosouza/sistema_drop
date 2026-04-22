# Sistema MIG ECOMMERCE — Gestão de Contas de Marketplace

## CONTEXTO E OBJETIVO

Sistema web completo de gestão de contas de marketplace chamado MIG ECOMMERCE, modelo B2B multi-tenant. Múltiplas empresas GO (Gestores Operacionais) independentes utilizam a mesma plataforma, cada uma operando seus Galpões e atendendo seus clientes AC (Gestores de Conta).

O fluxo operacional: GO mantém produtos físicos no Galpão (catálogo PG). O AC é cliente do Galpão, possui CMIGs (CNPJs) que agrupam suas Contas Marketplace (CM). Os Anúncios publicados nas CMs precisam estar vinculados a Produtos CMIG ou PG para que pedidos, estoque e NF-e sejam gerenciados pelo sistema.

---

## ENTIDADES DO SISTEMA

| Entidade | Nome na UI | Descrição |
|---|---|---|
| **SuperAdmin** | Super Administrador | `vinicius@madeingroup.com.br`; acesso irrestrito a todo o sistema e todos os GOs |
| **GO** | Gestor Operacional | Empresa/pessoa jurídica dona de um ou mais Galpões; role `go` |
| **Galpão** | Galpão | Armazém físico gerenciado por 1 GO; contém PG, UGOs e ACs |
| **UGO** | Operador Logístico | Funcionário do GO; vinculado a 1 Galpão; CRUD no PG; cadastra ACs; acessa qualquer CMIG ou CM do seu Galpão |
| **AC** | Gestor de Conta | Cliente do Galpão; gerencia CMIGs e CMs próprias ou de terceiros |
| **CMIG** | Conta MIG | Representa um CNPJ físico do AC; gerencia múltiplas CMs, estoque e NF-e |
| **CM** | Conta Marketplace | Conta em um marketplace (ML, Shopee, etc.); vinculada a 1 CMIG |
| **PG** | Produto Geral | Catálogo de produtos físicos do Galpão; gerenciado exclusivamente por UGO |
| **Produto CMIG** | Produto CMIG | Produto específico de uma CMIG; identificado por SKU CMIG; estoque independente do PG |
| **Anúncio** | Anúncio | Listing em uma CM; obrigatoriamente vinculado a um Produto CMIG ou PG |

---

## HIERARQUIA DE PERMISSÕES

```
SuperAdmin (vinicius@madeingroup.com.br)
 └── cria e gerencia GOs (N empresas distintas)
      └── GO (Gestor Operacional — role: go)
           ├── cria e gerencia seus Galpões
           └── Galpão
                ├── UGO (Operador Logístico — role: ugo, vinculado a 1 Galpão)
                │    ├── CRUD completo no PG do seu Galpão
                │    ├── cadastra novos ACs
                │    ├── visualiza e acessa qualquer CMIG ou CM do seu Galpão
                │    ├── vincula Anúncio → Produto CMIG ou PG
                │    └── importa Produto CMIG → PG (um a um, manualmente)
                │
                └── AC (Gestor de Conta — role: ac, cliente do Galpão)
                     ├── cria e gerencia suas CMIGs
                     │    ├── cadastra Produtos CMIG
                     │    ├── vincula Produto CMIG → PG existente (similaridade)
                     │    └── gerencia CMs (Contas Marketplace)
                     │         └── Anúncios (vinculados a Produto CMIG ou PG)
                     └── co-administra CMIGs/CMs de outros ACs (se convidado)
```

**Isolamento de dados:**
- AC só vê CMIGs/CMs que administra
- UGO só acessa CMIGs/CMs do seu Galpão
- GO só acessa dados dos seus Galpões
- SuperAdmin acessa tudo

---

## Stack Tecnológico do API BACKEND

- **Framework Web:** FastAPI
- **ORM:** SQLAlchemy
- **Banco de Dados:** Oracle ATP (Autonomous Transaction Processing)
- **Driver Oracle:** oracledb (python-oracledb)
- **Autenticação:** JWT (JSON Web Tokens)
- **Hash de Senhas:** bcrypt (via passlib)
- **Validação de Dados:** Pydantic (schemas)
- **CORS:** FastAPI CORSMiddleware

## Stack Tecnológico do FRONTEND

### Framework e Build
- **Vue 3.4.0** — Framework JavaScript progressivo
- **Vite 4.5.0** — Build tool e dev server
- **Vue Router 4.5.1** — Roteamento oficial do Vue

### Comunicação e Tempo Real
- **Axios 1.3.4** — Cliente HTTP para chamadas API
- **Socket.io-client 4.8.1** — WebSocket para comunicação em tempo real

### UI e Estilos
- **Bootstrap 5.3.8** — Framework CSS
- **Admin LTE 3.2.0** — Template administrativo
- **FontAwesome 6.7.2** — Biblioteca de ícones
- **jQuery 3.7.1** — Dependência do Admin LTE

### Utilitários
- **date-fns 4.1.0** — Manipulação de datas
- **vuedraggable 4.1.0** — Drag and drop
- **xlsx** (SheetJS 0.20.3) — Manipulação de planilhas Excel

### DevTools
- **@vitejs/plugin-vue 4.6.2** — Plugin Vite para Vue
- **husky 9.1.7** — Git hooks

---

## ESTRUTURA DE DIRETÓRIOS

```
SISTEMA_DROP
├── BACKEND
│   ├── routers/          (endpoints por módulo)
│   ├── models/           (entidades ORM)
│   ├── schemas/          (validação Pydantic)
│   ├── services/         (lógica de negócio e integrações ML/Shopee)
│   └── tasks/            (scheduler de sincronização)
├── FRONTEND
│   └── src/
│       ├── views/        (telas por perfil: admin / go / ugo / ac)
│       ├── components/   (componentes reutilizáveis)
│       ├── stores/       (estado global Pinia)
│       └── router/       (rotas com guards por perfil)
├── DOCs
│   ├── Backend/          (documentação MD do Backend)
│   └── Frontend/         (documentação MD do Frontend)
├── Scripts SQL           (scripts de criação e migração do banco)
└── Scripts FIX           (scripts de correção pontuais)
```

---

## ARQUITETURA MULTI-TENANT

```
SuperAdmin
 └── GO (N empresas distintas)
      └── Galpão (N por GO)
           ├── PG (catálogo de produtos por Galpão)
           ├── UGOs (funcionários do Galpão)
           └── ACs (clientes do Galpão)
                └── CMIG (CNPJ do AC — N por AC)
                     ├── Produtos CMIG (catálogo próprio)
                     └── CM (conta marketplace — N por CMIG)
                          └── Anúncios
```

---

## MÓDULOS A DESENVOLVER

---

### 1. AUTENTICAÇÃO E GESTÃO DE USUÁRIOS

**Perfis do sistema:**

| Perfil | Nome na UI | Criado por | Pode criar |
|---|---|---|---|
| `admin` | Super Administrador | Seed inicial (`vinicius@madeingroup.com.br`) | GOs |
| `go` | Gestor Operacional | Admin | UGOs, Galpões |
| `ugo` | Operador Logístico | GO (pelo painel do Galpão) | ACs |
| `ac` | Gestor de Conta | UGO | — |

**Cadastro de GO — feito pelo Admin:**
- Nome completo / Razão Social
- CNPJ
- E-mail (único no sistema — conta de acesso)
- WhatsApp
- Senha inicial

**Cadastro de UGO — feito pelo GO:**
- Nome completo
- E-mail (único no sistema)
- WhatsApp
- Galpão ao qual será vinculado
- Senha inicial

**Cadastro de AC — feito por UGO:**
- Nome completo
- E-mail (único no sistema)
- WhatsApp
- Tipo de pessoa: Física (CPF) ou Jurídica (CNPJ)
- Documento (CPF/CNPJ com validação e máscara)
- Endereço completo (CEP com auto-preenchimento via ViaCEP)
- Plano de acesso (tier selecionado pelo UGO no ato do cadastro)

**Funcionalidades de conta (todos os perfis):**
- Login/Logout com sessão segura (JWT + Refresh Token)
- Alteração de senha
- Perfil editável
- Modo escuro/claro (persistido em localStorage)
- Bloqueio de acesso quando plano vencido (apenas AC)

---

### 2. DASHBOARD

**Dashboard — Super Admin / GO:**
- Total de GOs ativos (admin) / Total de Galpões (go)
- Total de UGOs ativos
- Total de ACs ativos
- Total de CMIGs ativas
- Total de CMs ativas
- Anúncios sem vínculo no sistema

**Dashboard — Operador Logístico (UGO):**
- Total de produtos no PG (com estoque zerado em destaque)
- Total de Anúncios sem vínculo ao PG ou Produto CMIG
- Total de Gestores de Conta (AC) ativos no Galpão
- Total de CMIGs ativas no Galpão
- Total de CMs ativas no Galpão
- Lista dos últimos 8 produtos cadastrados no PG

**Dashboard — Gestor de Conta (AC):**
- Cards de KPIs por CMIG/CM administrada:
  - Pedidos do mês e variação em relação ao mês anterior
  - Pedidos para processar com link para listagem filtrada
  - Pedidos cancelados
  - Saldo atual por CM
- Barra superior (topbar):
  - Selector de CMIG ativa
  - Selector de CM ativa (dentro da CMIG selecionada)
  - Notificações com badge contador
  - Toggle modo escuro/claro
  - Menu do usuário

---

### 3. PG — PRODUTO GERAL

**Acesso:** exclusivo de UGO (CRUD completo). AC apenas visualiza. PG pertence ao Galpão do UGO.

**Relação com Produtos CMIG:** Um PG pode estar vinculado a N Produtos CMIG (similaridade). Os estoques são sempre independentes. O vínculo serve apenas como referência para facilitar pesquisa e comparação de preços.

**Listagem de Produtos:**
- Filtros: Nome, SKU, Categoria, Estoque, Status (ativo/inativo)
- Tabela: Id | Foto | SKU | Nome | Categoria | Preço de Custo | Estoque | Status | Ações

**Formulário de Cadastro/Edição:**

*Seção NOME:*
- Nome padrão (máx. 60 caracteres — obrigatório)
- Nome para Mercado Livre (máx. 60 caracteres)
- Nome para Shopee (máx. 100 caracteres)

*Seção INFORMAÇÕES DA CATEGORIA:*
- Categoria interna (select com hierarquia)
- Categoria Shopee (select via API Shopee)
- Categoria Mercado Livre (select via API ML, suporte a seleção manual em cascata)
- Tipo de produto Mercado Livre

*Seção INFORMAÇÕES DESCRITIVAS:*
- SKU (obrigatório, único no Galpão)
- EAN/GTIN + botão "Gerador de EAN"
- Marca
- Estoque (número)
- URL YouTube (vídeo do produto)

*Seção DIMENSÕES (cálculo de frete):*
- Peso (kg)
- Altura, Largura, Comprimento (em cm)

*Seção DESCRIÇÃO:*
- Textarea rich text / HTML

*Seção VARIAÇÕES:*
- Cor
- Tamanho

*Seção INFORMAÇÕES FISCAIS:*
- NCM (8 dígitos)
- CEST (7 dígitos)
- Origem (0=Nacional, 1=Estrangeira-Importação Direta, 2=Estrangeira-Mercado Interno, etc.)

*Seção VALORES:*
- Preço de Custo (valor cobrado do AC por pedido processado)
- Preço Sugerido de Venda

*Seção IMAGENS:*
- Upload múltiplo com drag & drop
- Pré-visualização com reordenação
- Remoção individual

---

### 4. CMIG — CONTA MIG

**Conceito:** Cada CMIG representa um CNPJ físico do AC. É a entidade fiscal e operacional que agrupa as CMs (Contas Marketplace) de uma razão social. Uma CMIG pertence a 1 AC principal, mas pode ser co-administrada por outros ACs convidados.

**Listagem de CMIGs:**
- Filtros: CNPJ, Razão Social, Status
- Tabela: Id | CNPJ | Razão Social | AC Responsável | Qtd CMs | Status | Ações

**Formulário de Cadastro/Edição (AC):**
- CNPJ (único no sistema, com validação e máscara)
- Razão Social
- Nome Fantasia
- E-mail fiscal
- Telefone
- Endereço completo (CEP com auto-preenchimento via ViaCEP)

**Co-administração de CMIG:**
- AC proprietário pode convidar outros ACs cadastrados no sistema para co-administrar

**Configuração de NF-e por CM:**
- Para cada CM vinculada à CMIG, o AC pode configurar regras por método de envio:
  - Exemplo: Vendas via FULL ML → NF-e emitida pelo Marketplace (não emitir)
  - Exemplo: Vendas via Envios ML / Normal Shopee → NF-e emitida pelo sistema
- A configuração permite múltiplas regras por CM (uma por método de envio)

**Acesso UGO:** UGO do Galpão pode visualizar e editar qualquer CMIG vinculada ao seu Galpão.

---

### 5. PRODUTOS CMIG

**Conceito:** Catálogo de produtos específico de uma CMIG. Identificado por SKU CMIG. Completamente independente do PG, com estoque próprio e separado.

**Acesso:**
- AC: CRUD completo nos Produtos CMIG das suas CMIGs
- UGO: leitura e importação para PG (um a um)

**Listagem de Produtos CMIG:**
- Filtros: SKU CMIG, Nome, Status, Vinculado ao PG (Sim/Não)
- Tabela: Id | Foto | SKU CMIG | Nome | Estoque | PG Vinculado | Status | Ações

**Formulário de Cadastro/Edição:**
- SKU CMIG (obrigatório, único dentro da CMIG)
- Título
- Descrição
- Marca
- Peso (kg), Altura, Largura, Comprimento (cm)
- NCM, CEST, Origem
- Preço de Custo
- Estoque
- Fotos (upload múltiplo com drag & drop)

**Vínculo com PG (similaridade):**
- AC pode vincular um Produto CMIG a um PG já cadastrado
- O vínculo é informativo/referencial — estoques sempre independentes
- Um Produto CMIG pode estar vinculado a 0 ou 1 PG

**Importação para PG (UGO):**
- UGO pode importar um Produto CMIG para o PG do seu Galpão (um a um)
- Cria novo PG copiando os dados do Produto CMIG
- Após importação, vincula automaticamente o Produto CMIG ao PG criado

---

### 6. CM — CONTA MARKETPLACE

**Conceito:** Uma CM representa uma conta ativa em um marketplace (ML, Shopee, etc.). Cada CM é vinculada a 1 CMIG. Identificada de forma única por `platform + email + celular`.

**Listagem de CMs:**
- Filtros: Marketplace, Status, CMIG, AC administrador
- Tabela: Id | Marketplace (ícone) | CMIG | Descrição | E-mail | Status | Último Sync | Ações

**Criar/Vincular Nova CM:**
- Select de CMIG (obrigatório — CM sempre pertence a uma CMIG)
- Select de marketplace: Mercado Livre / Shopee
- Descrição interna (apelido para identificação)
- E-mail da conta no marketplace
- Celular da conta no marketplace
- Sistema verifica duplicata por `platform + email + celular`
- **Verificação OTP**: envia código de 6 dígitos para e-mail e/ou WhatsApp
- Após confirmação OTP: redireciona para fluxo OAuth do marketplace

**Adicionar Co-administrador:**
- Campo de busca de AC (por nome ou e-mail) — somente ACs já cadastrados
- Confirmação enviada para o AC convidado

**Sincronização automática:**
- Scheduler: a cada N minutos, sincronizar novos pedidos de cada CM ativa
- Atualizar estoque dos Anúncios vinculados quando estoque Produto CMIG ou PG mudar
- Registrar timestamp de último sincronismo por CM

---

### 7. ANÚNCIOS

**Conceito:** Anúncios são os listings de produtos em uma CM. Todo Anúncio deve estar vinculado a um Produto CMIG ou PG para que pedidos, estoque e NF-e sejam gerenciados.

**Criação de Anúncio em uma CM:**
- AC cria o anúncio selecionando um Produto CMIG (da CMIG dona da CM) ou um PG
- Os dados do produto (título, fotos, descrição, dimensões, NCM) são pré-preenchidos
- Vínculo é mantido e pode ser alterado posteriormente pelo AC ou UGO

**Importação de Anúncios de uma CM:**
1. Ao autenticar via OAuth, o sistema baixa todos os anúncios (ativos e inativos)
2. Sincronização periódica adiciona novos e atualiza status
3. Sistema tenta localizar produto similar automaticamente (por título/EAN) em Produtos CMIG ou PG
4. AC é notificado sobre anúncios sem vínculo
5. AC pode: a) vincular a Produto CMIG ou PG existente; b) autorizar criação de novo Produto CMIG
6. Sistema só cria novo Produto CMIG quando AC autoriza explicitamente
7. AC só pode criar produto em CMIG (nunca em PG diretamente)
8. UGO pode vincular a qualquer Produto CMIG ou PG do Galpão

**Anúncio sem vínculo:** Pode existir temporariamente. Pedidos, controle de estoque e emissão de NF-e exigem vínculo.

**Listagem de Anúncios:**
- Filtros: CMIG, CM, Marketplace, Status, Vinculado (Sim/Não/Todos)
- Tabela: Id | Marketplace | CM | CMIG | Foto | Título | Item ID | Status | Produto Vinculado | Ações

**Ações do AC:**
- Visualizar detalhes
- Vincular/desvincular produto
- Sincronizar manualmente

**Ações do UGO:**
- Vincular Anúncio → Produto CMIG ou PG
- Desvincular

---

### 8. PLANOS DE ACESSO (AC)

**Cobrança:** a assinatura do AC é baseada exclusivamente na quantidade de CMs ativas.

**Estrutura de Tiers (configurável pelo Admin/GO):**
- Cada tier define: nome, nº máximo de CMs, valor mensal
- Exemplos: Starter (até 3 CMs), Pro (até 10 CMs), Enterprise (ilimitado)

**Gestão pelo GO/UGO:**
- CRUD de tiers de planos
- Atribuição de plano ao AC no cadastro
- Upgrade/downgrade de plano
- Histórico de mudanças de plano

**Controle de acesso:**
- Se AC atingiu limite de CMs do plano: bloqueio de criar/vincular nova CM
- Se mensalidade vencida: bloqueio de acesso com mensagem explicativa

---

### 9. MÓDULO FINANCEIRO

**Dupla camada de cobrança:**

#### Camada 1 — Assinatura do AC (Plano de Acesso)
- Mensalidade baseada no número de CMs ativas
- Gerada automaticamente no início de cada período
- Status: pendente / pago / vencido

#### Camada 2 — Saldo por CM (Conta Corrente Operacional)
Cada CM possui sua própria conta corrente virtual para os serviços do GO (etiquetas, notas fiscais, taxas):

**Tela Financeiro da CM:**
- Selector de CMIG → Selector de CM
- Saldo atual em destaque
- Botão "+ Adicionar crédito via PIX" → modal com valor e chave PIX do GO
- Tabela extrato: Id | Descrição | Valor (verde=entrada, vermelho=saída) | Status | Data/Hora
- Saldo nunca pode ficar negativo

---

### 10. MÓDULO DE PEDIDOS

**Fonte:** sincronizados automaticamente por CM (Mercado Livre, Shopee)

**Tabela "Todos os Pedidos":**

*Filtros:*
- Ref Order, Nome do Cliente, Data, Status de Pagamento, Cancelado, CMIG, CM

*Colunas:*
- Id interno | Status Operacional | Marketplace + Ref Order | Envio + Rastreio | Produtos | Cliente | Total | Data | Ações

*Pipeline "Status Operacional":*
1. **Baixou Pedido** (automático)
2. **Pedido Pago** (débito no saldo da CM)
3. **Etiqueta Gerada** (link para download)
4. **Etiqueta Impressa**
5. **Pedido Separado**
6. **Pedido Enviado**

*Emissão de NF-e por pedido:*
- Sistema verifica a regra NF-e configurada na CM para o método de envio do pedido
- Se `issuer = system`: botão "Emitir NF-e" disponível no pedido
- Se `issuer = marketplace`: NF-e emitida pelo marketplace (sem ação do sistema)

---

### 11. MÓDULO DE KITS

**Conceito:** Kit é um produto composto por múltiplos SKUs do PG, vendido como um único item. O estoque do kit é calculado como o menor estoque entre seus componentes dividido pela quantidade necessária.

**Formulário:**
- SKU (prefixo KITB2-)
- Nome, Categoria, Descrição
- Estoque (calculado automaticamente)
- Dimensões, NCM, CEST, Origem
- Componentes: SKU do PG | Foto | Produto | Valor | Quantidade | Remover

---

### 12. MÓDULO DE DEVOLUÇÃO

**Fluxo:**
1. AC gerencia a devolução com o marketplace
2. Orienta o cliente a enviar o produto para o Galpão do GO
3. Registra a devolução no sistema com dados de rastreio
4. GO recebe, inspeciona e aprova → crédito adicionado ao saldo da CM

**Formulário Nova Devolução:**
- ID do Pedido (select com autocomplete)
- Motivo: Produto com defeito / Produto errado / Desistência / Outro
- Descrição do ocorrido
- Código de Rastreio + URL + Transportadora
- Data prevista de chegada
- Código de segurança da devolução (marketplace)

---

### 13. MÓDULO DE NOTIFICAÇÕES

**Notificações geradas automaticamente:**
- **Saldo baixo:** saldo da CM cai abaixo do threshold configurado
- **Estoque zerado:** Produto CMIG ou PG vinculado a anúncio com estoque = 0
- **Anúncio sem vínculo:** anúncio importado sem Produto CMIG ou PG vinculado
- **Pedido sem ação:** pedido sem movimentação há mais de N horas
- **Plano vencendo:** mensalidade do AC vence em X dias
- **Crédito aprovado:** PIX verificado e crédito adicionado ao saldo da CM
- **Devolução aprovada:** GO aprovou devolução e creditou valor na CM

---

## ESTRUTURA DE BANCO DE DADOS

### Novas tabelas

| Tabela | Descrição |
|---|---|
| `goes` | Empresas GO: user_id (FK users, role=go), cnpj, company_name, trade_name, phone, email, is_active |
| `cmigs` | Conta MIG: owner_ac_id (FK users), warehouse_id (FK warehouses), cnpj (UNIQUE), company_name, trade_name, email, phone, is_active |
| `cmig_administrators` | M:M AC ↔ CMIG: user_id FK, cmig_id FK, is_owner |
| `cmig_products` | Produtos CMIG: cmig_id FK, sku_cmig (UNIQUE), title, stock, pg_product_id (nullable FK catalog_products) |
| `cmig_product_images` | Imagens dos Produtos CMIG |
| `nfe_configs` | Regra NF-e por CM: cm_id FK, shipping_method, issuer (marketplace\|system) |

### Alterações em tabelas existentes

| Tabela | Alteração |
|---|---|
| `users` | ADD `warehouse_id` (FK warehouses, nullable — UGO); ADD `go_id` (FK goes, nullable) |
| `users.role` | Enum: adicionar valor `go` |
| `warehouses` | ADD `go_id` (FK goes, NOT NULL) |
| `marketplace_accounts` | ADD `cmig_id` (FK cmigs, nullable inicialmente) |
| `product_listings` | ADD `cmig_product_id` (FK cmig_products, nullable) |
| `orders` | ADD `cmig_id` (FK cmigs, nullable) |

### Tabelas existentes sem alteração estrutural

| Tabela | Papel no novo modelo |
|---|---|
| `catalog_products` | PG — Produto Geral do Galpão |
| `product_listings` | Anúncios (atualizada com cmig_product_id) |
| `marketplace_accounts` | CM — Conta Marketplace (atualizada com cmig_id) |
| `orders` | Pedidos da CM (atualizado com cmig_id) |
| `account_administrators` | M:M AC ↔ CM (co-administração) |
| `account_balances` | Saldo por CM |
| `account_transactions` | Extrato por CM |
| `access_plans` | Planos de acesso (tiers) |
| `ac_subscriptions` | Assinaturas dos ACs |
| `otp_verifications` | OTP para vincular CM |
