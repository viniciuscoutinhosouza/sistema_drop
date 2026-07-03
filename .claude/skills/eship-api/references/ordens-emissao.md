# Módulo Ordem — ordem de saída, anexos, emissão, status

Todas as chamadas: `POST /?api&funcao=<Nome>`. Schemas do `Ordem.json` + shapes reais.

## webServicePostOrdem — criar ordem de saída (expedição)
**Request** (`*` = obrigatório):
- `numeroOrigem*` (string) — sua chave de correlação (nº do pedido no seu sistema).
- `codigoArmazemOrigem*` (string) — código do armazém.
- `cadastroDestinatario*` (object):
  - `cnpjDestinatario` **ou** `cpfDestinatario`, `nomeDestinatario`, `razaoSocialDestinatario`, `rg`
  - `contato[]`: `{ nome, email, telefone }`
  - `endereco`: `{ municipio*, estado*, bairro*, logradouro*, cep*, numero, complemento, telefone }`
- `produtos*` (array): cada item:
  - `codigoProduto*` (string, = SKU), `quantidadeProduto*` (integer), `loteProduto`
  - `infos` (object): `valorunitrioproduto`, `valortotalproduto`, `identificadorexterno`,
    `nmerolinha`, `norigem`, `ndacompra`, `regraempilhamento`, `mercadofull`
    > ⚠️ Essas grafias "estranhas" (`valorunitrioproduto`, `nmerolinha`) **são os nomes reais do
    > spec** — não são bug. Manter exatamente assim.
- `infosOrdem` (array de 1 objeto): metadados com chaves prefixadas `ORD...` **com espaços/acentos**,
  ex.: `"ORDCanal de Venda"`, `"ORDValor da ordem"`, `"ORDNº da Compra Canal de Venda"`, `"ORDChave"`
  (chave de acesso NF-e), `"ORDSerie da nota"`, `"ORDData de emissão da nota"`, `"ORDValor Frete"`,
  `"ORDPeso"`, `"ORDRota"`, `"ORDPrazo"`, `"ORDUrl externa"`... (dezenas de campos opcionais — todos
  string). Enviar só os que fizerem sentido.
- opcionais: `numeroCompra`, `idTipo`/`tipoOrdem`, `codigoDepositoReserva`, `reservar`,
  `transporte{nomeTransporte, codigoTransporte*}`, `observacao`, `idFila`/`descricaoFila`,
  `dataSaida`, `codigoRastreamento`, `ignorarOrdemCancelada`.

**Response:** `{ "ordem": { id, status{id,descricao}, idStatus, anexos, produtosOrdem[], ... } }`.
> ⚠️ O id da ordem é **`ordem.id`** (aninhado). Extrair o topo (`resp["ordem"]`) devolve o objeto
> inteiro — bug atual do `extract_order_id`.

## webServicePostOrdemPorXml — criar ordem a partir do XML da NF-e
**Request:** `tipoOrdem*` (integer), `cnpjRemetente`, `idArmazem`/`codigoArmazem`, `idFila`/
`descricaoFila`, `codigoDepositoReserva`, `conteudo` (XML como string) **ou** `url` (link do XML).

## webServiceGetOrdem — consultar ordens (paginado)
**Request:** filtros ricos + **`incluirInfo*` (boolean, OBRIGATÓRIO)** + paginação. Filtros úteis:
- `numeroOrigem` (string) — ✅ filtra pela sua chave de correlação.
- `ordem` (string, id do eShip), `statusOrdem` (integer, ver tabela), `tipoOrdem`,
  `cnpj`/`cpf`, `codigoCadastro`, datas de lançamento/embarque/atualização, `codigoTransporte`.

> ⚠️ **Bug conhecido:** o sync do Drop chama `GetOrdem` só com `{numeroOrigem}` e **não envia
> `incluirInfo`** (obrigatório). Além disso a resposta é uma **lista** em `corpo.body.dados[]` — o
> status está em `dados[0].status.id`, não no topo.

**Response:** `corpo.body.dados[]`, cada ordem com (campos úteis):
```
id, dataHora, dataHoraAtualizacao, observacao, remetente, destinatario,
enderecoRemetente, enderecoDestinatario, status{id,descricao,cor}, idStatus,
tipo{id,descricao} (=empresa/cliente no tenant multi-empresa), armazem, anexos[],
produtosOrdem[]{id,produto,quantidade,idProduto,...}, reservas[], historico,
valorTotal, nfeReferencia, falhas
```
Nota: `numeroOrigem` **não** volta no corpo da ordem; a correlação é feita pelo filtro de request.

## Tabela de status da ordem (`status.id → descricao`) — REAL, mapear por id
| id | descricao (latin-1) | Significado | shipment_status sugerido (Drop) |
|---:|---|---|---|
| 1 | Lançado | ordem criada | `handling` |
| 2 | Emitido | NF emitida | `handling` (ou `ready_to_ship`) |
| 3 | Em operação | em separação/picking | `handling` |
| 6 | Aguardando Expedição | separada, aguardando envio | `ready_to_ship` (`separated`) |
| 7 | Em Expedição | em expedição/despacho | `shipped` |
| 8 | Concluída/Despachada | despachada (terminal) | `shipped`/`delivered` |
| 10 | Cancelada | cancelada | `cancelled` |
| 4,5,9,11+ | (sem ordens na amostra) | confirmar em homolog | — |

> `webServiceGetStatusObjeto` (que daria o catálogo completo) retorna **MAP0014** no tenant
> `armazenaki`. Para completar o enum, filtre `GetOrdem` por `statusOrdem` = 1..N e leia
> `dados[0].status.descricao`. **Nunca** mapeie por texto (acento/encoding) — use o `id`.

## webServicePostArquivoOrdem — anexar NF-e / etiqueta / DANFE
**Request (campos reais):** `numeroOrigem` **ou** `codigoOrdem` (identifica a ordem),
`codigoArmazem`, `arquivoBase` (conteúdo em **Base64**) **ou** `arquivo`, `extensao` (ex.: `"xml"`,
`"pdf"`, `"zpl"`), `mimeType`, e as **flags** `inserirFiscal`, `atualizarTransporte`,
`cadastrarTransporte` (strings `"1"/"2"`).
> ⚠️ **Não existe `idTipoAnexo`** no schema real. O tipo do anexo é inferido pelas flags/extensão:
> - NF-e (XML fiscal): `inserirFiscal="1"` + `atualizarTransporte="1"` + `extensao="xml"`.
> - Etiqueta: enviar sem `inserirFiscal` (PDF/ZPL). O código atual manda `idTipoAnexo=4/7`
>   (constantes inexistentes) — corrigir para as flags.
- Conferir anexos existentes: `webServiceGetAnexosOrdem` (aceita `ordem`/`numeroOrigem`).

## Cancelar / estornar / emissão / histórico
- **`webServiceCancelaOrdem`** ⚠️ (nome correto — **sem "r"**; o código usa `webServiceCancelarOrdem`,
  que **não existe**). Request = filtros de ordem (aceita `numeroOrigem`).
- `webServiceEstornarOrdem` — estorna (reverte) a ordem.
- `webServicePostEmissao` / `webServiceGetEmissao` / `webServiceDeleteEmissao` — emissão de NF pelo
  próprio WMS (avaliar vs. emissão própria SEFAZ do Drop, ADR-0015).
- `webServiceGetFalhasOrdem` — falhas de processamento (aceita `numeroOrigem`).
- `webServiceGetOrdemHistorico` / `webServiceGetInfosOrdem` / `webServiceGetBackOrder` — histórico e
  metadados.
- `webServicePostOrdemTransferencia` / `webServiceGerarTransformacao` — transferências.

## Canais (`idFila`) usados no Drop
`61=CORREIOS`, `60=MELI FULL`, `58=AMAZON FULL`, `52=SHOPEE PT`, `54=MELI FLEX` (confirmar no
armazém via `webServiceGetFilaOperacao`/tipoOrdem antes de usar em produção).
