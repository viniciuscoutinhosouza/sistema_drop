---
name: eship-api
description: Auxilia no desenvolvimento de integrações com a API do eShip (WMS da Armazenaki, `*.eship.com.br/v3`). Use SEMPRE que o usuário mencionar eShip, Armazenaki, WMS, "envio de produtos", ordem/expedição, saldo/estoque físico, recebimento/entrada, rastreamento/embarque, ou qualquer função `webService*`. Cobre autenticação por apikey, o padrão RPC `?api&funcao=`, os 12 módulos WMS (Produto, Ordem, Transporte, Recebimento, Armazém, Sistema, Cadastro, Usuário, Inventário, Precificação, Requisição, Operação) e todas as operações Get/Post/Put/Delete. Use também ao corrigir/estender o módulo `BACKEND/integrations/eship/` do Sistema Drop.
---

# eShip (WMS Armazenaki) — Skill de integração

Esta skill orienta o desenvolvimento de integrações com a API do **eShip**, o WMS da Armazenaki
(`https://<tenant>.eship.com.br/v3`). Ela cobre a **API inteira** — todas as operações
Get/Post/Put/Delete dos 12 módulos WMS — e é a base para qualquer implementação (não só o fluxo
atual do Sistema Drop).

> **Fonte da verdade:** o OpenAPI oficial em `https://swagger.eship.com.br/docs/WMS/<Modulo>.json`
> (um arquivo por módulo) + o **comportamento da API ao vivo**. Esta skill resume e destaca; quando
> houver dúvida sobre um campo, **leia o spec do módulo** e/ou teste com uma função `Get*`.

## Como usar esta skill

Progressive disclosure: este arquivo dá a visão geral e aponta a referência detalhada. **Leia a
referência relevante antes de gerar código** — os detalhes que evitam bugs estão lá.

| Tarefa | Leia primeiro |
|---|---|
| Autenticar, montar a chamada, tratar erro/paginação/encoding | `references/autenticacao-rpc.md` |
| Descobrir se uma função existe / listar tudo que a API oferece | `references/catalogo-completo.md` |
| Cadastrar/consultar produto, variação, lote, saldo/estoque, entrada | `references/produtos-estoque.md` |
| Criar/consultar ordem, anexar NF-e/etiqueta, emissão, cancelar, status | `references/ordens-emissao.md` |
| Rastreamento, embarque, rota, remessa, recebimento/entrada programada | `references/transporte-recebimento.md` |
| Armadilhas conhecidas + backlog de correções do Sistema Drop | `references/gotchas-e-correcoes.md` |

## Conceitos fundamentais que valem repetir aqui

**Não é REST.** Há um único endpoint; a operação vai no query param `funcao` e o método é **sempre
POST**:

```
POST https://<tenant>.eship.com.br/v3/?api&funcao=webServiceXxx
Header: api: <APIKEY>
Content-Type: application/json
Body:  { ...parâmetros da função... }     # JSON, mesmo para consultas
```

- **`<tenant>`** = subdomínio da empresa (ex.: `armazenaki`). O spec mostra `http://localhost:8080/v3`
  — isso é placeholder de dev; use o subdomínio real. Sempre **HTTPS** (a apikey vai no header).
- **Autenticação:** apikey **única por empresa** no header `api`. (SecurityScheme `ApiKeyAuth`,
  `in: header`, `name: api`.)
- **HTTP 200 NÃO garante sucesso.** Erro de negócio vem em 200 com o campo `erros`:
  `{"erros":[{"erro":{"mensagem":"...","codigo":"MAP0014"}}], "corpo":{}}`. **Sempre inspecione
  `erros` antes de tratar como sucesso.** `MAP0014` = "Função não existe" (a função pode estar no
  spec mas **não habilitada** naquele tenant).
- **Encoding: ISO-8859-1 (latin-1).** As respostas trazem acentos em latin-1 — decodifique como
  `latin-1`, não utf-8, senão vira mojibake ("Lan�ado").
- **Paginação:** a maioria dos `Get*` aceita `pagina`, `quantidadeRegistros`, `ordenacao`,
  `completo`, `incrementar`. A resposta traz `corpo.body.dadosPaginacao`
  (`totalRegistros`, `registrosPorPagina`, `quantidadePaginas`, `paginaAtual`, `totalObjetos`) e
  `corpo.body.dados` (a lista). Padrão: **25 registros/página**.
- **Sem webhooks.** Não há push de eventos — status/rastreio são obtidos por **polling**.
- **WMS é a fonte de verdade do estoque físico.** Consulte saldo no eShip, não no Drop.
- **Status são objetos** `{id, descricao, cor}`, nunca strings. **Mapeie pelo `id` numérico** (o
  texto tem acento/encoding e pode mudar). Ver a tabela em `references/ordens-emissao.md`.

## Mapa dos 12 módulos WMS (289 funções)

| Módulo | Funções | Domínio |
|---|---:|---|
| **Produto** | 36 | produto, variação, categoria, lote, entrada, **saldoEstoque**, reserva, saída, serial |
| **Ordem** | 20 | ordem de saída, **anexo (NF-e/etiqueta)**, **emissão NF**, backorder, histórico, cancelar, estornar |
| **Transporte** | 68 | **rastreamento**, embarque, rota, remessa, volume, expedição (o rastreio real mora aqui) |
| **Recebimento** | 36 | entrada programada, apontamento, LPN, devolução, confronto NF-e |
| **Armazém** | 47 | depósito, doca, endereçamento, fila de operação, movimentador, tipoOrdem |
| **Sistema** | 26 | GetInfosObjeto, log, mensageria, metadados, gateway |
| **Cadastro** | 20 | cadastro (pessoa/empresa), contato, endereço, classificação |
| **Usuário** | 19 | usuário, **GetApikey**, grupos, relações de armazém/cadastro |
| **Inventário** | 15 | inventário, contagem, plano de contagem |
| **Precificação** | 1 | consulta de preço |
| **Requisição** | 1 | contagem por posição |
| **Operação** | — | referenciado no swagger, mas `Operacao.json` retorna 404 (não servido) |

Inventário completo função a função: `references/catalogo-completo.md`.

## Contexto no Sistema Drop

A integração vive em `BACKEND/integrations/eship/` (`client.py`, `config.py`, `service.py`,
`router.py`, `status_map.py`, `tasks.py`). Credenciais por **empresa (CMIG)**:
`cmig.eship_base_url` + `eship_api_key` + `eship_warehouse_code` + `eship_active`. O `client.call`
centraliza toda chamada HTTP. Há um backlog de correções conhecidas (status quebrado, nome de função
de cancelamento errado, filtro de saldo errado, extração de id da ordem etc.) documentado em
`references/gotchas-e-correcoes.md` — **consulte antes de mexer no módulo**.
