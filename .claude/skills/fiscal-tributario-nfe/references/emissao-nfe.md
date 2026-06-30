# Emissão e configuração de NF-e (55) e NFC-e (65)

Referência da **regra fiscal** de emissão. Para o **código** (DDL, SOAP, mTLS, assinatura A1,
fila), use [DOCs/guia-implementacao-nfe-oracle.md](../../../DOCs/guia-implementacao-nfe-oracle.md).

## Sumário

1. [Modelos e quando usar cada um](#modelos-e-quando-usar-cada-um)
2. [O que cadastrar para uma empresa emitir](#o-que-cadastrar-para-uma-empresa-emitir)
3. [Anatomia da NF-e 4.00](#anatomia-da-nf-e-400)
4. [Campos que mais geram rejeição](#campos-que-mais-geram-rejeição)
5. [Ambientes e ciclo de status](#ambientes-e-ciclo-de-status)
6. [Finalidades da NF-e](#finalidades-da-nf-e)
7. [Contingência](#contingência)
8. [DANFE](#danfe)
9. [Reforma Tributária — NT 2025.002](#reforma-tributária--nt-2025002)

---

## Modelos e quando usar cada um

| Modelo | Documento | Quando |
|---|---|---|
| **55** | **NF-e** | Operação entre empresas (B2B), venda a distância (e-commerce B2C), transporte, devolução, remessa. Destinatário identificado. |
| **65** | **NFC-e** | Venda **presencial ao consumidor final** (varejo de balcão). Substitui o cupom fiscal. Exige **CSC** + QR Code. |
| 57 | CT-e | Transporte (ver `documentos-transporte.md`) |
| 58 | MDF-e | Manifesto de carga (ver `documentos-transporte.md`) |

> No e-commerce/dropshipping do Sistema Drop, a venda a consumidor final em **outra UF** ou **a
> distância** é **NF-e 55** (não NFC-e), com `indPres` apropriado e DIFAL quando B2C inter-UF.

---

## O que cadastrar para uma empresa emitir

Pré-requisitos **legais** (sem eles a SEFAZ rejeita mesmo com XML perfeito):

1. **Certificado digital A1 e-CNPJ (ICP-Brasil)** — um `.pfx` **por CNPJ** (matriz e cada filial).
2. **Credenciamento como emissor de NF-e** na SEFAZ da UF (SP: Cadesp; RJ: portal SEFAZ-RJ).
3. **Inscrição Estadual ativa**.
4. **CSC (Código de Segurança do Contribuinte)** — **só NFC-e 65**, gera o QR Code.

Cadastro fiscal do emitente (mapeia para `NFE_EMPRESAS`): CNPJ, IE (e IE-ST se houver), razão
social, endereço com **código IBGE de 7 dígitos**, **CRT** (1/2/3/4 — regime), alíquota FECP,
caminho do certificado + env var da senha, séries fiscais por (modelo, série, ambiente).

> **🔴 Um CNPJ = um certificado.** O cert da matriz **não** emite NF-e da filial (`cStat=290`).
> **🔴 Senha do cert / token CSC nunca no banco** — só o **nome da env var**.

---

## Anatomia da NF-e 4.00

O XML `infNFe` tem grupos principais:

| Grupo | Tag | Conteúdo |
|---|---|---|
| Identificação | `ide` | `cUF`, `natOp`, `mod`, `serie`, `nNF`, `dhEmi`, `tpNF` (0 entrada/1 saída), `idDest` (1 interna/2 interestadual/3 exterior), `cMunFG`, `tpImp`, `tpEmis`, `finNFe`, `indFinal`, `indPres`, `cDV`, `tpAmb` |
| Emitente | `emit` | CNPJ, IE, `CRT`, endereço |
| Destinatário | `dest` | CNPJ/CPF, `indIEDest` (1 contrib/2 isento/9 não-contrib), endereço, email |
| Itens | `det` (1..N) | `prod` (cProd, cEAN, NCM, CEST, CFOP, uCom, qCom, vUnCom, vProd) + `imposto` |
| Impostos do item | `imposto` | `ICMS` (CST ou CSOSN), `IPI`, `PIS`, `COFINS`, e `ICMSUFDest` (DIFAL) |
| Totais | `total` | `ICMSTot` (vBC, vICMS, vICMSST, vFCP, vProd, vIPI, vPIS, vCOFINS, vNF…) |
| Transporte | `transp` | `modFrete`, transportadora, volumes (ver `documentos-transporte.md`) |
| Pagamento | `pag` | `detPag` (`tPag`, `vPag`), `vTroco` |
| Info adicionais | `infAdic` | `infCpl` (complementar ao contribuinte), `infAdFisco` |

### Chave de acesso (44 dígitos)

```
cUF(2) + AAMM(4) + CNPJ_emit(14) + mod(2) + serie(3) + nNF(9) + tpEmis(1) + cNF(8) + cDV(1)
```
`cNF` = código numérico aleatório (não pode ser igual ao `nNF`); `cDV` = dígito verificador
módulo 11.

### Grupo de ICMS — depende do CRT

- **CRT=3 (Regime Normal)** → grupo **`ICMS00/10/20/.../60/70/90`** com **CST** (ex.: `ICMS00`
  tributação integral; `ICMS60` ST já recolhida; `ICMS40` isenta).
- **CRT=1 (Simples)** → grupo **`ICMSSN101/102/201/202/500/900`** com **CSOSN**. Para transferir
  crédito (CSOSN 101/201): preencher `pCredSN` e `vCredICMSSN`.

---

## Campos que mais geram rejeição

| Campo | Armadilha | cStat típico |
|---|---|---|
| `cMunFG` / IBGE | Código IBGE inválido ou de 6 dígitos | 264, rejeição de município |
| `NCM` | NCM inexistente na tabela TIPI vigente | 778 "NCM não existe" |
| `CEST` | Obrigatório se produto está em regime de ST e faltou | 806 |
| `CFOP` | CFOP incompatível com `idDest`/operação (intra com 6xxx) | 522/527 |
| CST/CSOSN vs CRT | CST em empresa do Simples ou CSOSN no Regime Normal | rejeição grupo ICMS |
| `vNF` / totais | Soma dos itens ≠ total (arredondamento) | 533/534 "valor total difere" |
| `dhEmi` | Data fora da janela aceita (futuro / muito no passado) | 228/703 |
| Destinatário em HOMOLOGAÇÃO | `xNome` do dest **deve** ser "NF-E EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL" | 999/rejeição |
| `indIEDest` | Não-contribuinte com IE preenchida, ou contribuinte sem IE | 791/792 |

> **HTTP 200 não garante autorização.** Sempre leia o `cStat` interno do `protNFe`
> (`100` = autorizada). Ver tabela de cStat no guia de implementação (§7.8).

---

## Ambientes e ciclo de status

- **`tpAmb=2` HOMOLOGAÇÃO**: testes, sem valor fiscal. Toda empresa nova começa aqui (smoke:
  emitir 1 NF-e 55 e 1 NFC-e 65 e conferir `cStat=100`).
- **`tpAmb=1` PRODUÇÃO**: valor fiscal real. Só liberar após smoke OK + credenciamento confirmado
  (`PRODUCAO_LIBERADA=1` no Drop).

Estados internos (mapa do `NFE_NOTAS.STATUS`):

```
rascunho → assinada → transmitida → autorizada
                                  ↘ rejeitada (corrige e reenvia, mesmo número)
                                  ↘ denegada  (terminal — problema cadastral do dest.)
autorizada → cancelada (evento, prazo legal)
(faixa de número não usada) → inutilizada
```

---

## Finalidades da NF-e (`finNFe`)

| Cód | Finalidade | Uso |
|---|---|---|
| **1** | **Normal** | venda/remessa comum |
| **2** | **Complementar** | complementa valor/imposto **a maior** de uma nota já emitida (ex.: ICMS destacado a menos, complemento de frete). Referencia a chave original. |
| **3** | **Ajuste** | ajuste fiscal sem circulação de mercadoria (regularização de ST, estorno). |
| **4** | **Devolução** | devolução de mercadoria (total/parcial). CFOP de devolução (1.2xx/2.2xx ou 5.2xx/6.2xx), referencia a NF-e de origem, **espelha** os impostos da entrada. |

> No Drop, devolução segue **ADR-0009** (NF-e fiscal-only com `stock_updated=False` + contadores de
> inspeção como fonte canônica de estoque). A nota de devolução é fiscal; o estoque é tratado à
> parte. Respeite a ADR antes de mexer.

---

## Contingência

Quando a SEFAZ está fora do ar (`tpEmis`):

| Cód | Modo | Como |
|---|---|---|
| 1 | Normal | autorização online padrão |
| 4 | **EPEC** | Evento Prévio de Emissão em Contingência (autoriza prévia, transmite depois) |
| 9 | **SVC-AN/SVC-RS** | Sefaz Virtual de Contingência (autorizador alternativo) |

Em contingência, transmitir as notas pendentes assim que a SEFAZ normalizar. **NFC-e** tem
contingência **offline** própria (gera, entrega ao cliente, transmite em até 24h).

---

## DANFE

Representação gráfica (PDF) da NF-e — **não é a nota** (a nota é o XML autorizado). Só vale com
chave + protocolo. NFC-e tem **DANFE-NFC-e** (cupom estreito com QR Code do CSC). No Drop, gerado
via `BrazilFiscalReport` (ver guia §6).

---

## Reforma Tributária — NT 2025.002

A NF-e 4.00 já recebeu grupos para **IBS, CBS e IS** (NT 2025.002). Em 2026 (fase-teste) os campos
são preenchidos com alíquotas calibradoras (CBS 0,9% / IBS 0,1%) em paralelo aos tributos atuais.
Ao implementar emissão para 2026+, **incluir os novos grupos** e **confirmar a versão da NT
vigente** no Portal Nacional — o leiaute evolui a cada fase da transição (2026→2033).
