# Sistema MIG ECOMMERCE — Gestão de Contas de Marketplace

## CONTEXTO E OBJETIVO

Desenvolva um sistema web completo de gestão de contas de marketplace, chamado MIG ECOMMERCE.
O Modelo de negócio vai funcionar com B2B. Um fornecedor central disponibiliza produtos para Sellers dos Marketplaces, e oferece o serviço de gestor logístico, fazendo o serviço manual de emissão das etiquetas, notas fiscais, relatórios administrativos, gestão de estoque, etc.

O Fornecedor Principal será chamado por todo o sistema como Gestor Operacional (GO). O GO disponibilizará os produtos fisicamente em um galpão e deve criar um cadastro de Produtos Geral (PG) que será disponibilizado para os sellers dos Marketplaces venderem nas suas contas. Um Seller será chamado no sistema como Administrador de Conta (AC). Cada AC pode ter várias contas de vários Marketplaces, ou seja, um AC pode ter 2 ou mais contas no Mercado Livre + 2 ou mais contas na Shopee, etc. Uma Conta de Marketplace pode ser administrada por um ou vários AC.

O cadastro PG deve possuir todos os campos necessários para o cadastramento completo dos anúncios nos Marketplaces. Muitos campos podem ser comuns aos marketplaces, mas também podem haver campos específicos para cada marketplace. Os Usuários do Gestor Operacional (UGO) são funcionários do GO e somente estes podem fazer CRUD no cadastro PG. Somente um UGO pode cadastrar um AC. Quando um novo AC é cadastrado, ele pode vincular outros AC já cadastrados para administrar as contas que ele já administra. O AC apenas tem permissão para movimentar as contas que ele administra. Ele deve fazer as integrações com as suas contas dos Marketplaces. Para cada conta, o sistema deve baixar todos os anúncios, ativos ou inativos. Os AC não podem vincular os produtos dos seus anúncios ao cadastro PG. Apenas um UGO pode fazer esse vínculo. Apenas o administrador geral GO pode cadastrar novos UGO (usuários do Gestor Operacional), que poderão cadastrar novos AC, que poderão cadastrar integrações com novas contas.

---

## ENTIDADES DO SISTEMA

| Entidade | Nome na UI | Descrição |
|----------|-----------|-----------|
| **GO** | Gestor Operacional | Pessoa jurídica responsável pelo galpão e logística |
| **Admin** | Administrador | Usuário administrador geral do sistema; cria e gerencia Operadores Logísticos |
| **UGO** | Operador Logístico | Funcionário do GO; CRUD no PG; cadastra Gestores de Conta; vincula Anúncios ao PG |
| **AC** | Gestor de Conta | Administrador de contas de marketplace; gerencia CONTAs e Anúncios |
| **CONTA** | Conta de Marketplace | Conta em um marketplace (ML, Shopee, etc.); identificada por email + celular |
| **PG** | Produto Geral | Catálogo de produtos físicos do galpão; gerenciado exclusivamente por UGO |
| **Anúncio** | Anúncio | Listing baixado de uma CONTA; vinculado ao PG somente por UGO |

---

## HIERARQUIA DE PERMISSÕES

```
Admin (Administrador)
 └── cria e gerencia UGOs (Operadores Logísticos)
      └── UGO (Operador Logístico)
           ├── CRUD completo no PG (Produto Geral)
           ├── cadastra novos ACs (Gestores de Conta)
           └── vincula Anúncio → PG
                └── AC (Gestor de Conta) — cadastrado por UGO
                     ├── cria/vincula CONTAS de marketplace (com verificação OTP)
                     ├── adiciona outros ACs para co-administrar suas CONTAs
                     ├── baixa e gerencia Anúncios das suas CONTAs
                     └── NÃO pode vincular Anúncios ao PG
```

**Regras de co-administração de CONTA:**
- Uma CONTA pode ter N Gestores de Conta (AC) administrando-a simultaneamente
- O AC que criou a CONTA pode adicionar outros ACs já cadastrados no sistema
- Cada AC vê apenas as CONTAs que administra

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
│       ├── views/        (telas por perfil: admin / ugo / ac)
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

O sistema suporta múltiplos Gestores de Conta (AC) com dados isolados por CONTA:
- Cada AC gerencia apenas as CONTAs que administra
- Cada CONTA possui saldo financeiro próprio
- Cada CONTA possui seus próprios Anúncios, Pedidos e Extrato
- O PG (Produto Geral) é compartilhado — todos os ACs visualizam, nenhum edita

---

## MÓDULOS A DESENVOLVER

---

### 1. AUTENTICAÇÃO E GESTÃO DE USUÁRIOS

**Perfis do sistema:**

| Perfil | Nome na UI | Criado por | Pode criar |
|--------|-----------|-----------|-----------|
| `admin` | Administrador | Inicial do sistema | Operadores Logísticos |
| `ugo` | Operador Logístico | Admin | Gestores de Conta |
| `ac` | Gestor de Conta | Operador Logístico | — |

**Cadastro de Operador Logístico (UGO) — feito pelo Admin:**
- Nome completo
- E-mail (único no sistema)
- WhatsApp
- Senha inicial (gerada pelo sistema ou definida pelo Admin)

**Cadastro de Gestor de Conta (AC) — feito por UGO:**
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

**Co-administração de CONTA:**
- AC autenticado pode adicionar outro AC (já cadastrado) para co-administrar uma CONTA sua
- Vínculo confirmado via e-mail ou WhatsApp do AC convidado

---

### 2. DASHBOARD

**Dashboard — Operador Logístico (UGO):**
- Total de produtos no PG (com estoque zerado em destaque)
- Total de Anúncios sem vínculo ao PG
- Total de Gestores de Conta ativos
- Total de CONTAs ativas no sistema
- Lista dos últimos 8 produtos cadastrados no PG

**Dashboard — Gestor de Conta (AC):**
- Cards de KPIs por CONTA administrada:
  - Pedidos do mês e variação em relação ao mês anterior
  - Pedidos para processar (quantidade) com link para listagem filtrada
  - Pedidos cancelados (quantidade)
  - Saldo atual da CONTA
- Barra superior (topbar):
  - Selector de CONTA ativa (quando administra mais de uma)
  - Notificações com badge contador
  - Toggle modo escuro/claro
  - Menu do usuário (avatar, nome, Perfil, Alterar Senha, Sair)

---

### 3. PG — PRODUTO GERAL

**Acesso:** exclusivo de UGO (CRUD completo). AC apenas visualiza.

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
- SKU (obrigatório, único)
- EAN/GTIN + botão "Gerador de EAN"
- Marca
- Estoque (número)
- URL YouTube (vídeo do produto)

*Seção DIMENSÕES (cálculo de frete):*
- Peso (kg)
- Altura, Largura, Comprimento (em metros)

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

### 4. CONTAS DE MARKETPLACE

**Conceito:** Uma CONTA representa uma conta em um marketplace (ML, Shopee, etc.). Cada CONTA é identificada de forma única pela combinação de `platform + email + celular`. Uma CONTA pode ser co-administrada por múltiplos ACs.

**Listagem de CONTAs:**
- Filtros: Marketplace, Status (ativo/inativo), AC administrador
- Tabela: Id | Marketplace (ícone) | Descrição | E-mail da conta | Status | Último Sync | Ações

**Criar/Vincular Nova CONTA:**
- Select de marketplace: Mercado Livre / Shopee
- Descrição interna (apelido para identificação)
- E-mail da conta no marketplace
- Celular da conta no marketplace
- Sistema verifica se já existe CONTA com mesmo `platform + email + celular` — bloqueia duplicata
- **Verificação OTP**: envia código de 6 dígitos para e-mail e/ou WhatsApp cadastrado na conta
- Após confirmação OTP: redireciona para fluxo OAuth do marketplace

**Adicionar Co-administrador:**
- Campo de busca de AC (por nome ou e-mail) — somente ACs já cadastrados no sistema
- Confirmação enviada para o AC convidado por e-mail/WhatsApp

**Sincronização automática:**
- Scheduler: a cada N minutos, sincronizar novos pedidos de cada CONTA ativa
- Atualizar estoque dos Anúncios vinculados ao PG quando estoque PG mudar
- Registrar timestamp de último sincronismo por CONTA

---

### 5. ANÚNCIOS (LISTINGS)

**Conceito:** Anúncios são os listings de produtos baixados das CONTAs dos marketplaces. O AC pode visualizá-los e gerenciá-los. Apenas o UGO pode vincular um Anúncio a um PG.

**Download automático:**
- Ao autenticar uma CONTA via OAuth, o sistema baixa todos os anúncios (ativos e inativos)
- Sincronização periódica adiciona novos anúncios e atualiza status

**Listagem de Anúncios:**
- Filtros: CONTA, Marketplace, Status (ativo/inativo), Vinculado ao PG (Sim/Não/Todos)
- Tabela: Id | Marketplace | CONTA | Foto | Título | Item ID | Status | PG Vinculado | Ações

**Ações do AC sobre Anúncios:**
- Visualizar detalhes
- Sincronizar manualmente

**Ações do UGO sobre Anúncios:**
- Vincular Anúncio → PG (select de produto do catálogo PG)
- Desvincular

**Após vínculo:**
- Sistema passa a gerenciar o estoque do anúncio conforme o PG vinculado
- Atualizações de preço sugerido do PG são notificadas ao AC

---

### 6. PLANOS DE ACESSO (AC)

**Cobrança:** a assinatura do AC é baseada **exclusivamente** na quantidade de CONTAs de marketplace ativas.

**Estrutura de Tiers (configurável pelo Admin):**
- Cada tier define: nome, nº máximo de CONTAs, valor mensal
- Exemplos: Starter (até 3 CONTAs), Pro (até 10 CONTAs), Enterprise (ilimitado)

**Gestão pelo Admin/UGO:**
- CRUD de tiers de planos
- Atribuição de plano ao AC no momento do cadastro
- Upgrade/downgrade de plano do AC
- Histórico de mudanças de plano

**Controle de acesso:**
- Se AC atingiu o limite de CONTAs do plano: bloqueio de criar/vincular nova CONTA
- Se mensalidade vencida: bloqueio de acesso ao sistema com mensagem explicativa

---

### 7. MÓDULO FINANCEIRO

**Dupla camada de cobrança:**

#### Camada 1 — Assinatura do AC (Plano de Acesso)
- Mensalidade baseada no número de CONTAs ativas
- Gerada automaticamente no início de cada período
- Registrada em `ac_subscriptions`
- Status: pendente / pago / vencido

#### Camada 2 — Saldo por CONTA (Conta Corrente Operacional)
Cada CONTA possui sua própria conta corrente virtual para os serviços operacionais do GO (etiquetas, notas fiscais, taxas):

**Tela Financeiro da CONTA:**
- Selector de CONTA (quando AC administra mais de uma)
- Saldo atual da CONTA em destaque
- Botão "+ Adicionar crédito via PIX" → modal com:
  - Valor a adicionar
  - Chave PIX do GO exibida
  - Campo para informar o código/txid do PIX realizado
- Filtros: Tipo (Entrada/Saída), Data Início, Data Fim
- Tabela extrato:
  - Id | Descrição | Valor (verde=entrada, vermelho=saída) | Status | Data/Hora
  - Paginação server-side
- Saldo nunca pode ficar negativo (bloqueio de operação se saldo insuficiente)

---

### 8. MÓDULO DE PEDIDOS

**Fonte:** sincronizados automaticamente por CONTA (Mercado Livre, Shopee)

**Tabela "Todos os Pedidos" (por CONTA):**

*Cards de resumo:*
- Gráfico de barras: últimos 7 dias (pedidos por dia) — Chart.js
- Pedidos nos últimos 30 dias (quantidade + valor)
- Pedidos hoje (quantidade + valor)

*Filtros:*
- Ref Order (ID do pedido no marketplace)
- Nome do Cliente
- Data Início / Data Fim
- Status de Pagamento: Pago / Não Pago / Todos
- Cancelado: Sim / Não / Todos
- CONTA (selector das CONTAs do AC)

*Colunas da tabela:*
- Id interno
- Status Operacional (pipeline de fulfillment)
- Marketplace + Ref Order + Status do canal
- Método de envio + Código de rastreio
- Produtos (foto, nome, qtd × valor)
- Cliente
- Total (R$)
- Data/Hora
- Ações

*Pipeline "Status Operacional":*
1. **Baixou Pedido** (automático)
2. **Pedido Pago** (débito no saldo da CONTA)
3. **Etiqueta Gerada** (link para download)
4. **Etiqueta Impressa**
5. **Pedido Separado**
6. **Pedido Enviado**

*Ações por pedido:*
- **Pagar** → debita saldo da CONTA e solicita etiqueta ao GO
- **Ocultar** → arquivar pedido da listagem
- **Ajuda** → abre chamado de suporte
- **Emitir NF-e Entrada / Saída**
- **Ver etiqueta** → abre PDF/URL

---

### 9. MÓDULO DE KITS

**Conceito:** Kit é um produto composto por múltiplos SKUs do PG, vendido como um único item. O estoque do kit é calculado como o menor estoque entre seus componentes dividido pela quantidade necessária de cada um.

**Listagem de Kits:**
- Cards visuais: foto, SKU (prefixo KITB2-), nome, estoque calculado, composição
- Ações: Publicar / Duplicar / Excluir

**Formulário de Criação/Edição:**
- SKU (gerado com prefixo KITB2-)
- Nome, Categoria, Descrição
- Estoque (calculado automaticamente — somente leitura)
- Dimensões (Largura, Altura, Comprimento, Peso)
- NCM, CEST, Origem
- Componentes: tabela com SKU do PG | Foto | Produto | Valor | Quantidade (editável) | Remover

---

### 10. MÓDULO DE DEVOLUÇÃO

**Fluxo:**
1. AC gerencia a devolução com o marketplace
2. Orienta o cliente a enviar o produto para o galpão do GO
3. Registra a devolução no sistema com dados de rastreio
4. GO recebe, inspeciona e aprova → crédito é adicionado ao saldo da CONTA

**Tela de Devolução:**
- Banner com instruções e endereço do galpão
- Botão "+ Nova Devolução"
- Tabela: Id | Status | Motivo | Pedido | Rastreio | Ações

**Formulário Nova Devolução:**
- ID do Pedido (select com autocomplete)
- Motivo: Produto com defeito / Produto errado / Desistência / Outro
- Descrição do ocorrido
- Código de Rastreio + URL + Transportadora
- Data prevista de chegada
- Código de segurança da devolução (marketplace)

---

### 11. MÓDULO DE NOTIFICAÇÕES

**Notificações geradas automaticamente:**
- **Saldo baixo:** quando saldo da CONTA cai abaixo do threshold configurado
- **Estoque zerado no PG:** produto vinculado a anúncio com estoque = 0
- **Anúncio sem vínculo:** anúncio baixado da CONTA sem PG vinculado
- **Pedido sem ação:** pedido sem movimentação há mais de N horas
- **Plano vencendo:** mensalidade do AC vence em X dias
- **Crédito aprovado:** PIX verificado e crédito adicionado ao saldo da CONTA
- **Devolução aprovada:** GO aprovou devolução e creditou valor na CONTA

---

## ESTRUTURA DE BANCO DE DADOS — ALTERAÇÕES E NOVAS TABELAS

### Alterações em tabelas existentes

| Tabela | Tipo | Descrição |
|--------|------|-----------|
| `users.role` | ALTER | Enum atualizado: `supplier→ugo`, `dropshipper→ac` |
| `dropshipper_profiles` | ALTER | Renomear para `ac_profiles`; substituir campos de saldo por campos de plano |

### Novas tabelas

| Tabela | Descrição |
|--------|-----------|
| `marketplace_accounts` | CONTA: platform, email, phone, oauth tokens, status — unique(platform, email, phone) |
| `account_administrators` | Many-to-many: AC ↔ CONTA (quem administra o quê) |
| `account_balances` | Saldo corrente por CONTA (substitui saldo em dropshipper_profiles) |
| `account_transactions` | Extrato financeiro por CONTA (crédito PIX, débito por pedido) |
| `access_plans` | Tiers de planos para AC (nome, max_contas, valor_mensal) |
| `ac_subscriptions` | Assinaturas dos ACs (plano, período, status: ativo/vencido) |
| `otp_verifications` | Códigos OTP para verificação de vínculo de CONTA |

### Tabelas sem alteração estrutural (apenas conceitual)

| Tabela | Conceito antigo | Conceito novo |
|--------|----------------|---------------|
| `catalog_products` | Catálogo do fornecedor | **PG – Produto Geral** |
| `product_listings` | Listings do dropshipper | **Anúncios** (FK atualizada para `marketplace_accounts`) |
| `orders` | Pedidos do dropshipper | Pedidos da **CONTA** (FK atualizada) |
