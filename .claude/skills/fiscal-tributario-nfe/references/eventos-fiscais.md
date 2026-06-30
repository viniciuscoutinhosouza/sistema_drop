# Eventos fiscais — correção, cancelamento, inutilização, manifestação, devolução

Depois que a NF-e é **autorizada** (`cStat=100`) o XML é **imutável**: você só pode anexar
**eventos**. Este arquivo diz **qual evento resolve qual problema** — usar o errado gera passivo.

## Sumário

1. [Árvore de decisão: "errei a nota, e agora?"](#árvore-de-decisão-errei-a-nota-e-agora)
2. [Carta de Correção Eletrônica (CC-e)](#carta-de-correção-eletrônica-cc-e--110110)
3. [Cancelamento](#cancelamento--110111)
4. [Inutilização de numeração](#inutilização-de-numeração)
5. [NF-e complementar / ajuste / devolução](#nf-e-complementar--ajuste--devolução)
6. [Manifestação do destinatário](#manifestação-do-destinatário)
7. [Denegação](#denegação)
8. [Códigos de evento (resumo)](#códigos-de-evento-resumo)

---

## Árvore de decisão: "errei a nota, e agora?"

```
A mercadoria já circulou (saiu / foi entregue)?
│
├─ NÃO, e ainda dentro do prazo de cancelamento
│   ├─ erro em VALOR / IMPOSTO / DESTINATÁRIO / produto  → CANCELAR e reemitir corrigida
│   └─ erro pequeno que NÃO muda valor/imposto/dest.       → CARTA DE CORREÇÃO (CC-e)
│
├─ SIM (já circulou / fora do prazo de cancelamento)
│   ├─ erro que NÃO muda valor/imposto/dest./operação      → CARTA DE CORREÇÃO (CC-e)
│   ├─ destacou imposto/valor A MENOS                       → NF-e COMPLEMENTAR (finNFe=2)
│   ├─ destacou A MAIS / mercadoria volta                   → NF-e DEVOLUÇÃO (finNFe=4) pelo destinatário
│   │                                                          ou devolução/recusa
│   └─ ajuste fiscal sem mercadoria (ST, estorno)           → NF-e AJUSTE (finNFe=3)
│
└─ Número da nota NUNCA foi usado (pulou na sequência)      → INUTILIZAÇÃO
```

> Regra mestra: **CC-e nunca corrige valor, base/alíquota de imposto, dados do destinatário
> (CNPJ/CPF/IE), data de emissão, ou nada que altere a operação.** Se o erro é desses, é
> cancelamento (se der) ou nota nova (complementar/devolução/ajuste).

---

## Carta de Correção Eletrônica (CC-e) — 110110

Corrige **erros que NÃO alteram a operação**. Base: **Ajuste SINIEF 07/2005, cláusula 14-A**.

**PODE corrigir** (exemplos): erro de digitação em razão social que não muda o CNPJ, endereço de
entrega, dados do transportador, descrição complementar do produto que não mude a natureza, peso,
informações adicionais, natureza da operação **desde que não mude tributação**.

**NÃO pode corrigir** (vedação expressa):
- valores (preço, base de cálculo, alíquota, imposto, quantidade);
- dados cadastrais que alterem **remetente ou destinatário** (CNPJ/CPF, IE);
- **data de emissão** ou de saída;
- qualquer coisa que mude a **operação/tributação**.

**Mecânica:**
- Evento `110110`, enviado por `RecepcaoEvento4`.
- Texto da correção (`xCorrecao`, mín. 15 caracteres).
- Cada CC-e tem um **número sequencial** (`nSeqEvento`); **vale sempre a última** — a CC-e
  **substitui** a anterior, não soma. Use no máximo o que precisar.
- Só após a nota estar **autorizada**.

---

## Cancelamento — 110111

Torna a NF-e **sem efeito**. Base: cláusula 13 do Ajuste SINIEF 07/2005.

**Condições:**
- A **mercadoria NÃO pode ter circulado** (não houve saída/entrega).
- **Prazo:** **24 horas** após a autorização (prazo "ideal" da legislação nacional). Muitas UFs
  aceitam **cancelamento extemporâneo** até ~480h (20 dias) **com multa/penalidade**. **O prazo e
  a multa variam por UF — confirme no RICMS de {UF}.**
- Precisa do **protocolo de autorização** original (`nProt`).

**Mecânica:** evento `110111` com `xJust` (justificativa, mín. 15 caracteres). Retorno `cStat=135`
(evento registrado) ou `155` (registrado fora do prazo). No Drop: gera job `cancelar`,
`STATUS='cancelada'`, grava `PROTOCOLO_CANCELAMENTO` e `CANCELADA_EM`.

> Passou o prazo e a mercadoria circulou? **Não dá para cancelar** — usa-se **devolução**
> (destinatário emite NF-e de devolução) ou **ajuste**. Esse é o caso clássico de "não cancela,
> mas tem outro caminho".

---

## Inutilização de numeração

Para **"queimar" oficialmente um número de NF-e que nunca foi usado** — quebra de sequência por
falha de sistema (ex.: pulou do nNF 100 para o 102, o 101 nunca existiu).

- **Não** é cancelamento (não há nota): é declarar à SEFAZ que aquela faixa **não será usada**.
- Pedido `inutNFe` informando série + faixa `nNFIni`–`nNFFin` + justificativa.
- Prazo: até o **10º dia do mês seguinte** ao da quebra (regra geral; confirme na UF).
- Retorno `cStat=102` (inutilização homologada). No Drop: `STATUS='inutilizada'`.

> Use inutilização **só** quando o número realmente não gerou nota autorizada nem rejeitada
> pendente. Número de nota **rejeitada** pode ser reaproveitado (corrige e reenvia com o mesmo
> número) — aí **não** inutiliza.

---

## NF-e complementar / ajuste / devolução

Quando o erro **muda valor/imposto** e a nota já não pode ser cancelada, a correção é **uma nova
NF-e** que referencia a original (`refNFe` com a chave de 44 dígitos):

| Situação | Finalidade | CFOP típico | Observação |
|---|---|---|---|
| Destacou imposto/valor **a menos** | **Complementar (2)** | mesmo da original | só a diferença (vProd/imposto faltante) |
| Mercadoria **retorna** ou recusa | **Devolução (4)** | 1.2xx/2.2xx (entrada) ou 5.2xx/6.2xx (saída) | espelha os impostos da nota de origem |
| Regularização fiscal **sem mercadoria** (ST, estorno de crédito) | **Ajuste (3)** | conforme orientação da UF | não há circulação física |

**Devolução — pontos críticos:**
- Quem devolve **espelha exatamente** base, alíquota e valor de ICMS/IPI/PIS/COFINS da nota
  original (para o imposto "voltar" simetricamente).
- Se o **destinatário é Simples** (não destaca ICMS), a devolução sai sem destaque, mas o
  remitente original recupera o crédito via a nota de devolução conforme regra da UF.
- No Drop: **ADR-0009** — NF-e de devolução é **fiscal-only** (`stock_updated=False`); o estoque é
  governado por contadores de inspeção. Não acoplar baixa de estoque à emissão.

---

## Manifestação do destinatário

Eventos que o **destinatário** registra sobre uma NF-e emitida **contra ele** (útil para detectar
nota fria emitida em seu CNPJ e para tomar crédito com segurança):

| Evento | Nome | Significado |
|---|---|---|
| `210200` | **Confirmação da Operação** | recebeu a mercadoria e confirma — habilita crédito pleno |
| `210210` | **Ciência da Operação** | sabe que existe a NF-e, ainda sem confirmar |
| `210220` | **Desconhecimento da Operação** | não reconhece — defesa contra nota emitida indevidamente |
| `210240` | **Operação não Realizada** | reconhece a NF-e mas a operação não se concretizou (recusa) |

Importante para grandes compradores e para o **manifesto** que precede o download do XML completo
(quem só tem o resumo via DF-e precisa manifestar ciência para baixar o XML inteiro).

---

## Denegação

Não é evento do emitente: é a SEFAZ **recusando autorizar** por **irregularidade cadastral** do
emitente ou destinatário (ex.: IE inapta, CNPJ baixado). `cStat` 110/301/302. A NF-e fica
**denegada** — **não pode ser usada nem cancelada**, e o **número é consumido** (não reaproveita).
Resolve-se regularizando o cadastro e emitindo **nota nova com novo número**.

---

## Códigos de evento (resumo)

| Código | Evento | Quem |
|---|---|---|
| 110110 | Carta de Correção (CC-e) | emitente |
| 110111 | Cancelamento | emitente |
| 110112 | Cancelamento por substituição (NFC-e, algumas UFs) | emitente |
| (inutNFe) | Inutilização de numeração | emitente |
| 110140 | EPEC (contingência) | emitente |
| 210200 | Confirmação da Operação | destinatário |
| 210210 | Ciência da Operação | destinatário |
| 210220 | Desconhecimento da Operação | destinatário |
| 210240 | Operação não Realizada | destinatário |

Todos transmitidos por **`RecepcaoEvento4`** (mesmo webservice). No Drop, cada evento vira linha
**append-only** em `NFE_NOTAS_EVENTOS` (tabela imutável — trigger barra UPDATE/DELETE) e o request/
response SOAP fica em `NFE_LOGS_SEFAZ` (retenção 5 anos).
