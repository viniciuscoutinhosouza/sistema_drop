# Integração ERP → E-SHIP (Armazenaki) — Guia Completo de Endpoints

## 1. Autenticação

A API E-SHIP utiliza **apikey** passada no **header** de todas as requisições.

```http
Header: api: <SUA_APIKEY>
```

**Exemplo:**
```json
{ "api": "1234567890abcdef" }
```

- A apikey é gerada dentro do painel E-SHIP e é única por usuário/empresa.
- Sem ela, nenhuma chamada à API será autenticada.

---

## 2. Base URL

```
https://<subdomain>.eship.com.br/v3/?api&funcao=<webService>
```

> Substitua `<subdomain>` pelo subdomínio da sua conta (ex: `armazenaki`).

---

## 3. Endpoint — Cadastrar Produto

### 3.1 Informações Gerais

| Campo        | Valor |
|---|---|
| URL          | `https://<subdomain>.eship.com.br/v3/?api&funcao=webServicePostProduto` |
| Método HTTP  | `POST` |
| Content-Type | `application/json` |

---

### 3.2 Parâmetros da Requisição

| Campo | Tipo | Tamanho | Obrigatório | Descrição / Valores |
|---|---|---|---|---|
| `codigoSKU` | STRING | 15 | ✅ Sim | Código SKU único do produto no seu sistema |
| `descricao` | STRING | 200 | ✅ Sim | Descrição/nome do produto |
| `gtin` | STRING | 15 | Opcional | Código de barras (EAN/GTIN) |
| `cnpjCadastro` | STRING | 50 | ✅ Sim | CNPJ do lojista/empresa |
| `tipo` | INT | 11 | Opcional | Tipo do produto: `5`=Insumo, `1`=Simples, `2`=Virtual |
| `descricaoTipo` | STRING | 255 | Opcional | Descrição do tipo (texto livre) |
| `status` | INT | 11 | Opcional | `2`=Bloqueado, `3`=Desativado, `5`=Em ajuste de inventário, `4`=Em inventário, `1`=Normal |
| `descricaoStatus` | STRING | 255 | Opcional | Descrição do status |
| `embalado` | INT | 11 | ✅ Sim | `1`=Embalado, `2`=Não Embalado |
| `unidadePeso` | INT | 11 | Opcional | `5`=kilograma, `6`=grama, `7`=tonelada |
| `descricaoUnidadePeso` | STRING | 255 | Opcional | Descrição da unidade de peso |
| `pesoLiquido` | INT | 11 | Opcional | Peso líquido do produto |
| `pesoBruto` | INT | 11 | Opcional | Peso bruto do produto |
| `pesoCubico` | INT | 11 | Opcional | Peso cúbico |
| `unidadeReferencia` | INT | 11 | Opcional | `1`=pol, `2`=m, `3`=mm, `4`=cm, `5`=kg, `6`=g, `7`=ton, `8`=un, `9`=cm³, `10`=m³, `11`=mm³, `12`=m², `13`=plt, `14`=cx, `15`=mg, `16`=jar, `17`=far, `18`=L, `19`=pac, `20`=pec, `23`=mi |
| `descricaoUnidadeReferencia` | STRING | 255 | Opcional | Descrição da unidade de referência |
| `unidadeMedida` | INT | 11 | Opcional | `1`=polegada, `2`=metro, `3`=milímetro, `4`=centímetro |
| `descricaoUnidadeMedida` | STRING | 255 | Opcional | Descrição da unidade de medida |
| `largura` | INT | 11 | Opcional | Largura do produto |
| `comprimento` | INT | 11 | Opcional | Comprimento do produto |
| `altura` | INT | 11 | Opcional | Altura do produto |
| `caracteristicas` | STRING | 255 | Opcional | Características adicionais |
| `controles` | STRING | 255 | Opcional | `6`=Data Fabricação, `4`=Fracionamento, `8`=Frasqueamento, `1`=Lote, `5`=Não Baixa Saldo, `3`=Serial Number, `7`=Unitizar, `2`=Validade |
| `descricaoControles` | STRING | 255 | Opcional | Descrição dos controles |
| `debitoLotes` | INT | 11 | Opcional | `1`=FEFO, `2`=FIFO, `3`=LIFO |
| `descricaoDebitoLotes` | STRING | 255 | Opcional | Descrição do débito de lotes |

---

### 3.3 Exemplo de Payload (JSON)

```json
{
  "codigoSKU": "PROD-001",
  "descricao": "Camiseta Azul M",
  "gtin": "7891234567890",
  "cnpjCadastro": "12.345.678/0001-90",
  "tipo": 1,
  "status": 1,
  "embalado": 1,
  "unidadePeso": 5,
  "pesoLiquido": 300,
  "pesoBruto": 350,
  "largura": 30,
  "comprimento": 40,
  "altura": 2,
  "unidadeMedida": 4,
  "controles": "1"
}
```

---

## 4. Endpoint — Inserir Ordem (Pedido)

### 4.1 Informações Gerais

| Campo        | Valor |
|---|---|
| URL          | `https://<subdomain>.eship.com.br/v3/?api&funcao=webServicePostOrdem` |
| Método HTTP  | `POST` |
| Content-Type | `application/json` |

---

### 4.2 Parâmetros Principais da Ordem

| Campo | Tipo | Tamanho | Obrigatório | Descrição |
|---|---|---|---|---|
| `numeroOrigem` | STRING | 250 | ✅ Sim | Número único do pedido no seu sistema (ID do pedido no ERP) |
| `numeroCompra` | STRING | 250 | Opcional | Número da compra/nota |
| `codigoArmazemOrigem` | STRING | 25 | ✅ Sim | Código do armazém de origem (depósito de saída) |
| `idTipo` | INT | 11 | Opcional | ID do tipo/lojista |
| `tipoOrdem` | STRING | 255 | Opcional | Tipo da ordem (texto livre) |
| `codigoDepositoReserva` | STRING | 50 | Opcional | Código do depósito de reserva |
| `descDepositoDestino` | STRING | 250 | Opcional | Descrição do depósito destino |
| `codigoArmazem` | STRING | 25 | Opcional | Código do armazém |
| `reservar` | STRING | 1 | Opcional | `1`=Sim, `2`=Não |
| `ordenDependencia` | STRING | 250 | Opcional | Dependência de ordem |
| `desmembrarProduto` | STRING | 250 | Opcional | `1`=Sim, `2`=Não |

---

### 4.3 Sub-objeto `infosOrdem` (opcional)

Informações adicionais da ordem. Enviar como lista/array.

| Campo | Tipo | Descrição |
|---|---|---|
| `ORDNº da Nota venda` | STRING | Número da nota de venda |
| `ORDNº da Compra` | STRING | Número da compra |
| `ORDDeposito - Retirada` | STRING | Ex: `321`=ESTOQUE_PADRÃO_MIG |
| `ORDTipo Operação` | STRING | Tipo de operação |
| `ORDSetor` | STRING | Setor |
| `ORDFila` | STRING | Canal/fila de despacho (ex: CORREIOS, SHOPEE, etc.) |
| `ORDNº Origem` | STRING | Número de origem |
| `ORDReq. Cancelamento` | STRING | Requisição de cancelamento |
| `ORDReq. Devolução` | STRING | Requisição de devolução |
| `ORDData Faturamento(F)` | STRING | Data de faturamento físico |
| `ORDData Faturamento(I)` | STRING | Data de faturamento ideal |
| `ORDValor Nota` | STRING | Valor total da nota fiscal |
| `ORDMotivo Cancelamento` | STRING | Motivo de cancelamento |
| `ORDDepósito Destino` | STRING | Código do depósito destino |
| `ORDCod. Fiscal` | STRING | Código fiscal (CFOP) da operação |
| `ORDChave` | STRING | Chave de acesso da NF-e |
| `ORDValor Frete` | STRING | Valor do frete |
| `ORDSerie da nota` | STRING | Série da nota fiscal |
| `ORDData de emissão da nota` | STRING | Data de emissão da NF |
| `ORDSituação da nota` | STRING | Situação da nota |
| `ORDTipo de frete` | STRING | Tipo de frete |
| `ORDValor da ordem` | STRING | Valor total da ordem |
| `ORDData vinda da integracao` | STRING | Data de integração |
| `ORDData do embarque` | STRING | Data de embarque |
| `ORDPrazo` | STRING | Prazo de entrega |
| `ORDData calculo prazo` | STRING | Data de cálculo do prazo |
| `ORDUrl externa` | STRING | URL externa de rastreio |
| `ORDNº Embarque pré definido` | STRING | Número de embarque pré-definido |
| `ORDRota` | STRING | Rota de entrega |
| `ORDNº Carga` | STRING | Número da carga |
| `ORDPeso` | STRING | Peso da ordem |
| `ORDData da Compra` | STRING | Data da compra |
| `ORDCanal de Venda` | STRING | Canal de venda (marketplace, loja própria, etc.) |
| `ORDNº da Compra Ecommerce` | STRING | Número da compra no e-commerce |
| `ORDTransporte Alterado` | STRING | Transportadora alterada |
| `ORDAlterar Transporte` | STRING | Flag para alterar transporte |
| `ORDClasse Imposto` | STRING | Classe de imposto |
| `ORDNº da Compra Canal de Venda` | STRING | Número da compra no canal de venda |
| `ORDCódigo da integração do pedido Multisoft` | STRING | Código de integração Multisoft |
| `ORDNº Coleta` | STRING | Número de coleta |
| `ORDNº Máquina` | STRING | Número de máquina |
| `ORDNº Instalação` | STRING | Número de instalação |

---

### 4.4 Sub-objeto `cadastroDestinatario` (Obrigatório)

Dados do destinatário/cliente da ordem.

| Campo | Tipo | Descrição |
|---|---|---|
| `cnpjDestinatario` | STRING | CNPJ do destinatário |
| `cpfDestinatario` | STRING | CPF do destinatário |
| `nomeDestinatario` | STRING | Nome do destinatário |
| `razaoSocialDestinatario` | STRING | Razão social |
| `rg` | STRING | RG do destinatário |
| **`contato`** (LISTA) | | Lista de contatos |
| → `nome` | STRING | Nome do contato |
| → `email` | STRING | E-mail do contato |
| → `telefone` | STRING | Telefone do contato |
| **`endereco`** (OBJETO) | | Endereço de entrega |
| → `municipio` | STRING | Município/cidade |
| → `estado` | STRING | Estado (UF) |
| → `bairro` | STRING | Bairro |
| → `logradouro` | STRING | Logradouro/rua |
| → `numero` | STRING | Número |
| → `cep` | STRING | CEP |
| → `complemento` | STRING | Complemento |
| → `telefone` | STRING | Telefone de entrega |

---

### 4.5 Itens da Ordem (Array de Produtos)

| Campo | Tipo | Descrição |
|---|---|---|
| `codigoProduto` | STRING | Código SKU do produto (deve já existir no eShip) |
| `quantidadeProduto` | INT | Quantidade do produto na ordem |
| `loteProduto` | STRING | Lote do produto (se aplicável) |
| **`infos`** (OBJETO) | | Informações adicionais do item |
| → `valorunitrioproduto` | STRING | Valor unitário do produto |
| → `valortotalproduto` | STRING | Valor total do item |
| → `identificadorexterno` | STRING | ID externo do item |
| → `nmerolinha` | STRING | Número da linha do pedido |
| → `norigem` | STRING | Número de origem do item |
| → `ndacompra` | STRING | Número da compra do item |

---

### 4.6 Exemplo Completo de Payload (JSON)

```json
{
  "numeroOrigem": "PEDIDO-12345",
  "numeroCompra": "NF-98765",
  "codigoArmazemOrigem": "ESTOQUE_PADRAO",
  "cadastroDestinatario": {
    "nomeDestinatario": "João da Silva",
    "cpfDestinatario": "123.456.789-00",
    "contato": [
      {
        "nome": "João da Silva",
        "email": "joao@exemplo.com",
        "telefone": "(11) 99999-9999"
      }
    ],
    "endereco": {
      "logradouro": "Rua das Flores",
      "numero": "123",
      "complemento": "Apto 45",
      "bairro": "Centro",
      "municipio": "São Paulo",
      "estado": "SP",
      "cep": "01310-100",
      "telefone": "(11) 99999-9999"
    }
  },
  "infosOrdem": [
    {
      "ORDCanal de Venda": "Shopee",
      "ORDValor Nota": "250.00",
      "ORDValor Frete": "15.90",
      "ORDData da Compra": "2026-06-25",
      "ORDValor da ordem": "265.90"
    }
  ],
  "produtos": [
    {
      "codigoProduto": "PROD-001",
      "quantidadeProduto": 2,
      "infos": {
        "valorunitrioproduto": "125.00",
        "valortotalproduto": "250.00",
        "nmerolinha": "1",
        "identificadorexterno": "ITEM-001"
      }
    }
  ]
}
```

---

## 5. Endpoint — Inserir Ordem por XML da NF-e (DANFE)

Cria a ordem **já processando o XML da NF-e** diretamente. O eShip lê os dados do XML e popula os campos automaticamente.

### 5.1 Informações Gerais

| Campo        | Valor |
|---|---|
| URL          | `https://<subdomain>.eship.com.br/v3/?api&funcao=webServicePostOrdemPorXml` |
| Método HTTP  | `POST` |
| Content-Type | `application/json` |

### 5.2 Parâmetros da Requisição

| Campo | Tipo | Tamanho | Obrigatório | Descrição |
|---|---|---|---|---|
| `cnpjRemetente` | STRING | 14 | Opcional | CNPJ do remetente/loja |
| `idArmazem` | INT | 11 | Opcional | ID do armazém (ex: `2`=Armazenaki_Aruja) |
| `codigoArmazem` | STRING | 25 | Opcional | Código do armazém de origem |
| `tipoOrdem` | INT | 11 | ✅ Sim | ID do tipo/lojista (ver lista na plataforma) |
| `idFila` | INT | 11 | Opcional | Canal de despacho: `61`=CORREIOS, `58`=AMAZON FULL, `60`=MELI FULL, `52`=SHOPEE PONTO DE COLETA, `54`=MELI FLEX, `53`=SHEIN ENVIOS, `57`=TIKTOK PONTO DE COLETA |
| `descricaoFila` | STRING | 255 | Opcional | Descrição da fila/canal |
| `codigoDepositoReserva` | STRING | 50 | Opcional | Código do depósito de reserva |
| `conteudo` | STRING | 1000 | Opcional | **Conteúdo do XML da NF-e (string completa)** |
| `url` | STRING | 1000 | Opcional | URL pública do arquivo XML (alternativa ao campo `conteudo`) |

### 5.3 Exemplo de Payload (JSON)

```json
{
  "cnpjRemetente": "12345678000190",
  "idArmazem": 2,
  "tipoOrdem": 57,
  "idFila": 61,
  "conteudo": "<?xml version=\"1.0\" encoding=\"UTF-8\"?><nfeProc>...</nfeProc>"
}
```

---

## 6. Endpoint — Inserir Arquivo na Ordem (NF-e, Etiqueta, PDF DANFE)

Endpoint universal para envio de arquivos em uma ordem já existente. Serve para NF-e (XML ou PDF) e para **etiqueta de entrega**.

### 6.1 Informações Gerais

| Campo        | Valor |
|---|---|
| URL          | `https://<subdomain>.eship.com.br/v3/?api&funcao=webServicePostArquivoOrdem` |
| Método HTTP  | `POST` |
| Content-Type | `application/json` |

### 6.2 Parâmetros da Requisição

| Campo | Tipo | Tamanho | Obrigatório | Descrição |
|---|---|---|---|---|
| `codigoArmazem` | STRING | 255 | Opcional | Código do armazém |
| `codigoOrdem` | STRING | 255 | Opcional | Código interno da ordem no eShip |
| `numeroOrigem` | STRING | 50 | Opcional | **Número de origem do pedido no SEU sistema** (mesmo `numeroOrigem` da criação da ordem) |
| `inserirFiscal` | STRING | 3 | Opcional | `1`=Sim, `2`=Não — Se deve inserir como nota fiscal |
| `atualizarTransporte` | STRING | 3 | Opcional | `1`=Sim, `2`=Não — Se deve atualizar dados de transporte |
| `cadastrarTransporte` | STRING | 3 | Opcional | `1`=Sim, `2`=Não — Cadastrar transporte se não existir |
| `arquivo` | INDEFINIDO | 1 | Opcional | Arquivo binário (upload multipart) |
| `arquivoBase` | STRING | ilimitado | Opcional | **Arquivo em Base64** (recomendado para JSON) |
| `extensao` | STRING | 3 | Opcional | Extensão: `xml`, `pdf`, `png`, `zpl`, etc. |
| `mimeType` | STRING | 255 | Opcional | MIME type: `application/xml`, `application/pdf`, `image/png`, etc. |
| `idTipoAnexo` | INT | 11 | Opcional | **Tipo do anexo** — ver tabela abaixo |

### 6.3 Tabela de Tipos de Anexo (`idTipoAnexo`)

| Valor | Tipo | Uso |
|---|---|---|
| `4` | XMLDANFE | XML da NF-e (DANFE) — **use para enviar o XML da nota fiscal** |
| `7` | ETIQUETA | **Etiqueta de entrega/despacho** |
| `9` | XML | XML genérico |
| `2` | DOCUMENTOS / IT / POP | Documentos gerais |
| `12` | ARQUIVOS | Arquivos genéricos |
| `11` | ASSINATURA | Assinatura digital |
| `13` | CERTIFICADO | Certificado digital |
| `14` | CONFIGURAÇÃO | Configuração |
| `3` | FOTOS | Fotos |
| `6` | JSON | JSON |
| `8` | LOG | Log |
| `10` | REPORT | Relatório |
| `15` | VALORES | Valores |
| `5` | VIDEOS | Vídeos |
| `16` | ÁUDIO | Áudio |

---

### 6.4 Exemplo 1 — Enviar XML da NF-e em ordem existente

```json
{
  "numeroOrigem": "PEDIDO-12345",
  "inserirFiscal": "1",
  "atualizarTransporte": "1",
  "cadastrarTransporte": "1",
  "arquivoBase": "<XML_DA_NFe_EM_BASE64>",
  "extensao": "xml",
  "mimeType": "application/xml",
  "idTipoAnexo": 4
}
```

> **Como gerar Base64:**
> - PHP: `base64_encode(file_get_contents('nfe.xml'))`
> - JavaScript: `btoa(xmlString)`
> - Python: `base64.b64encode(xml_bytes).decode()`

---

### 6.5 Exemplo 2 — Enviar Etiqueta de Entrega (PDF)

```json
{
  "numeroOrigem": "PEDIDO-12345",
  "arquivoBase": "<ETIQUETA_PDF_EM_BASE64>",
  "extensao": "pdf",
  "mimeType": "application/pdf",
  "idTipoAnexo": 7
}
```

### 6.6 Exemplo 3 — Enviar Etiqueta ZPL (Zebra)

```json
{
  "numeroOrigem": "PEDIDO-12345",
  "arquivoBase": "<ETIQUETA_ZPL_EM_BASE64>",
  "extensao": "zpl",
  "mimeType": "text/plain",
  "idTipoAnexo": 7
}
```

---

## 7. Outros Endpoints Relevantes — ORDEM

| Serviço | funcao | Descrição |
|---|---|---|
| Consultar Ordem | `webServiceGetOrdem` | Busca status/dados de uma ordem |
| Atualizar Ordem | `webServicePutOrdem` | Atualiza dados de uma ordem |
| Cancelar Ordem | `webServiceCancelarOrdem` | Cancela uma ordem |
| Consultar Falhas Ordem | `webServiceGetFalhasOrdem` | Verifica erros de processamento |
| Consultar Arquivos Ordem | `webServiceGetArquivosOrdem` | Lista arquivos anexados |
| Inserir Arquivo na Ordem | `webServicePostArquivoOrdem` | Envia NF-e, etiqueta, PDF, etc. |
| Estornar Ordem | `webServiceEstornarOrdem` | Estorna uma ordem |

---

## 8. Outros Endpoints Relevantes — PRODUTO

| Serviço | funcao | Descrição |
|---|---|---|
| Consultar Produto | `webServiceGetProduto` | Busca dados de produto por SKU |
| Editar Produto | `webServicePutProduto` | Atualiza dados de um produto |
| Consultar Saldo Estoque | `webServiceGetSaldoEstoque` | Saldo disponível em estoque |
| Inserir Entrada | `webServicePostEntrada` | Registra entrada de estoque |
| Consultar Entradas | `webServiceGetEntradas` | Lista entradas realizadas |
| Inserir Lote | `webServicePostLote` | Cadastra lote de produto |

---

## 9. Fluxo Completo de Integração Recomendado

```
1. CADASTRAR PRODUTO
   → POST webServicePostProduto
   → Verificar se já existe com GET webServiceGetProduto antes de cadastrar

2. SINCRONIZAR ESTOQUE (opcional)
   → GET webServiceGetSaldoEstoque (verificar saldo atual)
   → POST webServicePostEntrada (dar entrada de estoque inicial)

3. CRIAR PEDIDO/ORDEM
   → POST webServicePostOrdem
   → Salvar o "numeroOrigem" como chave de vínculo

4. ENVIAR XML DA NF-e
   → POST webServicePostArquivoOrdem
   → { "numeroOrigem": "PEDIDO-12345", "inserirFiscal": "1",
       "atualizarTransporte": "1", "arquivoBase": "<BASE64>",
       "extensao": "xml", "mimeType": "application/xml", "idTipoAnexo": 4 }

5. ENVIAR ETIQUETA DE ENTREGA
   → POST webServicePostArquivoOrdem
   → { "numeroOrigem": "PEDIDO-12345", "arquivoBase": "<BASE64>",
       "extensao": "pdf", "mimeType": "application/pdf", "idTipoAnexo": 7 }

6. MONITORAR STATUS DO PEDIDO
   → GET webServiceGetOrdem (polling por numeroOrigem)
   → GET webServiceGetFalhasOrdem (verificar erros)

7. CANCELAR (se necessário)
   → POST webServiceCancelarOrdem
```

---

## 10. Resumo Rápido — Envio de Arquivos

| Necessidade | Endpoint | `idTipoAnexo` | `extensao` | `mimeType` |
|---|---|---|---|---|
| Enviar XML NF-e | `webServicePostArquivoOrdem` | `4` | `xml` | `application/xml` |
| Enviar PDF DANFE | `webServicePostArquivoOrdem` | `4` | `pdf` | `application/pdf` |
| Enviar Etiqueta PDF | `webServicePostArquivoOrdem` | `7` | `pdf` | `application/pdf` |
| Enviar Etiqueta ZPL | `webServicePostArquivoOrdem` | `7` | `zpl` | `text/plain` |
| Enviar Etiqueta PNG | `webServicePostArquivoOrdem` | `7` | `png` | `image/png` |
| Criar ordem via XML | `webServicePostOrdemPorXml` | — | — | — |

---

## 11. Observações Importantes

- **`codigoProduto` na ordem deve coincidir com `codigoSKU` do cadastro.** O produto deve estar previamente cadastrado no eShip.
- **`codigoArmazemOrigem`** é obrigatório na ordem e deve corresponder ao depósito configurado no eShip.
- **`cnpjCadastro`** no produto deve ser o CNPJ da empresa proprietária do estoque.
- **`cadastroDestinatario`** na ordem é obrigatório — sem ele a ordem não é criada.
- Datas devem ser enviadas no formato `YYYY-MM-DD`.
- Valores monetários devem ser STRING com ponto decimal (ex: `"125.50"`).
- Use sempre `Content-Type: application/json` e `api: <apikey>` no header.
- O campo **`ORDFila`** controla a transportadora/canal: `61`=CORREIOS, `60`=MELI FULL, `58`=AMAZON FULL, `52`=SHOPEE PONTO DE COLETA, `54`=MELI FLEX.
- Ao enviar XML com `inserirFiscal: "1"` e `atualizarTransporte: "1"`, o eShip extrai dados fiscais e atualiza o transporte automaticamente.
- O vínculo entre arquivo e ordem é feito pelo `numeroOrigem` (ID do pedido no seu ERP).
