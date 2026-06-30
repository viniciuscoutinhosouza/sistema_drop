# Tabelas fiscais — CST, CSOSN, CFOP, NCM, CEST, origem, indicadores

Códigos que vão na NF-e e definem a tributação de cada item. Escolher o código errado é a causa
nº 1 de rejeição e de autuação. **Confirme sempre na tabela oficial vigente** (Portal NF-e / RICMS
da UF) — aqui está o essencial para acertar.

## Sumário

1. [Origem da mercadoria](#origem-da-mercadoria-tabela-a)
2. [CST de ICMS (Regime Normal)](#cst-de-icms-regime-normal-tabela-b)
3. [CSOSN (Simples Nacional)](#csosn-simples-nacional)
4. [CST de IPI](#cst-de-ipi)
5. [CST de PIS/COFINS](#cst-de-piscofins)
6. [CFOP](#cfop)
7. [NCM e CEST](#ncm-e-cest)
8. [Indicadores da NF-e](#indicadores-da-nf-e)

---

## Origem da mercadoria (Tabela A)

Primeiro dígito do código de situação tributária do ICMS. Define se o produto é nacional ou
importado (afeta a alíquota interestadual de **4%** para importados):

| Cód | Origem |
|---|---|
| 0 | Nacional (exceto 3,4,5,8) |
| 1 | Estrangeira — importação direta (exceto 6) |
| 2 | Estrangeira — adquirida no mercado interno (exceto 7) |
| 3 | Nacional, conteúdo de importação **> 40% e ≤ 70%** |
| 4 | Nacional, processos produtivos básicos (Dec-Lei 288/67 etc.) |
| 5 | Nacional, conteúdo de importação **≤ 40%** |
| 6 | Estrangeira — importação direta, **sem similar nacional**, lista CAMEX |
| 7 | Estrangeira — mercado interno, sem similar nacional, lista CAMEX |
| 8 | Nacional, conteúdo de importação **> 70%** |

> Origem 1, 2, 3, 8 → alíquota interestadual **4%** (Resolução SF 13/2012). Origem 0,4,5,6,7 → 7%
> ou 12% conforme UFs.

---

## CST de ICMS (Regime Normal) — Tabela B

Código de 3 dígitos = **origem (1) + tributação (2)**. Ex.: `000`, `060`, `041`.

| CST | Tributação do ICMS |
|---|---|
| **00** | Tributada integralmente |
| **10** | Tributada **e com cobrança de ICMS por ST** |
| **20** | Com **redução de base de cálculo** |
| **30** | Isenta/não tributada **e com ICMS por ST** |
| **40** | **Isenta** |
| **41** | **Não tributada** |
| **50** | Suspensão |
| **51** | Diferimento |
| **60** | **ICMS cobrado anteriormente por ST** (mercadoria já "fechada") |
| **70** | Com redução de BC **e** cobrança por ST |
| **90** | Outras |

Grupos XML correspondentes: `ICMS00`, `ICMS10`, `ICMS20`, …, `ICMS60`, `ICMS90`.

---

## CSOSN (Simples Nacional)

Usado **no lugar do CST** quando `CRT=1` (Simples). 3 dígitos:

| CSOSN | Significado | Transfere crédito? |
|---|---|---|
| **101** | Tributada **com permissão de crédito** | **Sim** (`pCredSN`/`vCredICMSSN`) |
| **102** | Tributada **sem permissão de crédito** | Não |
| **103** | Isenção do ICMS para faixa de receita | Não |
| **201** | Com permissão de crédito **e com ST** | Sim + ST |
| **202** | Sem permissão de crédito **e com ST** | Não + ST |
| **203** | Isenção de ICMS para faixa **e com ST** | Não + ST |
| **300** | Imune | Não |
| **400** | Não tributada pelo Simples | Não |
| **500** | **ICMS cobrado por ST/antecipação** (já recolhido) | Não |
| **900** | Outros | conforme caso |

> Grupos XML: `ICMSSN101`, `ICMSSN102` (cobre 102/103/300/400), `ICMSSN201`, `ICMSSN202` (cobre
> 202/203), `ICMSSN500`, `ICMSSN900`. **Crédito ao cliente só com 101/201** preenchendo
> `pCredSN` (alíquota de crédito do Simples) e `vCredICMSSN` (valor).

---

## CST de IPI

2 dígitos. Saídas mais comuns:

| CST | IPI na saída |
|---|---|
| 50 | Saída **tributada** |
| 51 | Saída **isenta** |
| 52 | Saída com **suspensão** |
| 53 | Saída com **alíquota zero** |
| 54 | Saída **imune** |
| 55 | Saída com suspensão (outras) |
| 99 | Outras saídas |
| 00–04 | Entradas (recuperação de crédito etc.) |

Só **indústria/equiparado** destaca IPI; comércio puro não é contribuinte.

---

## CST de PIS/COFINS

Mesma tabela para os dois. Mais usados na saída:

| CST | Situação |
|---|---|
| **01** | Tributável — **alíquota básica** (cumulativo 0,65/3% ou não-cum. 1,65/7,6%) |
| 02 | Tributável — alíquota diferenciada |
| 03 | Tributável — alíquota por unidade de medida |
| **04** | **Monofásico — revenda a alíquota zero** |
| 05 | ST |
| **06** | **Alíquota zero** |
| **07** | **Isenta** |
| 08 | Sem incidência |
| 09 | Suspensão |
| **49** | Outras operações de **saída** |
| 50–66 | Operações com direito a **crédito** (entradas, não-cumulativo) |
| 70–75 | Operações de crédito presumido |
| 98/99 | Outras |

> Erro comum: revenda de produto **monofásico** (autopeça, cosmético, bebida) lançada como `01`
> em vez de `04`/`06` → paga PIS/COFINS indevido sobre algo já tributado na origem.

---

## CFOP

**Código Fiscal de Operações e Prestações** — 4 dígitos. O **1º dígito** indica o destino/origem
geográfico da operação:

| 1º díg | Tipo | Sentido |
|---|---|---|
| 1 | Entrada | **dentro da UF** |
| 2 | Entrada | **outra UF** |
| 3 | Entrada | **exterior** (importação) |
| 5 | Saída | **dentro da UF** |
| 6 | Saída | **outra UF** |
| 7 | Saída | **exterior** (exportação) |

Exemplos frequentes (saída):

| CFOP | Operação |
|---|---|
| 5.102 / 6.102 | Venda de mercadoria adquirida de terceiros (intra / inter UF) |
| 5.405 / 6.404 | Venda de mercadoria **com ST** |
| 5.101 / 6.101 | Venda de produção do estabelecimento (indústria) |
| 5.202 / 6.202 | **Devolução** de compra para comercialização |
| 5.949 / 6.949 | Outra saída não especificada |
| 5.910 / 6.910 | Remessa em bonificação/brinde |

> **Coerência obrigatória:** `idDest` (1/2/3) tem que casar com o 1º dígito do CFOP. Vender para
> outra UF com CFOP 5.xxx (intra) → rejeição. E CFOP de **ST** (5.405/6.404) exige o grupo de ST
> (CST 10/60 ou CSOSN 201/202/500).

---

## NCM e CEST

- **NCM** (Nomenclatura Comum do Mercosul) — **8 dígitos**, classifica a mercadoria; define
  **IPI (TIPI)** e influencia ICMS/ST/PIS/COFINS. **Obrigatório** em todo item de NF-e (mercadoria
  genérica usa `00`, mas produto real exige o NCM correto). NCM inexistente → rejeição 778.
- **CEST** (Código Especificador da Substituição Tributária) — **7 dígitos**, identifica produto
  **sujeito a ST**. **Obrigatório quando o produto tem ST** (e mesmo em operação sem ST, se o
  produto está na lista do Convênio ICMS 142/2018). Faltou CEST em produto ST → rejeição 806.

> Mesmo NCM pode ou não ter ST dependendo da **UF de destino e do convênio/protocolo** — confirme.
> O CEST está atrelado ao **segmento** do produto, não só ao NCM.

---

## Indicadores da NF-e

| Campo | Valores |
|---|---|
| `indFinal` | 0 = não é consumidor final; 1 = **consumidor final** (dispara DIFAL B2C inter-UF) |
| `indPres` | 0 não se aplica; 1 presencial; 2 internet; 3 teleatendimento; 4 NFC-e domicílio; 5 presencial fora do estab.; 9 **operação não presencial, outros** (e-commerce comum) |
| `indIEDest` | 1 contribuinte ICMS; 2 contribuinte isento de IE; **9 não-contribuinte** |
| `tpNF` | 0 entrada; 1 saída |
| `idDest` | 1 interna; 2 interestadual; 3 exterior |
| `finNFe` | 1 normal; 2 complementar; 3 ajuste; 4 devolução (ver `eventos-fiscais.md`) |

> No e-commerce/dropshipping para pessoa física em outra UF: `indFinal=1`, `indPres=9`,
> `indIEDest=9`, `idDest=2` → **gera DIFAL** para a UF de destino (ver `credito-debito-impostos.md`).
