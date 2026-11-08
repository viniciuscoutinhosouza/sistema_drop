# Bling v3 — Produtos, Estoque, Depósitos, Categorias

> Base: `https://api.bling.com.br/Api/v3`. Header `Authorization: Bearer <access_token>`.
> Nomes de campo marcados **[confirmar]** — valide no `developer.bling.com.br/referencia` ou com um
> `GET` real antes de montar o payload de escrita.

## Produtos

| Operação | Método + caminho |
|---|---|
| Listar | `GET /produtos?pagina=1&limite=100` (filtros: `codigo`, `nome`, `tipo`, `situacao`, `idCategoria`…) |
| Obter | `GET /produtos/{idProduto}` |
| Criar | `POST /produtos` |
| Alterar | `PUT /produtos/{idProduto}` |
| Alterar situação (ativo/inativo) | `PATCH /produtos/{idProduto}/situacoes` **[confirmar]** |
| Excluir | `DELETE /produtos/{idProduto}` |

**Campos típicos do produto** (confirmar nomes/estrutura): `nome`, `codigo` (SKU), `preco`, `tipo`
(`P` produto / `S` serviço), `situacao` (`A`/`I`), `formato` (`S` simples / `V` com variações),
`unidade`, `pesoLiquido`, `pesoBruto`, `gtin` (EAN), `gtinEmbalagem`, `descricaoCurta`, `categoria.id`,
`estoque.minimo/maximo`, e **dados fiscais**: `tributacao.origem`, `ncm`, `cest`, `tributacao.*`.

**Variações:** produto `formato=V` tem produtos-filhos (grade). A criação de variação segue o mesmo
recurso `/produtos` com vínculo ao pai **[confirmar]** a estrutura exata (`variacao`/`produtoPai`).

**Imagens:** o produto aceita URLs de imagem (`imagemURL`/`midia` **[confirmar]**). O Bling **baixa** a
imagem pela URL — ela precisa ser **pública e acessível por HTTP** (no Sistema Drop, absolutize com
`PUBLIC_BASE_URL`, como já se faz para ML/Shopee).

## Estoque / Saldos

O Bling separa **saldo** (quanto tem) de **movimento** (lançamento que altera o saldo):

| Operação | Método + caminho |
|---|---|
| Consultar saldo | `GET /estoques/saldos?idsProdutos[]=...&idDeposito=...` **[confirmar]** |
| Lançar movimento (entrada/saída/balanço) | `POST /estoques` |

**Movimento (`POST /estoques`)** — campos típicos **[confirmar]**: `produto.id`, `deposito.id`,
`operacao` (`E` entrada / `S` saída / `B` balanço), `quantidade`, `preco`/`custo`, `observacoes`.

> ⚠️ **Semântica de estoque no Sistema Drop:** o SSOT de estoque é **event-sourced** local
> (ADR-0004/0019). Ao integrar com o Bling, decida a **direção** (quem é a verdade): empurrar o saldo
> local → Bling (balanço), ou puxar do Bling. **Nunca** criar dupla contagem — se o Bling também baixa
> estoque na emissão/venda, alinhe para não debitar duas vezes. Isto é decisão de arquitetura (ADR),
> não um detalhe de endpoint.

## Depósitos

| Operação | Método + caminho |
|---|---|
| Listar | `GET /depositos` |
| Obter | `GET /depositos/{idDeposito}` |

Toda operação de estoque é **por depósito**. Mapeie o **Galpão/Warehouse** do Sistema Drop ↔ o depósito
do Bling antes de sincronizar saldo.

## Categorias de produto

| Operação | Método + caminho |
|---|---|
| Listar | `GET /categorias/produtos` |
| Obter/Criar/Alterar | `GET/POST/PUT /categorias/produtos[/{id}]` |

## Boas práticas de escrita

- **Idempotência por SKU/código:** antes de `POST`, faça `GET /produtos?codigo=<sku>` para decidir
  criar vs atualizar (evita duplicar produto no Bling).
- **Respeite 3 req/s:** sincronização de catálogo em lote → fila + throttle (ver
  `webhooks-erros-limites.md`).
- **Fiscal é do Bling quando ele emite:** se a CMIG emite NF-e **pelo Bling**, os campos fiscais do
  produto (NCM/CEST/origem/tributação) precisam estar corretos **lá**. Se emite pela emissão própria
  SEFAZ do Sistema Drop (ADR-0015/0028), o Bling pode ser só espelho de catálogo/estoque — **defina o
  papel do Bling por CMIG** antes de sincronizar.
