# PROMPT: Desenvolver Sistema de Gestão de Dropshipping – UnicDrop Clone

## CONTEXTO E OBJETIVO
Desenvolva um sistema web completo de gestão de dropshipping chamado MIG ECOMMERCE, com 
modelo de negócio B2B onde um fornecedor central disponibiliza produtos para dropshippers 
venderem nos marketplaces Mercado Livre e Shopee. O sistema deve automatizar todo o fluxo: 
captação de pedidos dos marketplaces → pagamento ao fornecedor → geração de etiqueta → 
rastreamento → devoluções.

---

### Stack Tecnológico do API BACKEND

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
- **Vue 3.4.0** - Framework JavaScript progressivo
- **Vite 4.5.0** - Build tool e dev server (extremamente rápido)
- **Vue Router 4.5.1** - Roteamento oficial do Vue

### Comunicação e Tempo Real
- **Axios 1.3.4** - Cliente HTTP para chamadas API
- **Socket.io-client 4.8.1** - WebSocket para comunicação em tempo real

### UI e Estilos
- **Bootstrap 5.3.8** - Framework CSS
- **Admin LTE 3.2.0** - Template administrativo
- **FontAwesome 6.7.2** - Biblioteca de ícones
- **jQuery 3.7.1** - Dependência do Admin LTE (não recomendado com Vue)

### Utilitários
- **date-fns 4.1.0** - Manipulação de datas
- **vuedraggable 4.1.0** - Drag and drop
- **xlsx** (SheetJS 0.20.3) - Manipulação de planilhas Excel

### DevTools
- **@vitejs/plugin-vue 4.6.2** - Plugin Vite para Vue
- **husky 9.1.7** - Git hooks



## ESTRUTURA DE DIRETORIOS
- SISTEMA_DROP
|-- BACKEND
|---|-- Grupo de endpoints de comunicação com Mercado Livre
|---|-- Grupo de endpoints de comunicação com Shoppee
|-- FRONTEND
|-- DOCs : Arquivos MD de Documentação dos Modulos
|---|-- Backend : MD do Backend
|---|-- Frontend : MD do Frontend
|-- Scripts SQL
|-- Scripts FIX






---

## ARQUITETURA MULTI-TENANT

O sistema deve suportar múltiplos dropshippers (usuários/lojistas) com dados 100% isolados. 
Cada dropshipper tem:
- Sua própria conta com saldo financeiro
- Seus próprios produtos cadastrados (vinculados ao catálogo do fornecedor)
- Seus próprios pedidos
- Suas próprias integrações com marketplaces
- Sua própria mensalidade (assinatura SaaS)

---

## MÓDULOS A DESENVOLVER

### 1. AUTENTICAÇÃO E GESTÃO DE USUÁRIOS

**Cadastro de usuário (dropshipper):**
- Nome completo
- E-mail (único no sistema)
- WhatsApp
- Tipo de pessoa: Física (CPF) ou Jurídica (CNPJ)
- Documento (CPF/CNPJ com validação e máscara)
- Endereço completo (CEP com auto-preenchimento via ViaCEP, Rua, Número, Complemento, 
  Bairro, Cidade, Estado)

**Funcionalidades de conta:**
- Login/Logout com sessão segura (token CSRF)
- Alteração de senha
- Perfil editável
- Modo escuro/claro (persistido em localStorage ou cookie)
- Controle de mensalidade (data de vencimento, status: em dia / vencido)
- Bloqueio de acesso quando mensalidade vencida

---

### 2. DASHBOARD (Home)

**Cards de KPIs principais:**
- Número de Vendas no mês com variação percentual em relação ao mês anterior (seta verde/
  vermelha + %)
- Pedidos para pagar (quantidade) com link direto para a listagem filtrada
- Pedidos sem vínculo de produto (quantidade) com link
- Pedidos cancelados (quantidade) com link

**Cards de métricas secundárias (ícones coloridos):**
- Total de produtos cadastrados
- Vendas dos últimos 30 dias em R$
- Vendas de hoje em R$

**Seção "Top 8 últimos produtos do catálogo":**
- Buscar os 8 produtos mais recentemente adicionados ao catálogo do fornecedor
- Exibir: foto, nome, preço de custo, estoque, botão "Cadastrar Produto"

**Barra superior (topbar):**
- Saldo atual da conta corrente do dropshipper com ícone de cifrão e link para financeiro
- Ícone de e-mail (ou mensagens)
- Ícone de notificações com badge contador (não lidas)
  - Dropdown com lista das últimas 10 notificações e link "Ver todos"
- Toggle modo escuro/claro
- Menu do usuário (avatar + nome + dropdown: Perfil, Mensalidade, Alterar Senha, Sair)

---

### 3. MÓDULO FINANCEIRO

**Regras de negócio:**
- Cada dropshipper tem uma "conta corrente" virtual no sistema
- Crédito via PIX (dropshipper faz PIX para chave do fornecedor e registra na plataforma)
- Débito automático ao pagar um pedido: valor do produto + R$ X de taxa da plataforma + 
  frete (quando aplicável)
- Saldo nunca pode ficar negativo (bloquear pagamento se saldo insuficiente)

**Tela Financeiro:**
- Exibir saldo atual em destaque
- Botão "+ Adicionar novo PIX – Online" → modal ou página com:
  - Valor a adicionar
  - Chave PIX do fornecedor exibida
  - Campo para informar o número/código do PIX realizado
  - O pagamento é verificado manualmente ou via webhook do banco (implementar conforme 
    possibilidade)
- Filtros: Tipo (Entrada/Saída), Data Início, Data Fim
- Tabela extrato "Conta Corrente":
  - Id | Descrição (texto automático) | Valor (verde=entrada, vermelho=saída) | Status | 
    Data/Hora
  - Paginação configurável (10, 25, 50, 100)
- Total de 13.500+ registros suportados (implementar paginação server-side)

---

### 4. MÓDULO DE PEDIDOS

**Fontes de pedidos:**
- Mercado Livre (via API oficial do ML – webhooks de novos pedidos)
- Shopee (via API oficial da Shopee – polling ou webhooks)
- Pedido Manual (criado diretamente na plataforma pelo dropshipper)

**Tabela "Todos os Pedidos":**

*Cards de resumo no topo:*
- Gráfico de barras (últimos 7 dias, quantidade de pedidos por dia) — usar Chart.js
- Pedidos nos últimos 30 dias (quantidade + valor R$)
- Pedidos hoje (quantidade + valor R$)

*Filtros de busca:*
- Ref Order (ID do pedido no marketplace)
- Nome do Cliente
- Data Início / Data Fim
- Pedido Pago: Sim / Não / Todos
- Cancelado: Sim / Não / Todos
- Canal: Mercado Livre / Shopee / Manual
- Integração (select dinâmico com as integrações do usuário)

*Colunas da tabela:*
- Id (interno)
- Status B2 (pipeline de fulfillment — ver abaixo)
- Detalhes do Pedido (canal, ref_id marketplace, ref_order, status canal, código de rastreio, 
  status de pagamento)
- Detalhes do Envio (método: Shopee Xpress CPF / Flex / Retirada pelo Comprador / etc.)
- Produtos (foto miniatura, SKU, nome, quantidade × valor)
- Cliente (nome/login)
- Total (R$)
- Data/Hora
- Ações (dropdown)

*Pipeline "Status B2" (status interno de fulfillment):*
1. **Baixou pedido** (timestamp automático)
2. **Pedido Pago** (timestamp quando dropshipper paga)
3. **Etiqueta Gerada** (timestamp automático + link "Ver etiqueta")
4. **Etiqueta Impressa** (timestamp)
5. **Pedido Separado** (marcado manualmente ou automaticamente)
6. **Pedido Enviado** (timestamp)

*Menu de Ações por pedido (dropdown):*
- **Pagar** → debita saldo e marca como pago; gera solicitação de etiqueta ao fornecedor
- **Ocultar** → arquivar pedido da listagem principal
- **Ajuda com o pedido** → abre chat/ticket de suporte
- **Emitir NFE: Entrada** → gera NF-e de entrada
- **Emitir NFE: Saída** → gera NF-e de saída
- **Ver etiqueta** → abre PDF/URL da etiqueta de envio

**Tela "Pedidos Não Pagos":**
- 3 cards: Pedidos para pagar (qtd), Valor dos Pedidos (R$), Valor total para pagar 
  (considera saldo disponível)
- Mesmos filtros e tabela, pré-filtrado por Pedido Pago = Não, Cancelado = Não

---

### 5. MÓDULO DE PRODUTOS (Meus Produtos)

**Listagem:**
- Gráfico de pizza: distribuição de produtos por canal (ML × Shopee)
- Gráfico de linha/barras: produtos cadastrados nos últimos 30 dias
- Filtros: Nome, SKU, Reference, Id, Integração, Com integração de SKU (Sim/Não/Todos)
- Tabela com: Id, Canal, Integração (nome + ID do anúncio no marketplace), Foto, Nome, 
  SKU, Preço de venda, Estoque, Data de cadastro, Ações (Editar/Excluir)

**Formulário de Cadastro/Edição de Produto:**

*Seleção de integração:*
- Checkboxes para cada integração cadastrada pelo usuário (Mercado Livre, Shopee)
- Ao selecionar, exibe campos específicos para aquele canal

*Seção NOME:*
- Nome padrão (máx. 60 caracteres — obrigatório)
- Nome para Mercado Livre (máx. 60 caracteres — exibido se ML selecionado)
- Nome para Shopee (máx. 100 caracteres — exibido se Shopee selecionado)

*Seção INFORMAÇÕES DA CATEGORIA:*
- Categoria UnicDrop (preenchida automaticamente, somente leitura)
- Categoria Shopee (select carregado via API da Shopee)
- Categoria Mercado Livre (select carregado via API do ML, com suporte à seleção manual)
- Tipo de produto Mercado Livre (select com opções da API do ML)
- Checkbox "Escolher categoria manualmente" (ativa seleção em cascata manual)

*Seção INFORMAÇÕES DESCRITIVAS:*
- SKU (obrigatório, único por usuário)
- EAN/GTIN + botão "Gerador de EAN" (gera EAN válido aleatório)
- Marca
- Estoque (número)
- URL YouTube (para vídeo do produto)

*Seção DIMENSÕES (para cálculo de frete):*
- Peso (kg)
- Altura, Largura, Comprimento (em metros)

*Seção DESCRIÇÃO:*
- Textarea rich text ou HTML

*Seção VARIAÇÃO:*
- Cor
- Tamanho

*Seção INFORMAÇÕES FISCAIS:*
- NCM (8 dígitos, com busca/validação)
- CEST (7 dígitos)
- Origem (select com 9 opções conforme legislação fiscal brasileira: 0=Nacional, 
  1=Estrangeira-Importação Direta, 2=Estrangeira-Mercado Interno, 3=Nacional>40%, etc.)

*Seção VALORES:*
- Custo de Compra (valor do fornecedor — somente informativo, puxado do catálogo)
- Preço de Venda para Mercado Livre (campo separado)
- Preço de Venda para Shopee (campo separado)

*Seção IMAGENS:*
- Upload múltiplo (arrastar e soltar + clique)
- Pré-visualização com possibilidade de reordenar por drag & drop
- Remoção individual
- Suporte a imagens já salvas (edição)
- Campos ocultos para controle de ordem e exclusão

*Fluxo de publicação:*
- Ao salvar, o sistema faz chamada à API do ML ou Shopee para criar/atualizar o anúncio
- Retorna o ID do anúncio no marketplace e armazena no produto

---

### 6. MÓDULO DE KITS

**Conceito:** Um kit é um produto composto por múltiplos SKUs do catálogo do fornecedor, 
vendido como um único item. O estoque do kit é calculado como o menor estoque entre seus 
componentes dividido pela quantidade de cada um.

**Listagem de Kits:**
- Cards visuais com: foto, SKU (prefixo KITB2-), nome, estrelas, preço, estoque calculado
- Composição listada: N× (SKU) Nome do componente
- Ações por kit: Publicar (no marketplace) / Duplicar / Excluir

**Formulário de Criação/Edição de Kit:**

*Coluna Esquerda – Dados do Kit:*
- SKU (gerado automaticamente com prefixo KITB2-)
- Nome
- Categoria (select)
- Estoque (calculado automaticamente — somente leitura)
- Price Cost (soma dos custos dos componentes × quantidades — calculado)
- Descrição
- Cor / Tamanho
- Largura, Altura, Comprimento (cm)
- Peso (kg)
- NCM, CEST, Origem

*Coluna Direita – Produtos do Kit:*
- Botão "+ Adicionar SKU" → abre modal de busca de SKU no catálogo
- Tabela: SKU | Foto | Produto | Valor Unitário | Quantidade (editável) | Ações (remover)
- Botão "Criar Kit"

---

### 7. MÓDULO CATÁLOGO DE PRODUTOS (Fornecedor → Dropshipper)

**Descrição:** Vitrine dos produtos disponíveis no estoque do fornecedor para o dropshipper 
escolher e cadastrar em sua loja.

**Interface:**
- Campo de busca por texto
- Filtro por categoria (árvore de categorias)
- Botão toggle "Mais Vendidos" (ordena por quantidade de vendas nos últimos 7/30 dias)
- Ordenação: Últimos cadastrados / Mais vendidos / Menor preço / Maior preço
- Grid de cards responsivo (4 colunas desktop, 2 tablet, 1 mobile)

**Card de produto do catálogo:**
- Foto do produto
- SKU (entre parênteses) + Nome completo
- Preço de custo em destaque
- Avaliação em estrelas (média das avaliações dos dropshippers)
- Cor, Tamanho, Estoque disponível
- Botão "**+ Cadastrar Produto**" → navega para formulário de cadastro pré-preenchido com 
  dados do produto do catálogo

---

### 8. MÓDULO PEDIDO MANUAL (Drop Manual)

**Descrição:** Permite comprar produtos diretamente do fornecedor sem venda no marketplace. 
Útil para pedidos de clientes diretos (WhatsApp, Instagram, etc.).

**Interface:**
- Mesmo layout e filtros do Catálogo
- Botão "**Comprar Produto**" em cada card → modal ou página de confirmação
- No modal: endereço de entrega do cliente, forma de pagamento (saldo da plataforma), 
  confirmação
- Cria um pedido interno com canal "Manual"

---

### 9. MÓDULO DE DEVOLUÇÃO

**Fluxo:**
1. Dropshipper gerencia devolução com o marketplace (fora do sistema)
2. Orienta cliente a enviar produto para endereço do fornecedor
3. Registra a devolução no sistema com dados de rastreio
4. Fornecedor recebe o produto e aprova a devolução → crédito é adicionado ao saldo

**Tela de Devolução:**
- Banner/alerta amarelo com instruções e endereço do fornecedor
- Botão "+ Nova Devolução"
- Tabela de devoluções: Id | Status (Analisando/Devolvido/Rejeitado) | Motivo | Detalhes 
  do Pedido | Rastreio | Ações

**Formulário Nova Devolução:**
- ID do Pedido UnicDrop (select ou texto com autocomplete)
- Motivo: Produto com defeito / Produto errado / Desistência da compra / Outro
- Descrição do ocorrido (textarea)
- Código de Rastreio
- URL de Rastreio
- Transportadora
- Data previsão de chegada (datepicker)
- Código de Segurança da Devolução (fornecido pelo marketplace)

---

### 10. MÓDULO DE INTEGRAÇÕES

**Conceito:** Um dropshipper pode ter múltiplas integrações (contas) no mesmo marketplace 
(ex: 2 contas no Mercado Livre) ou em marketplaces diferentes.

**Tabela de Integrações:**
- Id | Descrição | Canal (ícone + nome + badge Ativo/Inativo) | Data de registo | 
  Last Sync | Ações (Editar / Excluir / Vincular SKU)

**Criar Nova Integração:**
- Select de canal: Mercado Livre / Shopee / Conta Bling V3
- Campo de descrição (nome para identificação interna)
- Ao selecionar ML: redireciona para OAuth do Mercado Livre (fluxo Authorization Code)
- Ao selecionar Shopee: redireciona para OAuth da Shopee
- Ao selecionar Bling V3: solicita API Key do Bling

**Vincular SKU – Mercado Livre:**
- Inserir MLB ID do anúncio existente no ML
- Select de SKU interno para vincular (com busca)
- Exibe preview do SKU selecionado (foto, SKU, estoque)
- Salva vínculo: anúncio MLB → SKU interno

**Vincular SKU – Shopee (Manual):**
- Inserir Shopee Item ID do anúncio
- Botão "Buscar produto" → faz chamada à API Shopee e retorna dados do anúncio
- Depois selecionar SKU interno para vincular

**Sincronização automática:**
- Job Laravel (via Queue + Scheduler): a cada N minutos, sincronizar novos pedidos 
  de cada integração ativa
- Atualizar estoque nos anúncios quando o estoque do fornecedor mudar
- Registrar Last Sync timestamp

---

### 11. MÓDULO DE ALERTAS E NOTIFICAÇÕES

**Tipos de alerta gerados pelo sistema automaticamente:**
- **Valor devolvido:** Quando um pedido é cancelado e o valor é creditado de volta
- **Estoque zerado:** Quando produto fica sem estoque no fornecedor (estoque = 0)
- **Preço aumentou:** Quando o fornecedor sobe o