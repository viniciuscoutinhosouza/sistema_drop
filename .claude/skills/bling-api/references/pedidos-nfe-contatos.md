# Bling v3 — Pedidos de venda, NF-e/NFC-e, Contatos

> Base: `https://api.bling.com.br/Api/v3`. Nomes **[confirmar]** na referência oficial/`GET` real.

## Pedidos de venda

| Operação | Método + caminho |
|---|---|
| Listar | `GET /pedidos/vendas?pagina=1&limite=100` (filtros por data, situação, contato…) |
| Obter | `GET /pedidos/vendas/{idPedidoVenda}` |
| Criar | `POST /pedidos/vendas` |
| Alterar | `PUT /pedidos/vendas/{idPedidoVenda}` |
| Alterar situação | `PATCH /pedidos/vendas/{id}/situacoes/{idSituacao}` **[confirmar]** |

**Campos típicos** **[confirmar]**: `contato.id` (cliente — tem de existir em `/contatos`), `data`,
`itens[]` (`produto.id` ou `codigo`, `quantidade`, `valor`), `parcelas[]`, `transporte` (frete,
volumes), `loja.id` (canal de venda), `numeroPedidoLoja` (idempotência por pedido do marketplace).

> **Idempotência:** use `numeroPedidoLoja`/`numeroLoja` com o `platform_order_id` do Sistema Drop para
> não duplicar o pedido no Bling quando reenviar.

## Situações (status)

`GET /situacoes/modulos` e `GET /situacoes` **[confirmar]** — o Bling tem situações por módulo (venda,
NF-e…). Para mudar o status de um pedido você referencia o **id da situação**, não um texto livre.

## Notas fiscais (NF-e / NFC-e)

> O Bling é um **emissor fiscal completo**. Se a CMIG optar por emitir **pelo Bling**, o fluxo é:
> criar a NF-e (a partir do pedido ou avulsa) → **enviar/emitir** → acompanhar o status SEFAZ →
> baixar XML/DANFE.

| Operação | Método + caminho |
|---|---|
| Listar NF-e | `GET /nfe?pagina=1&limite=100` |
| Obter | `GET /nfe/{idNotaFiscal}` |
| Criar (rascunho) | `POST /nfe` |
| **Emitir/enviar à SEFAZ** | `POST /nfe/{idNotaFiscal}/enviar` **[confirmar]** |
| XML / DANFE | `GET /nfe/{id}/xml`, `GET /nfe/{id}/pdf` **[confirmar]** |
| NFC-e | `/nfce` (análogo) |

**Pontos de atenção fiscais:**
- A emissão pelo Bling exige a **configuração fiscal da empresa no painel do Bling** (certificado A1,
  série, natureza de operação, regime tributário). A API **não** configura isso.
- **Não confunda com a emissão própria SEFAZ do Sistema Drop** (ADR-0015/0016/0028). São **dois
  emissores** sob o mesmo CNPJ → **séries diferentes** para não colidir numeração (como já é
  ML=série 2, Shopee=série 3, própria=série 1). Se o Bling emitir, reserve **outra série** para ele e
  documente.
- Se a CMIG usa a emissão própria do Sistema Drop, o Bling pode ser **só anexo/espelho** (upload do XML
  que já foi autorizado) — **[confirmar]** se a API aceita importar/vincular um XML externo, senão o
  Bling re-emitiria (duplicando o documento fiscal). **Decisão de arquitetura, não detalhe de endpoint.**

## Contatos (clientes e fornecedores)

| Operação | Método + caminho |
|---|---|
| Listar | `GET /contatos?pagina=1&limite=100` (filtrar por `numeroDocumento` = CPF/CNPJ) |
| Obter | `GET /contatos/{idContato}` |
| Criar | `POST /contatos` |
| Alterar | `PUT /contatos/{idContato}` |

**Campos típicos** **[confirmar]**: `nome`, `tipo` (`F` física / `J` jurídica), `numeroDocumento`
(CPF/CNPJ, só dígitos), `ie`, `email`, `telefone`, `endereco{...}`, `tiposContato` (cliente/fornecedor).

> **Idempotência:** antes de criar, `GET /contatos?numeroDocumento=<doc>` — o Bling costuma recusar
> documento duplicado. Reaproveite o contato existente (mesmo padrão do `_upsert_customer` da NF-e
> própria). Lembre que o **endereço do comprador do ML vem como objeto `{id,name}`** — no Sistema Drop
> use `services/address_parser.parse_buyer_address` para achatar antes de mandar ao Bling.

## Ordem de montagem de um pedido completo no Bling

1. **Contato** (cliente): upsert por CPF/CNPJ → pega `idContato`.
2. **Produtos**: garantir que existem por `codigo` (SKU) → pega `idProduto` (ou manda por `codigo`).
3. **Pedido de venda**: `POST /pedidos/vendas` com `contato.id` + `itens[]` + `numeroPedidoLoja`.
4. (Opcional) **NF-e**: criar a partir do pedido e emitir — **só** se o papel fiscal do Bling for esse.
