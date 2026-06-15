📋 Especificação Técnica — Pós-Venda: Mensagens Não Lidas & Reclamações
Mercado Turbo v6.1.30 — Análise para Desenvolvimento de Clone Fiel Gerado em: 14/06/2026

📌 Sumário
Estrutura Geral da Página
Aba: Mensagens Não Lidas
Aba: Reclamações
Modais e Diálogos Globais
API do Mercado Livre — Mensagens Pós-Venda
API do Mercado Livre — Reclamações
Fluxo de Integração Recomendado
1. Estrutura Geral
URL da Página
https://app.mercadoturbo.com.br/sistema/mensagem/conversacoes_novo?aba=0
aba=0 → Mensagens Não Lidas
aba=1 → Reclamações (acesso direto via menu: /sistema/mensagem/conversacoes_novo?aba=1)
Layout da Página
A página é um layout de duas colunas + painel lateral direito, contida dentro de um <tablist> com duas abas:

+--------------------------------------------------+
|  [Tab: Mensagens Não Lidas]  [Tab: Reclamações 3]|
+--------------------------------------------------+
| Coluna Esq.  | Painel Central     | Painel Dir.  |
| (lista)      | (detalhe)          | (histórico)  |
| ~280px       | ~630px             | ~200px       |
+--------------------------------------------------+
Componente de Abas (TabList)
Tab 1: "Mensagens Não Lidas" — href #tab-mensagens-pos-venda
Tab 2: "Reclamações" — href #j_idt846 — badge numérico vermelho com contagem (ex.: 3)
Framework: JSF (JavaServer Faces) com PrimeFaces
2. Aba: Mensagens Não Lidas
URL
https://app.mercadoturbo.com.br/sistema/mensagem/conversacoes_novo?aba=0
2.1 Estado Vazio (Empty State)
Coluna Esquerda:

+-----------------------------------------+
|  Você não possui mensagens não lidas    |
|                                         |
|  (lista vazia)                          |
|                                         |
|        [🔄]   [✓]                       |
+-----------------------------------------+
Painel Central (Empty State):

+-----------------------------------------+
|   [Ilustração: mulher com checklist]    |
|                                         |
|   Você Não Possui Mensagens Pendentes   |
|   (h2 - cor: #5c35d9 / roxa)           |
|                                         |
|  No momento, você não tem mensagens     |
|  pós-venda aguardando resposta/leitura. |
|  As conversas aparecem organizadas      |
|  por venda na coluna ao lado.           |
|  Para buscar novas mensagens, clique    |
|  no botão de sincronizar [🔄] abaixo.  |
|                                         |
|  Quando houver novas mensagens, você    |
|  verá um alerta sobre o botão de        |
|  sincronização — como neste exemplo:   |
|                                         |
|  +----------------------------+         |
|  | [🔄¹]  [✓]               |         |
|  +----------------------------+         |
+-----------------------------------------+
2.2 Botões de Ação (rodapé da coluna esquerda)
Botão	Ícone	Tooltip	Ação
Sincronizar	🔄 (circular arrows)	"Recarregar mensagens"	Busca novas mensagens não lidas na API
Marcar como Lida	✓ (check)	"Marcar mensagens como lida por período"	Abre modal de seleção de período
Badge no botão Sincronizar: Badge vermelho circular com número quando há mensagens pendentes (ex: badge "1" vermelho).
Ambos os botões são circulares, estilo outlined, cor cinza/slate.
2.3 Estado com Conversas (quando há mensagens)
A coluna esquerda exibe uma lista de conversas. Cada item contém:

+------------------------------------------+
| [foto_produto 60x60]  Título Produto     |
|                       #ID_venda  [📋]    |
|                       Apelido Comprador  |
|                       Última mensagem:   |
|                       "trecho da msg..." |
|                       há X tempo         |
+------------------------------------------+
Painel Central (conversa aberta):

+------------------------------------------------------+
| [Qtd]x Título do Produto [📋]                        |
| #ID_VENDA [📋] | APELIDO [📋] | MLB-ID [📋] | R$ Val |
| Vendido em DD/MM/AAAA                                |
+------------------------------------------------------+
| [Área de Chat - rolagem vertical]                    |
|  ┌─────────────────────────────┐                     |
|  │ Nome Comprador              │ ← mensagem recebida |
|  │ "texto da mensagem..."      │   (balão esq.)      |
|  │                       X dias│                     |
|  └─────────────────────────────┘                     |
|        ┌────────────────────────────┐                |
|        │ "resposta do vendedor..."  │ ← enviada      |
|        │                    X dias  │   (balão dir.) |
|        └────────────────────────────┘                |
|  [Anexo: nome_arquivo.jpg] ← link clicável          |
+------------------------------------------------------+
| [📎] [Digite sua mensagem aqui...        ] [►]       |
|                         350 caracteres restantes     |
+------------------------------------------------------+
2.4 Área de Input de Mensagem
Elemento	Especificação
<textarea>	placeholder: "Digite sua mensagem aqui..."
Contador	"350 caracteres restantes" (máximo = 350 chars)
Botão enviar	Ícone de seta/avião, cor verde (
#00a650 aprox.)
Botão anexo	Ícone 📎 (clipe), abre <input type="file">
Mensagens prontas	Link/ícone adicional para abrir modal de templates
2.5 Diálogo: Marcar Mensagens como Lida por Período
+------------------------------------------------+
| MODAL: "Marcar Mensagens como Lida por Período"|
|  [X] Fechar                                    |
|                                                |
|  [Seletor de período / data range]             |
|                                                |
|  [Marcar como Lido]   [Fechar]                 |
+------------------------------------------------+
2.6 Diálogo: Código de Rastreio
+----------------------------------------+
| MODAL: "Código de Rastreio"            |
|  [X] Fechar                            |
|                                        |
|  [Input: código de rastreamento]       |
|                                        |
|  [Enviar]   [Fechar]                   |
+----------------------------------------+
2.7 Diálogo: Cálculo de Frete dos Correios
+----------------------------------------+
| MODAL: "Cálculo de Frete dos Correios" |
|  [X] Fechar                            |
|                                        |
|  [campos do cálculo]                   |
|                                        |
|  [Calcular]   [Fechar]                 |
+----------------------------------------+
2.8 Diálogo: Mensagens Prontas (Templates)
+----------------------------------------+
| MODAL: "Mensagens Prontas"             |
|  [X] Fechar                            |
|                                        |
|  [Lista de templates cadastrados]      |
|                                        |
|  [Usar Mensagem]   [Fechar]            |
+----------------------------------------+
2.9 Diálogo: Carrinho do Comprador
+----------------------------------------+
| MODAL: "Carrinho do Comprador"         |
|  [X] Fechar                            |
|                                        |
|  [info dos itens do carrinho]          |
|                                        |
|  [Fechar]                              |
+----------------------------------------+
2.10 Diálogo: Informações da Entrega
+----------------------------------------+
| MODAL: "Informações da Entrega"        |
|  [X] Fechar                            |
|                                        |
|  [detalhes de envio/rastreio]          |
|                                        |
|  [Fechar]                              |
+----------------------------------------+
2.11 Diálogo: Reembolso Parcial
+----------------------------------------+
| MODAL: "Reembolso Parcial"             |
|  [X] Fechar                            |
|                                        |
|  [valor a reembolsar]                  |
|                                        |
|  [Reembolsar]   [Fechar]               |
+----------------------------------------+
3. Aba: Reclamações
URL
https://app.mercadoturbo.com.br/sistema/mensagem/conversacoes_novo?aba=1
3.1 Layout Geral
+-----------------------------------------------------------+
| [Tab: Mensagens Não Lidas] | [Tab: Reclamações  3]        |
+-----------------------------------------------------------+
| COLUNA ESQ.   | PAINEL CENTRAL              | PAINEL DIR. |
| ~280px        | ~630px                      | ~200px      |
+-----------------------------------------------------------+
3.2 Coluna Esquerda — Filtro + Lista
Filtro (toolbar):

Exibir Reclamações: [dropdown: Abertas ▼]
Opções do dropdown:

Todas (value="0")
Abertas (value="1") — padrão selecionado
Fechadas (value="2")
Item de lista (grid cell) — cada reclamação:

+------------------------------------------+
| [foto_produto 60x60]                     |
|   Tipo: Reclamação Comprador/Vendedor    |
|   Estágio: Reclamação                   |  ← ou "Intervenção do Mercado Livre"
|   Status: Aberto                         |  ← cor laranja/vermelho para Aberto
|   Última Interação: DD/MM/AAAA HH:MM    |
+------------------------------------------+
Estágios possíveis observados:

Valor API	Label UI
claim	Reclamação
dispute	Intervenção do Mercado Livre
recontact	Recontato
Status possíveis observados:

Valor API	Label UI	Cor
opened	Aberto	Laranja (#f73)
closed	Fechado	Cinza
Paginação (navigation):

[<<] [<] [1] [>] [>>]   Página: [1 ▼]
Componentes:

Link "Primeira página" — <<
Link "Página anterior" — <
Link "Page N" — número atual
Link "Próxima página" — >
Link "Última página" — >>
Combobox de seleção de página
3.3 Painel Central — Detalhes da Reclamação
3.3.1 Header da Reclamação
+--------------------------------------------------------------+
| [Qtd]x Título do Produto                          [📋]       |
| #ID_VENDA [📋] | APELIDO [📋] | MLB-ID [📋] | R$ Valor |     |
| Vendido em DD/MM/AAAA                                        |
| ID Reclamação: XXXXXXXXXX [📋] | Aberta em DD/MM/AAAA HH:MM |
| [Ver no ML]  [Ver Resolução Esperada]                        |
+--------------------------------------------------------------+
| [badge: Reputação Afetada]  Motivo da Reclamação: "texto"   |
|  OU                                                          |
| [badge: Reputação Não Afetada]  Motivo da Reclamação: "txt" |
+--------------------------------------------------------------+
Badges de Reputação:

Badge	Cor de Fundo	Cor Texto
Reputação Afetada	Vermelho (
#e02020 aprox.)	Branco
Reputação Não Afetada	Verde (
#00a650 aprox.)	Branco
Botões do Header:

Botão	Tipo	Ação
Ver no ML	<button type="submit">	Abre a reclamação no Mercado Livre
Ver Resolução Esperada	<button type="submit">	Exibe modal com resoluções esperadas
Ícones de Copiar [📋]:

Cada ID relevante tem um ícone de cópia ao lado
IDs copiáveis: ID da venda, Apelido do comprador, ID do anúncio (MLB), ID da reclamação
3.3.2 Ações Disponíveis
Caso: Estágio "Reclamação" (claim)

Ações Disponíveis: [?]
[Enviar Mensagem ao Comprador]  [Reembolsar Total]
[Solicitar Mediação do ML]
Caso: Estágio "Intervenção do Mercado Livre" (dispute) com devolução

Esta reclamação possui uma devolução: [Ver Detalhes]
Depois que receber a devolução, você pode:
[Revisar Devolução]
Nota: No estágio dispute, os botões de "Enviar Mensagem ao Comprador" e "Reembolsar Total" podem não aparecer, sendo substituídos pelas opções de devolução.

Botões de Ação Identificados:

Botão	Tipo	Disponibilidade	API Action
Enviar Mensagem ao Comprador	Outlined button	stage=claim	send_message_to_complainant
Reembolsar Total	<button type="submit">	stage=claim	refund
Solicitar Mediação do ML	<button type="submit">	stage=claim	open_dispute
Ver Detalhes	<button type="submit">	quando há devolução	GET /claims/{id}/returns
Revisar Devolução	<button type="submit">	após receber devolução	return_review
3.3.3 Abas de Mensagens (inner tabs)
[Mensagens com o Comprador] | [Mensagens com o Mediador]
Aba: Mensagens com o Comprador

Quando stage=claim e disponível:

+------------------------------------------------------+
| Nome Comprador                                       |
| "texto da mensagem..."                               |
|                                               X dias |
|                                                      |
|       "Resposta do vendedor..."                      |
|                                               X dias |
|                                                      |
| [Anexo: nome_arquivo.jpeg] ← link                   |
+------------------------------------------------------+
| [📎] [Digite sua mensagem aqui...    ] [►]           |
|                    350 caracteres restantes          |
+------------------------------------------------------+
Quando stage=dispute e mensagens com comprador bloqueadas:

+------------------------------------------------------+
| (spinner loading)                                    |
| Não é possível enviar mensagem ao comprador          |
+------------------------------------------------------+
Aba: Mensagens com o Mediador

Quando stage=dispute (Intervenção ML):

+------------------------------------------------------+
| Mediador                                             |
| "Olá — sou a assistente virtual do Mercado Livre."  |
| [texto em negrito com resumo do caso]               |
| - Detalhes relatados pelo comprador: ...            |
| - Ações realizadas: ...                              |
| [Anexo: arquivo.jpeg] ← link                        |
|                                              X dias  |
|                                                      |
| Mediador                                             |
| "O caso foi analisado... opções:                    |
|  1. [Melhor opção ⭐] Devolução                     |
|  2. Reembolso parcial                               |
|  3. Orientação"                                     |
|                                              X dias  |
|                                                      |
| "Pode oferecer a devolução integral, 100%"          |
| (resposta do vendedor)                              |
|                                                      |
| (spinner loading)                                   |
| Não é possível enviar mensagem ao mediador          |
+------------------------------------------------------+
Nota: Quando a mediação está encerrada ou em etapa final, ambas as abas exibem "Não é possível enviar mensagem" com spinner de loading.

3.4 Painel Direito — Histórico de Ações
+---------------------------+
| Histórico de Ações        |
+---------------------------+
| ┌─────────────────────┐   |
| │ Enviou Mensagem ao  │   |
| │ Comprador           │   |
| │ Quem: Vendedor      │   |
| │ Estágio: Reclamação │   |
| │ Status: Aberto      │   |
| │ Data: 13/06/2026    │   |
| │       15:19         │   |
| └─────────────────────┘   |
| ┌─────────────────────┐   |
| │ Enviou Mensagem ao  │   |
| │ Vendedor            │   |
| │ Quem: Comprador     │   |
| │ ...                 │   |
| └─────────────────────┘   |
| ┌─────────────────────┐   |
| │ Abriu a Reclamação  │   |
| │ Quem: Comprador     │   |
| │ Data: 12/06/2026... │   |
| └─────────────────────┘   |
+---------------------------+
Tipos de eventos no histórico:

action_name (API)	Label Exibido
open_claim	Abriu a Reclamação
send_message_to_complainant	Enviou Mensagem ao Comprador
send_message_to_mediator	Enviou Mensagem ao Mediador
open_dispute / mediador entra	Enviou Mensagem ao Vendedor (Quem: Mediador)
generate_return_async	generate_return_async (nome raw)
allow_return	Gerar Etiqueta de Devolução
Cada card do histórico contém:

Título: ação realizada
Quem: Vendedor / Comprador / Mediador
Estágio: Reclamação / Intervenção do Mercado Livre
Status: Aberto / Fechado
Data: DD/MM/AAAA HH:MM
3.5 Modais Específicos de Reclamações
Modal: Resoluções Esperadas
+------------------------------------------+
| MODAL: "Resoluções Esperadas"            |
| [X] Fechar                               |
|                                          |
| [conteúdo das resoluções do ML]          |
|                                          |
| [Fechar]                                 |
+------------------------------------------+
Modal: Detalhes da Devolução
+------------------------------------------+
| MODAL: "Detalhes da Devolução"           |
| [X] Fechar                               |
|                                          |
| [informações de status da devolução]     |
|                                          |
| [Fechar]                                 |
+------------------------------------------+
Modal: Revisar Devolução
+------------------------------------------+
| MODAL: "Revisar Devolução"               |
| [X] Fechar                               |
|                                          |
| [produto chegou conforme esperado?]      |
|                                          |
| [Tudo Certo]   [Há um Problema]          |
| [Fechar]                                 |
+------------------------------------------+
Modal: Reportar Problema com a Devolução
+------------------------------------------+
| MODAL: "Reportar Problema com a         |
|         Devolução"                       |
| [X] Fechar                               |
|                                          |
| [formulário de detalhes do problema]     |
|                                          |
| [Enviar Para Análise]   [Fechar]         |
+------------------------------------------+
Diálogo de Confirmação (AlertDialog)
+------------------------------------------+
| [X] Fechar                               |
|                                          |
| [mensagem de confirmação]                |
|                                          |
| [Sim]   [Não]                            |
+------------------------------------------+
4. Modais e Diálogos Globais
Estes modais existem no DOM e são compartilhados entre as duas abas:

Modal	Botões de Ação
Informações da Entrega	Fechar
Marcar Mensagens como Lida por Período	Marcar como Lido / Fechar
Código de Rastreio	Enviar / Fechar
Mensagens Prontas	Usar Mensagem / Fechar
Carrinho do Comprador	Fechar
Cálculo de Frete dos Correios	Calcular / Fechar
Reembolso Parcial	Reembolsar / Fechar
Resoluções Esperadas	Fechar
Detalhes da Devolução	Fechar
Revisar Devolução	Tudo Certo / Há um Problema / Fechar
Reportar Problema com a Devolução	Enviar Para Análise / Fechar
AlertDialog genérico	Sim / Não
5. API — Mensagens Pós-Venda
Base URL: https://api.mercadolibre.com Autenticação: Authorization: Bearer $ACCESS_TOKEN

5.1 Buscar Mensagens Não Lidas (todas as ordens)
http
GET /messages/unread?role=seller&tag=post_sale
Parâmetros:

Parâmetro	Tipo	Obrigatório	Descrição
role	String	Sim	seller ou buyer
tag	String	Sim	sempre post_sale
Resposta (com mensagens):

json
{
  "user_id": 378136913,
  "results": [
    {
      "resource": "/packs/1977056109/sellers/378136913",
      "count": 1
    }
  ]
}
Resposta (sem mensagens):

json
{
  "user_id": "1234512314",
  "results": []
}
Lógica: results.length > 0 → há mensagens pendentes. count = quantidade por pack.

5.2 Buscar Mensagens de um Pack específico
http
GET /messages/packs/{PACK_ID}/sellers/{SELLER_ID}?tag=post_sale
Este endpoint marca as mensagens como lidas automaticamente. Para apenas consultar sem marcar:

http
GET /messages/packs/{PACK_ID}/sellers/{SELLER_ID}?tag=post_sale&mark_as_read=false
Campos da resposta de cada mensagem:

json
{
  "paging": { "limit": 2, "offset": 1, "total": 31 },
  "conversation_status": {
    "path": "/packs/2000000089077943/seller/415458330",
    "status": "active",
    "substatus": null,
    "claim_id": null,
    "shipping_id": null
  },
  "messages": [
    {
      "id": "2c92808469fea23a...",
      "site_id": "MLB",
      "from": {
        "user_id": "415458330",
        "email": "comprador@email.com",
        "name": "Nome Comprador"
      },
      "status": "IN_MODERATION",
      "text": "Texto da mensagem",
      "message_date": {
        "received": "2019-04-08T20:58:49.000Z",
        "read": "2019-04-08T20:58:52.000Z"
      },
      "message_moderation": {
        "status": "NON_MODERATED",
        "reason": "none"
      },
      "message_attachments": [
        {
          "filename": "arquivo.pdf",
          "original_filename": "arquivo_original.pdf",
          "type": "application/octet-stream",
          "size": 225677
        }
      ]
    }
  ]
}
5.3 Mensagens Não Lidas Filtradas por Resource
http
GET /messages/unread/packs/{PACK_ID}/sellers/{SELLER_ID}?tag=post_sale
5.4 Enviar Mensagem (POST)
http
POST /messages/packs/{PACK_ID}?tag=post_sale
Content-Type: application/json
json
{
  "from": {
    "user_id": 123456789
  },
  "to": {
    "user_id": 987654321
  },
  "text": "Texto da mensagem aqui (máx 350 chars)"
}
5.5 Fluxo por Notificações (recomendado pelo ML)
O fluxo oficial recomendado é:

Subscrever notificações do tópico /messages
Ao receber notificação → identificar o pack_id
Fazer GET /messages/packs/{PACK_ID}/sellers/{SELLER_ID}?tag=post_sale para obter o conteúdo
6. API — Reclamações
Base URL: https://api.mercadolibre.com/post-purchase/v1

6.1 Buscar Reclamações do Vendedor (principal endpoint)
http
GET /post-purchase/v1/claims/search?players.user_id={USER_ID}&players.role=respondent&status=opened&limit=30&offset=0
Parâmetros de Filtro:

Parâmetro	Tipo	Notas
players.user_id	Number	Obrigatório junto com players.role
players.role	String	complainant ou respondent
status	String	opened / closed
stage	String	claim, dispute, recontact, stale, none
type	String	mediations, return, fulfillment, ml_case
order_id	Number	Filtra por pedido específico
date_created	Date	Com range=
last_updated	Date	Com range=
Paginação:

Parâmetro	Padrão	Máximo
offset	0	9999
limit	30	100
Resposta:

json
{
  "paging": {
    "total": 316,
    "offset": 0,
    "limit": 30
  },
  "data": [
    {
      "id": 5527113570,
      "resource_id": 2000016902839600,
      "status": "opened",
      "type": "mediations",
      "stage": "claim",
      "resource": "order",
      "reason_id": "PNR...",
      "fulfilled": true,
      "quantity_type": "total",
      "players": [
        {
          "role": "complainant",
          "type": "buyer",
          "user_id": 123456,
          "available_actions": []
        },
        {
          "role": "respondent",
          "type": "seller",
          "user_id": 789012,
          "available_actions": [
            {
              "action": "send_message_to_complainant",
              "mandatory": false,
              "due_date": null
            },
            {
              "action": "refund",
              "mandatory": false,
              "due_date": null
            },
            {
              "action": "open_dispute",
              "mandatory": false,
              "due_date": null
            }
          ]
        }
      ],
      "resolution": null,
      "site_id": "MLB",
      "date_created": "2026-06-12T19:26:00.000-04:00",
      "last_updated": "2026-06-13T15:19:00.000-04:00"
    }
  ]
}
6.2 Consultar Reclamação Específica
http
GET /post-purchase/v1/claims/{CLAIM_ID}
Campos principais da resposta:

Campo	Tipo	Descrição
id	Number	ID da reclamação
resource_id	Number	ID do pedido/envio/pagamento
status	String	opened / closed
type	String	mediations, return, fulfillment, etc.
stage	String	claim, dispute, recontact, stale, none
reason_id	String	PNR (Produto Não Recebido), PDD (Produto Diferente/Defeituoso), CS (Compra Cancelada)
fulfilled	Boolean	Produto foi entregue?
quantity_type	String	total / partial
players	Array	Atores (comprador, vendedor, mediador) com available_actions
resolution	Object	null se aberta; dados de resolução se fechada
date_created	DateTime	Abertura da reclamação
last_updated	DateTime	Última atualização
related_entities	Array	Ex.: [{type: "return", ...}] quando há devolução
Mapeamento de stage → Label UI:

stage	Label no Mercado Turbo
claim	Reclamação
dispute	Intervenção do Mercado Livre
recontact	Recontato
stale	(ML / comprador)
none	—
Mapeamento de available_actions → Botões UI:

action	Botão Exibido
send_message_to_complainant	"Enviar Mensagem ao Comprador"
send_message_to_mediator	(habilita aba "Mensagens com o Mediador")
refund	"Reembolsar Total"
open_dispute	"Solicitar Mediação do ML"
allow_partial_refund	"Reembolso Parcial"
return_review	"Revisar Devolução"
allow_return	"Gerar etiqueta de devolução"
send_tracking_number	"Código de Rastreio"
Mapeamento de related_entities → Info na UI:

json
"related_entities": [{"type": "return", "id": 12345}]
→ Exibe: "Esta reclamação possui uma devolução: [Ver Detalhes]"

6.3 Detalhes da Reclamação (título/descrição em PT-BR)
http
GET /post-purchase/v1/claims/{CLAIM_ID}/detail
json
{
  "due_date": "2026-06-19T22:33:00.000-04:00",
  "action_responsible": "mediator",
  "title": "Devolução em mediação com Mercado Livre",
  "description": "Interviemos para ajudar. ...",
  "problem": "Produto não recebido"
}
6.4 Histórico de Ações da Reclamação
http
GET /post-purchase/v1/claims/{CLAIM_ID}/actions-history
json
[
  {
    "action_name": "send_message_to_complainant",
    "player_role": "respondent",
    "claim_stage": "claim",
    "claim_status": "opened",
    "date_created": "2026-06-13T15:19:00.000-04:00"
  },
  {
    "action_name": "open_claim",
    "player_role": "complainant",
    "claim_stage": null,
    "claim_status": null,
    "date_created": "2026-06-12T19:26:00.000-04:00"
  }
]
Mapeamento action_name → Label UI no Histórico:

action_name	player_role	Label Exibido
open_claim	complainant	Abriu a Reclamação
send_message_to_complainant	respondent	Enviou Mensagem ao Comprador
send_message_to_complainant	complainant	Enviou Mensagem ao Vendedor
send_message_to_mediator	respondent	Enviou Mensagem ao Mediador
send_message_to_mediator	complainant	Enviou Mensagem ao Mediador
open_dispute	complainant	Iniciou uma Mediação
generate_return_async	mediator	generate_return_async (raw)
allow_return	respondent	Gerar Etiqueta de Devolução
6.5 Verificar se Afeta Reputação
http
GET /post-purchase/v1/claims/{CLAIM_ID}/affects-reputation
json
{
  "affects_reputation": "affected",
  "has_incentive": true,
  "due_date": "2026-06-14T20:00:00.000-04:00"
}
Mapeamento → Badge UI:

affects_reputation	Badge
affected	🔴 "Reputação Afetada"
not_affected	🟢 "Reputação Não Afetada"
not_applies	(sem badge)
6.6 Mensagens de uma Reclamação
http
GET /post-purchase/v1/claims/{CLAIM_ID}/messages?role=seller
Resposta:

json
[
  {
    "sender_role": "complainant",
    "receiver_role": "respondent",
    "message": "Não recebi o pacote...",
    "translated_message": null,
    "date_created": "2026-06-12T19:26:00.000-04:00",
    "attachments": [
      {
        "filename": "foto_produto.jpeg"
      }
    ],
    "status": "available",
    "stage": "claim",
    "message_moderation": {
      "status": "clean",
      "reason": null
    },
    "hash": "5527113570_0_abc123..."
  }
]
Mapeamento sender_role → Layout da mensagem:

sender_role	Posição no chat	Nome exibido
complainant (buyer)	Esquerda (balão cinza)	Nome do comprador
respondent (seller)	Direita (balão verde/roxo)	(sem nome, é o vendedor)
mediator	Esquerda (balão diferenciado)	"Mediador"
6.7 Enviar Mensagem em uma Reclamação
http
POST /post-purchase/v1/



