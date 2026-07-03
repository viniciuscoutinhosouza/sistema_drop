# Catálogo completo — 289 funções WMS (por módulo e verbo)

Fonte: OpenAPI oficial `https://swagger.eship.com.br/docs/WMS/<Modulo>.json`. Todas as funções são
`POST /?api&funcao=<Nome>`. ⚠️ Estar no spec **não garante** que a função esteja habilitada no
tenant (pode retornar `MAP0014`). Para o schema request/response de cada uma, abra o `<Modulo>.json`
e procure o path `/?api&funcao=<Nome>`.

## Produto (36)
- **Get:** `webServiceGetProduto`, `webServiceGetCategoria`, `webServiceGetCategoriaLote`,
  `webServiceGetEntrada`, `webServiceGetInfoEntrada`, `webServiceGetLote`, `webServiceGetReserva`,
  `webServiceGetSaida`, `webServiceGetSaldoEstoque`, `webServiceGetSerialNumber`
- **Post:** `webServicePostProduto`, `webServicePostVariacao`, `webServicePostCategoria`,
  `webServicePostCategoriaLote`, `webServicePostEntrada`, `webServicePostEntradaProgramadaXML`,
  `webServicePostInfoEntrada`, `webServicePostLote`, `webServicePostProdutoFornecedor`
- **Put:** `webServicePutProduto`, `webServicePutCategoria`, `webServicePutCategoriaLote`,
  `webServicePutLote`
- **Delete:** `webServiceDeleteProduto`, `webServiceDeleteCategoria`, `webServiceDeleteCategoriaLote`
- **Outros:** `webServiceExcluirRelacaoProdutoCategoria`, `webServiceExcluirRestricaoCategoriaProduto`,
  `webServiceApagarBloqueios`, `webServiceConfigurarRestricaoProdutoArmazem`,
  `webServiceDuplicarProduto`, `webServiceEditarConfiguracaoProduto`,
  `webServiceRelacionarCategoriaProduto`, `webServiceRelacionarProdutoCategoria`,
  `webServiceRelacionarProdutoPreco`, `webServiceTransferirSaldoTotalListarOcupacoes`

## Ordem (20)
- **Get:** `webServiceGetOrdem`, `webServiceGetAnexosOrdem`, `webServiceGetBackOrder`,
  `webServiceGetEmissao`, `webServiceGetFalhasOrdem`, `webServiceGetInfosOrdem`,
  `webServiceGetOrdemHistorico`
- **Post:** `webServicePostOrdem`, `webServicePostOrdemPorXml`, `webServicePostOrdemTransferencia`,
  `webServicePostArquivoOrdem`, `webServicePostEmissao`
- **Put:** `webServicePutOrdem`
- **Delete:** `webServiceDeleteOrdem`, `webServiceDeleteEmissao`
- **Outros:** `webServiceCancelaOrdem` ⚠️(nome correto, sem "r"), `webServiceEstornarOrdem`,
  `webServiceGerarTransformacao`, `webServiceEmitirOrdemPorProduto`, `webServiceInfoOrdem`

## Transporte (68) — o rastreio/expedição real mora aqui
- **Get:** `webServiceGetTransporte`, `webServiceGetEmbarque`, `webServiceGetRota`,
  `webServiceGetRotaObjeto`, `webServiceGetRemessa`, `webServiceGetAvisoRecebimento`,
  `webServiceGetDadosObjetosEmbarque`
- **Post:** `webServicePostTransporte`, `webServicePostEmbarque`, `webServicePostRota`,
  `webServicePostRemessa`, `webServicePostRastreamentoTransporte`,
  `webServicePostRastreamentoTransportePorRange`, `webServicePostAbrangenciaTransporte`,
  `webServicePostAvisoRecebimento`
- **Put:** `webServicePutTransporte`, `webServicePutEmbarque`, `webServicePutRota`,
  `webServicePutRemessa`, `webServicePutRastreamentoTransporte`, `webServicePutAvisoRecebimento`,
  `webServicePutHorarioColetaTransporte`, `webServicePutInsumoVolume`, `webServicePutLimitadorTransporte`
- **Delete:** `webServiceDeleteTransporte`, `webServiceDeleteEmbarque`, `webServiceDeleteRota`,
  `webServiceDeleteRotaObjeto`, `webServiceDeleteRemessa`, `webServiceDeleteVolume`,
  `webServiceDeleteAbrangenciaTransporte`, `webServiceDeleteMunicipioRota`,
  `webServiceDeleteRastreamentoTransporte`
- **Outros (28):** embarque/volume/rota (`webServiceExpedirObjeto`, `webServiceFecharEmbarque`,
  `webServiceFinalizarEmbarque`, `webServiceLiberarEmbarque`, `webServiceAbrirVariosEmbarques`,
  `webServiceFecharVariosEmbarques`, `webServiceCheckVolumeEmbarque`,
  `webServiceCheckVolumeEmbarquePorNota`, `webServiceRelacionarVolumeEmbarque`,
  `webServiceRelacionarEmbarqueRota`, `webServiceRelacionarEmbarqueFilaOperacao`,
  `webServiceRelacionarDocaTransporte`, `webServiceRelacionarMunicipioRota`,
  `webServiceAgruparRotaObjetoOrdem`, `webServiceAgruparRotaObjetoRecebimento`,
  `webServiceAgruparRotaObjetoVolumeRecebimento`, `webServiceCriarRelacaoRotaObjeto`,
  `webServiceCriarRelacaoRotaObjetoOrdem`, `webServiceApagarRelacaoRotaObjeto`,
  `webServiceExcluirObjetoRotaEmbarque`, `webServiceExcluirVolumeDoEmbarque`,
  `webServiceExcluirVolumeEmbarque`, `webServiceAjustarCategoriaVolume`, `webServiceAjustarRemessa`,
  `webServiceAvancarRemessa`, `webServiceAtualizarVolume`, `webServiceFecharVolume`,
  `webServiceReiniciaChecagemVolumes`, `webServiceTratarCodVolumeEmbarque`,
  `webServiceTratarCodigoEmbarque`, `webServiceTratarCodigoObjeto`, `webServiceDesfazerRegistro`,
  `webServiceDesrelacionarEmbarqueRota`, `webServiceCancelarAvisoRecebimento`,
  `webServiceFinalizarAvisoRecebimento`)

## Recebimento (36)
- **Get:** `webServiceGetRecebimento`, `webServiceGetApontamentos`, `webServiceGetEntradaProgramada`,
  `webServiceGetCategoriaRecebimento`, `webServiceGetClassificacaoRecebimento`,
  `webServiceGetConfrontoNotaFiscalRecebimento`, `webServiceGetInfosRecebimento`,
  `webServiceGetMotivoDevolucao`, `webServiceGetTipoRecebimento`, `webServiceGetVolumeRecebimento`
- **Post:** `webServicePostRecebimento`, `webServicePostEntradaProgramada`,
  `webServicePostApontamento`, `webServicePostArquivoRecebimento`, `webServicePostLpn`,
  `webServicePostCategoriaRecebimento`, `webServicePostClassificacaoRecebimento`,
  `webServicePostInfoVolumeRecebimento`, `webServicePostMotivoDevolucao`
- **Put:** `webServicePutRecebimento`, `webServicePutConfiguracaoRecebimento`,
  `webServicePutCategoriaRecebimento`, `webServicePutMotivoDevolucao`,
  `webServicePutStatusTipoRecebimento`
- **Delete:** `webServiceDeleteRecebimento`, `webServiceDeleteEntradaProgramada`,
  `webServiceDeleteLpn`, `webServiceDeleteCategoriaRecebimento`,
  `webServiceDeleteClassificacaoRecebimento`, `webServiceDeleteMotivoDevolucao`
- **Outros:** `webServiceInfoRecebimento`, `webServiceInfoVolumeRecebimento`,
  `webServiceGravarConfiguracaoRecebimento`, `webServiceRelacionarCategoriaRecebimento`,
  `webServiceDesfazerRestricaoCategoriaRecebimento`,
  `webServiceDesfazerRestricaoCategoriaRecebimentoSetor`

## Armazém (47)
- **Get:** `webServiceGetArmazem`, `webServiceGetArea`, `webServiceGetDeposito`, `webServiceGetDoca`,
  `webServiceGetEnderecamento`, `webServiceGetHistoricoMovimentacao`,
  `webServiceGetHistoricoMovimentacaoRecebimento`, `webServiceGetHostArmazem`,
  `webServiceGetMovimentador`, `webServiceGetOcupacaoMovimentador`, `webServiceGetOcupacaoProduto`,
  `webServiceGetPosicaoFixa`, `webServiceGetTipoArmazem`, `webServiceGetTipoDeposito`
- **Post:** `webServicePostArmazem`, `webServicePostDeposito`, `webServicePostDoca`,
  `webServicePostFilaOperacao`, `webServicePostMovimentador`, `webServicePostOcupacaoProduto`,
  `webServicePostTipoDeposito`, `webServicePostTipoOrdem`, `webServicePostConfiguracaoOrdem`
- **Put:** `webServicePutArmazem`, `webServicePutDeposito`, `webServicePutFilaOperacao`,
  `webServicePutMovimentador`, `webServicePutPosicao`, `webServicePutTipoDeposito`,
  `webServicePutTipoOrdem`
- **Delete:** `webServiceDeleteArmazem`, `webServiceDeleteDeposito`, `webServiceDeleteDoca`,
  `webServiceDeleteEnderecamento`, `webServiceDeleteFilaOperacao`, `webServiceDeleteMovimentador`,
  `webServiceDeleteTipoDeposito`, `webServiceDeleteConfiguracaoOrdem`
- **Outros:** `webServiceTransferirOcupacaoProduto`, `webServiceConfigurarDebitoOcupacao`,
  `webServiceConfigurarEncaminhamento`, `webServiceEditarStatusMovimentador`,
  `webServiceLiberarMovimentador`, `webServiceGravarConfiguracaoPosCheckout`,
  `webServiceGravarConfiguracaoPosPicking`, `webServiceRelacionarDocaArea`,
  `webServiceRelacionarHostArmazem`

## Sistema (26)
- **Get:** `webServiceGetStatusObjeto` ⚠️(MAP0014 no tenant armazenaki), `webServiceGetInfosObjeto`,
  `webServiceGetFuncao`, `webServiceGetLog`, `webServiceGetNivel`, `webServiceGetMeta`,
  `webServiceGetMensageria`, `webServiceGetMensageriaPopup`, `webServiceGetAppSubProcesso`,
  `webServiceGetComponenteFront`, `webServiceGetRelacaoParametrosGateway`
- **Post/Put/Delete:** `webServicePost/Put/Delete` de `Meta`, `Log`, `Mensageria`,
  `MensageriaPopup`, `AppSubProcesso`, `ComponenteFront`, `InfoObjeto`, `RelacaoParametrosGateway`

## Cadastro (20)
- **Get:** `webServiceGetCadastro`, `webServiceGetContato`, `webServiceGetEndereco`,
  `webServiceGetInfoCadastro`
- **Post:** `webServicePostCadastro`, `webServicePostContato`, `webServicePostEndereco`,
  `webServicePostClassificacaoCadastro`, `webServicePostInfoCadastro`, `webServicePostTipoCadastro`
- **Put:** `webServicePutCadastro`, `webServicePutEndereco`, `webServicePutTipoCadastro`
- **Delete:** `webServiceDeleteCadastro`, `webServiceDeleteEndereco`,
  `webServiceDeleteClassificacaoCadastro`, `webServiceDeleteTipoCadastro`
- **Outros:** `webServiceDesativarContato`, `webServiceConfigurarRestricaoCadastroArmazem`,
  `webServiceGravarConfiguracaoCadastro`

## Usuário (19)
- **Get:** `webServiceGetUsuario`, `webServiceGetApikey`, `webServiceGetGrupoUsuario`,
  `webServiceGetTipoUsuario`
- **Post/Put/Delete:** `webServicePostUsuario`, `webServicePutUsuario`, `webServiceDeleteUsuario`,
  `webServiceAtualizarServidor`, `webServiceAlterarSenha`
- **Relações/config:** `webServiceRelacionarArmazemUsuario`, `webServiceRelacionarCadastroUsuario(s)`,
  `webServiceRelacionarFuncaoUsuario`, `webServiceRelacionarModuloUsuario`,
  `webServiceRelacionarProcessoUsuario`, `webServiceRelacionarAvisoUsuario`,
  `webServiceSelecionarArmazemUsuario`, `webServiceFavoritarFuncaoUsuario`,
  `webServiceGravarConfiguracaoUsuario`

## Inventário (15)
- **Get:** `webServiceGetInventario`, `webServiceGetContagemInventario`, `webServiceGetCheckContagem`,
  `webServiceGetPlanoInventario`, `webServiceGetPorcentagemContadaInventario`,
  `webServiceGetTotalizadoInventario`, `webServiceGetTotalizadoRequisicao`
- **Post/Put/Delete:** `webServicePost/Put` de `Inventario`, `ContagemInventario`;
  `webServicePostPlanoInventario`; `webServiceDelete` de `Inventario`, `ContagemInventario`,
  `CheckContagem`

## Precificação (1) / Requisição (1)
- `webServiceGetPrecificacao` · `webServiceGetReqContagemPosicao`

## Operação
- Grupo listado no swagger, mas `Operacao.json` → **HTTP 404** (não servido no momento).
