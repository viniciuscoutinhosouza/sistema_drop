# Módulo Produto — cadastro, saldo/estoque, entrada

Todas as chamadas: `POST /?api&funcao=<Nome>` (ver `autenticacao-rpc.md`). Schemas extraídos do
`Produto.json` + shapes reais capturados do tenant `armazenaki`.

## webServicePostProduto — cadastrar/atualizar produto (idempotente por SKU)
**Request** (`*` = obrigatório):
- `codigoSKU*` (string) — o SKU/código do produto
- `descricao*` (string)
- `cnpjCadastro*` (string) — CNPJ da empresa dona do cadastro (só dígitos)
- `embalado*` (integer) — 1/2 (observado `embalado: 2` em itens reais; confirme a semântica)
- `gtin` (string) — EAN/código de barras (opcional)
- `tipo` (integer, `1=Simples`) + `descricaoTipo`
- `status` (integer, `1=Normal`) + `descricaoStatus`
- pesos/dimensões: `pesoLiquido`, `pesoBruto`, `pesoCubico`, `largura`, `comprimento`, `altura`,
  `unidadePeso`, `unidadeMedida`, `unidadeReferencia` (+ `descricao*` de cada)
- `caracteristicas`, `controles`/`descricaoControles`, `debitoLotes`/`descricaoDebitoLotes`

> ⚠️ O spec **não declara maxLength** para `codigoSKU`/`gtin`. Truncar em 15 (como o código atual)
> é suposição — confirme os limites reais antes de assumir; SKUs longos podem ser válidos.

> ⚠️ **O `GetProduto` NÃO traz o estoque na listagem** — `totalFisico`/`totalDisponivel`/
> `totalReservado`/`itsFull` vêm **0** e `saldoEstoque` vem `[]`. O estoque real está no
> **`webServiceGetSaldoEstoque`** (ver abaixo). Para exibir estoque na lista, **enriqueça** cada
> produto com o saldo, casando **`GetProduto.id` == `GetSaldoEstoque.pro_produto_id`** (ou por
> `codigo`/SKU). No Drop isso é feito em `service._fetch_saldo_indexes` + `_eship_produto_row(p, saldo)`.

## webServiceGetProduto — listar produtos (paginado; estoque vem 0 aqui)
**Request:** filtros + paginação (`pagina`, `quantidadeRegistros`, `ordenacao`, `completo`).
**Response:** `corpo.body.dadosPaginacao` + `corpo.body.dados[]`. Cada produto (campos úteis):
```
id, codigo (=SKU), codigoBarras (=EAN), descricao,
pesoLiquido/pesoBruto/pesoCubico, largura/comprimento/altura, dataCriacao {date,timezone},
embalado, cfop, unidadeMedida, tipo{id,descricao}, debito{id,descricao},
status{id,descricao,cor}, statusBloqueio[], cadastro{id,nome,razaoSocial,ie,...},
controles, variante, categorias[], saldoEstoque[], imagemPrincipal, imagens[],
itsFull (bool), totalFisico, totalDisponivel, totalReservado, totalEnderecado,
totalEntrada, totalSaidas, totalEntradaProgramada
```
- Escala real observada: **6.890 produtos / 304 páginas** a 25/pág. `quantidadeRegistros` é honrado
  **até 100** (200/500 são ignorados e caem para 25) → use 100 para reduzir a ~76 páginas. Para
  varrer tudo, itere até `quantidadePaginas`.
- ⚠️ **Filtros de empresa/cadastro são IGNORADOS neste endpoint.** O request declara `cnpj`, `cpf`,
  `cadastro`, `codigoCadastro`, `nomeCadastro`, `descricaoCadastro`, mas a API **não os aplica**
  (comprovado ao vivo: total permanece 6.890 com qualquer um). Já os filtros de **produto**
  (`descricaoProduto`, `codigoProduto`, `statusProduto`) **funcionam**. Como o WMS é multi-tenant,
  para listar só os produtos de uma empresa é preciso **filtrar no cliente** por
  `produto.cadastro.cnpj`/`cadastro.cpf` (só dígitos). `webServiceGetSaldoEstoque` também **não** tem
  campo de empresa. (Uma apikey emitida por CMIG pode já vir escopada — não comprovado; manter o
  filtro client-side como salvaguarda.)

## webServiceGetSaldoEstoque — saldo por produto (FONTE REAL do estoque)
**Escopo:** ✅ **já vem escopado ao(s) depósito(s) da CONTA** — com a apikey de uma empresa retorna
só o estoque dela (ex.: MIG → 52 linhas, todas do depósito `ESTOQUE_PADRÃO_MIG`), diferente do
`GetProduto` (que é multi-tenant). Ou seja, **não precisa filtrar por empresa** aqui.

**Request (filtros — os úteis):**
- `codigoProduto` (string) ⚠️ **é este o filtro por produto** — **não** existe `codigoSKU` aqui.
  Alternativas: `codigoItem`, `idProduto`, `codigoBarrasProduto`, `descricaoProduto`. Sem filtro,
  retorna todo o estoque da conta (paginado, `quantidadeRegistros` até 100).
- filtros de lote (`numeroLote`, `dataValidade*`), depósito/armazém, datas, paginação.

**Response** (`corpo.body.dados[]`), campos por linha (uma por produto × depósito × lote):
`pro_produto_id` (== `GetProduto.id`), `codigo` (SKU), `saldo` (físico), `saldodisponivel`,
`saldoreservado`, `saldoentrada`, `saldosaida`, `saldovirtual`, `saldopendente`, `descricaoDeposito`,
`totalSemReserva`. **Valores são strings** (ex.: `"300.0000"`, `"0.00000"`) — converta para número.
Um produto pode ter **várias linhas** (depósitos/lotes) → **some** por `pro_produto_id`.

> ⚠️ **Bug conhecido no Drop:** `get_saldo_estoque` envia `{"codigoSKU": sku}`, campo inexistente →
> o filtro é ignorado e volta o saldo geral. Use `codigoProduto`.

## webServicePostEntrada — entrada de estoque (recebimento simples)
**Request:** `quantidade*`, `codigoProduto*`, `numeroLote`, `codigoDeposito`, `dataValidade`,
`serialNumber`. Para entrada via XML de NF-e, ver `webServicePostEntradaProgramadaXML` (Produto) e
`webServicePostEntradaProgramada` (Recebimento, em `transporte-recebimento.md`).

## Outras funções úteis do módulo
- `webServicePostVariacao` — cadastra variação de um produto (SKU da variação).
- `webServiceGetLote` / `webServicePostLote` / `webServicePutLote` — controle de lotes.
- `webServiceGetReserva` — reservas de estoque; `webServiceGetSaida` — saídas.
- `webServiceGetSerialNumber` — números de série.
- `webServiceGetCategoria` / `Post` / `Put` / `Delete` + `webServiceRelacionarProdutoCategoria` —
  categorização.
- `webServiceGetEntrada` / `webServiceGetInfoEntrada` — consulta de entradas.

## Mapeamento com o Sistema Drop
- Cada `OrderItem.sku` / variação vira um `codigoSKU` no eShip (pré-cadastro via
  `push_cmig_products` e `upsert_produto`).
- EAN (`gtin`) resolvido do `CMIGProduct.ean`/`CatalogProduct.ean`.
- Saldo físico do WMS é a fonte de verdade — a tela "Produtos (eShip)" lê `GetProduto`
  (info+estoque) e `GetSaldoEstoque`.
