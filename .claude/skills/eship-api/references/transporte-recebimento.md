# Módulos Transporte e Recebimento

Duas áreas que a integração atual do Drop ainda **não** explora, mas que são a fonte real de
rastreamento (Transporte) e do fluxo de entrada de mercadoria (Recebimento).

## Transporte (68 funções) — rastreamento, embarque, rota, remessa

O **rastreio real** (código de rastreamento / status de transporte) vive aqui, não no `GetOrdem`.
Fluxo de expedição do WMS: ordem → volume → **embarque** (por rota) → **remessa** → expedição.

### Consulta (Get)
- `webServiceGetTransporte` — dados do transporte/transportadora. Request: `codigoTransporte`,
  `nomeTransporte`, `transporte` (id), `statusTransporte`, `cadastroTransporte` + paginação.
- `webServiceGetEmbarque` — embarques (agrupam volumes por rota/doca).
- `webServiceGetRota` / `webServiceGetRotaObjeto` — rotas e objetos vinculados.
- `webServiceGetRemessa` — remessas.
- `webServiceGetDadosObjetosEmbarque` — objetos de um embarque.
- `webServiceGetAvisoRecebimento` — avisos de recebimento (logística reversa/coleta).

### Rastreamento (Post/Put)
- `webServicePostRastreamentoTransporte` / `webServicePostRastreamentoTransportePorRange` —
  grava/gera códigos de rastreio.
- `webServicePutRastreamentoTransporte` — atualiza rastreio.
- ⚠️ **Não há** `webServiceGetRastreamentoTransporte` no spec — para **ler** o rastreio, use o objeto
  do transporte/embarque (`GetTransporte`/`GetEmbarque`) ou o `codigoRastreamento` que a própria
  ordem carrega (passado no `PostOrdem`).

### Operação de embarque/volume (Outros)
`webServiceExpedirObjeto`, `webServiceFecharEmbarque`/`webServiceFinalizarEmbarque`/
`webServiceLiberarEmbarque`, `webServiceAbrir/FecharVariosEmbarques`,
`webServiceCheckVolumeEmbarque(PorNota)`, `webServiceRelacionarVolumeEmbarque`,
`webServiceRelacionarEmbarqueRota`, `webServiceAgruparRotaObjetoOrdem`, `webServiceAtualizarVolume`,
`webServiceFecharVolume`, `webServiceTratarCodigoObjeto`/`webServiceTratarCodigoEmbarque` etc.
CRUD de rota/remessa/volume/abrangência via `Post/Put/Delete` correspondentes (ver
`catalogo-completo.md`).

### Uso potencial no Drop
Para popular `Order.tracking_code`/`tracking_url` de forma confiável, avaliar ler o transporte do
embarque da ordem (em vez de depender de campos adivinhados no `GetOrdem`). Backlog item 7.

## Recebimento (36 funções) — entrada programada, apontamento, devolução

Fluxo de **entrada** de mercadoria no armazém (compras, devoluções, transferências de entrada).

### webServicePostEntradaProgramada — programar recebimento (aceita XML de NF-e)
**Request:** `entradaProgramada*` (array), cada entrada:
- `quantidade*`, `codigoProduto*`, `cnpjFornecedor*`
- `nivelEntrada`, `dataEntrada`, `codigoRecebimento`, `docRecebimento`, `codigoDeposito`/
  `codigoArmazem`/`descricaoDeposito`, `unidMedida`
- `linkXml` **ou** `corpoXml` — XML da NF-e de entrada (link ou conteúdo)
- `infosEntradaProgramada[]`, `infosRecebimento[]`, `numeroPedido`, `numeroProcesso`,
  `numeroDocumento`, `atualizar`

### Consulta e apoio
- `webServiceGetRecebimento` / `webServiceGetInfosRecebimento` / `webServiceGetVolumeRecebimento` —
  consulta de recebimentos e volumes.
- `webServiceGetApontamentos` / `webServicePostApontamento` — apontamento (conferência) de itens.
- `webServiceGetEntradaProgramada` — consulta das entradas programadas.
- `webServiceGetConfrontoNotaFiscalRecebimento` — confronto NF-e × físico.
- `webServicePostArquivoRecebimento` — anexa arquivo (ex.: XML/DANFE) ao recebimento.
- `webServicePostLpn` / `webServiceDeleteLpn` — LPN (unidade logística/palete).
- Devolução: `webServiceGet/Post/Put/DeleteMotivoDevolucao`.
- Categorias/classificações: `Categoria/ClassificacaoRecebimento` (Get/Post/Put/Delete).

### Uso potencial no Drop
Automatizar a entrada de estoque quando o CMIG receber mercadoria (NF-e de entrada → `corpoXml`),
tornando o WMS ciente do físico sem digitação. Fora do escopo atual da integração.
