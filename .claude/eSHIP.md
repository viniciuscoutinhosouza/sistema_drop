



Ordem
{
"ordem": null,
"tipoFrete": null,
"statusOrdem": null,
"tipoOrdem": null,
"dataLancamento": null,
"dataFinalLancamento": null,
"periodoLancamentoHora": null,
"periodoLancamentoHoraDiaUtil": null,
"periodoLancamentoHoraMais": null,
"periodoLancamento": null,
"periodoEmbarqueOrdem": null,
"numeroOrigem": null,
"infoFila": null,
"infoValor": null,
"infoValorMenorQue": null,
"infoValorMaiorQue": null,
"preVolumetria": null,
"preVolumetriaMaiorQue": null,
"preVolumetriaMenorQue": null,
"preVolumetriaPeso": null,
"preVolumetriaPesoMaiorQue": null,
"preVolumetriaPesoMenorQue": null,
"dataEmbarqueOrdem": null,
"dataFinalEmbarqueOrdem": null,
"infoNotNull": null,
"infoNull": null,
"periodoFaturamento": null,
"infoFilaTexto": null,
"infoNumeroNota": null,
"periodoLancamentoMesAtualFinal": null,
"periodoLancamentoUltimoMesInicial": null,
"periodoEmbarqueMesAtualFinal": null,
"periodoEmbarqueUltimoMesInicial": null,
"periodoFaturamentoMesAtualFinal": null,
"periodoFaturamentoUltimoMesInicial": null,
"periodoLancamentoMaiorQue": null,
"dataHoraLancamento": null,
"dataHoraFinalLancamento": null,
"dataHoraInicialAtualizacao": null,
"dataHoraFinalAtualizacao": null,
"criadoPor": null,
"observacao": null,
"dadoInfo": null,
"likeInfo": null,
"tipoInfo": null,
"anexosDisponiveis": null,
"anexosIndisponiveis": null,
"cadastro": null,
"codigoCadastro": null,
"cadastroSuperior": null,
"nomeCadastro": null,
"descricaoCadastro": null,
"cnpj": "59951479000275",
"cpf": null,
"armazem": null,
"tipoArmazem": null,
"statusArmazem": null,
"codigoTransporte": null,
"nomeTransporte": null,
"transporte": null,
"transporteMultiplo": null,
"statusTransporte": null,
"cadastroTransporte": null,
"incluirInfo": null,
"pagina": "1",
"quantidadeRegistros": "25",
"ordenacao": 2,
"incrementar": null,
"completo": 2
}


{
    "codigoItem": null,
    "codigoProdutoFornecedor": null,
    "codigoProduto": 320,
    "idProduto": null,
    "codigoBarrasProduto": null,
    "descricaoProduto": null,
    "tipoProduto": null,
    "embalagem": null,
    "statusProduto": null,
    "debito": null,
    "controles": null,
    "categoria": null,
    "multiplasCategorias": null,
    "dataInicialCriacaoProduto": null,
    "dataFinalCriacaoProduto": null,
    "periodoCriacaoProduto": null,
    "pagina": "1",
    "cnpj": "59951479000275",
    "quantidadeRegistros": "25",
    "ordenacao": 2,
    "completo": 2
}
 

-> envio de ordem para pessoa física:
 
{
	"numeroOrigem": "2000017245325174",
	"codigoArmazemOrigem": "2",
	"idTipo": 104,
	"tipoOrdem": "MIG IMPORTACOES",
	"cadastroDestinatario": {
		"cpfDestinatario": "77494915036",
		"nomeDestinatario": "RAQUEL CAMPANHA",
		"contato": [
			{
				"nome": "RAQUEL CAMPANHA",
				"email": "",
				"telefone": ""
			}
		],
		"endereco": {
			"logradouro": "Rua Adolfo Reile 286",
			"numero": "286",
			"complemento": "Apto 125 B",
			"bairro": "Jardim Celeste",
			"municipio": "São Paulo",
			"estado": "SP",
			"cep": "04195070"
		}
	},
	"infosOrdem": [
		{
			"ORDCanal de Venda": "mercadolivre",
			"ORDValor da ordem": "40.01",
			"ORDNº da Compra Canal de Venda": "2000017245325174",
			"ORDChave": ""
		}
	],
	"produtos": [
		{
			"codigoProduto": "5468",
			"quantidadeProduto": 1,
			"infos": {
				"valorunitrioproduto": "40.01",
				"valortotalproduto": "40.01",
				"nmerolinha": "1"
			}
		}
	]
}



-> envio de ordem para pessoa jurídica: 
 
{
	"numeroOrigem": "2000017245325174",
	"codigoArmazemOrigem": "2",
	"idTipo": 104,
	"tipoOrdem": "MIG IMPORTACOES",
	"cadastroDestinatario": {
		"cnpjDestinatario": "{cpnj do destinatário}",
		"nomeDestinatario": "RAQUEL CAMPANHA",
		"contato": [
			{
				"nome": "RAQUEL CAMPANHA",
				"email": "",
				"telefone": ""
			}
		],
		"endereco": {
			"logradouro": "Rua Adolfo Reile 286",
			"numero": "286",
			"complemento": "Apto 125 B",
			"bairro": "Jardim Celeste",
			"municipio": "São Paulo",
			"estado": "SP",
			"cep": "04195070"
		}
	},
	"infosOrdem": [
		{
			"ORDCanal de Venda": "mercadolivre",
			"ORDValor da ordem": "40.01",
			"ORDNº da Compra Canal de Venda": "2000017245325174",
			"ORDChave": ""
		}
	],
	"produtos": [
		{
			"codigoProduto": "5468",
			"quantidadeProduto": 1,
			"infos": {
				"valorunitrioproduto": "40.01",
				"valortotalproduto": "40.01",
				"nmerolinha": "1"
			}
		}
	]
}


-> anexar nota fiscal na ordem:
 
/v3/?api&funcao=webServicePostArquivoOrdem
 
{
	"codigoArmazem": "2",
	"numeroOrigem": "{número de origem da ordem gerada}",
	"inserirFiscal": "2",
	"arquivoBase": "Arquivo em base64",
	"extensao": "xml"
}
 
-> anexar etiqueta em pdf:
 
/v3/?api&funcao=webServicePostArquivoOrdem
 
{
	"codigoArmazem": "2",
	"numeroOrigem": "{número de origem da ordem gerada}",
	"inserirFiscal": "2",
	"arquivoBase": "Arquivo em base64",
	"extensao": "pdf"
}
 


-> adicionar um novo produto
 
/v3/?api&funcao=webServicePostProduto
 
{
"codigoSKU": "Teste1007",
"descricao": "Teste1007",
"gtin": "Teste1007",
"cnpjCadastro": "59951479000275",
"tipo": 1,
"descricaoTipo": null,
"status": null,
"descricaoStatus": null,
"embalado": 1,
"unidadePeso": 6,
"descricaoUnidadePeso": null,
"pesoLiquido": null,
"pesoBruto": null,
"pesoCubico": null,
"unidadeReferencia": null,
"descricaoUnidadeReferencia": null,
"unidadeMedida": null,
"descricaoUnidadeMedida": null,
"largura": null,
"comprimento": null,
"altura": null,
"caracteristicas": null,
"controles": null,
"descricaoControles": null,
"debitoLotes": null,
"descricaoDebitoLotes": null
}
 

