# Crédito e débito — não-cumulatividade, ICMS-ST, DIFAL, FECP, IPI, PIS/COFINS

Referência para **calcular o imposto da operação** e entender o que gera **crédito** (entrada) e
**débito** (saída). Leia antes de calcular ICMS próprio, ST, DIFAL, IPI ou PIS/COFINS.

## Sumário

1. [O princípio da não-cumulatividade](#o-princípio-da-não-cumulatividade)
2. [ICMS próprio](#icms-próprio)
3. [ICMS-ST (substituição tributária)](#icms-st-substituição-tributária)
4. [DIFAL inter-UF (EC 87/2015)](#difal-inter-uf-ec-872015)
5. [FECP / FCP](#fecp--fcp)
6. [IPI](#ipi)
7. [PIS e COFINS](#pis-e-cofins)
8. [ISS](#iss)
9. [Apuração: juntando débito − crédito](#apuração-juntando-débito--crédito)

---

## O princípio da não-cumulatividade

Imposto **não-cumulativo** incide só sobre o **valor agregado** em cada etapa: a empresa **debita**
o imposto na saída (venda) e **credita** o que pagou na entrada (compra). Recolhe a diferença.

```
Imposto a recolher = Σ Débitos (saídas) − Σ Créditos (entradas)
```

Se os créditos superam os débitos no período, gera **saldo credor** que transporta para o mês
seguinte (não vira dinheiro de volta, salvo exceções como exportação).

| Imposto | Não-cumulativo? | Quem credita |
|---|---|---|
| ICMS | Sim | contribuinte do ICMS (comércio/indústria) |
| IPI | Sim | indústria e equiparados |
| PIS/COFINS | Só no Lucro Real | empresa no não-cumulativo |
| ICMS-ST | Não (encerra a cadeia) | — |

> **Simples Nacional não credita** (recolhe tudo no DAS). Ele pode *transferir* um crédito de
> ICMS limitado ao destinatário via CSOSN 101/201 (`pCredSN`), mas **não toma** crédito de entrada.

---

## ICMS próprio

Imposto estadual sobre circulação de mercadoria. Alíquota **depende da UF e da operação**:

- **Interna** (dentro da mesma UF): varia por UF e por produto (ex.: 17%, 18%, 19%, 20%, 22%…).
  **Confirme no RICMS da UF.**
- **Interestadual** (entre UFs): **7%** ou **12%**, conforme origem/destino, e **4%** para
  **produto importado** (Resolução SF 13/2012):

```
Origem S/SE (exceto ES) → N/NE/CO/ES : 7%
Demais combinações entre contribuintes : 12%
Mercadoria importada (origem 1,2,3,8) : 4%
```

### Cálculo do ICMS "por dentro"

O ICMS integra a própria base (é "por dentro"):

```
Base ICMS = Valor_produto + Frete + Seguro + Outras_despesas − Desconto (+ IPI, se NÃO for p/ revenda)
ICMS = Base × Alíquota
```

> O IPI **entra** na base do ICMS quando a venda é para **consumidor final / uso e consumo**.
> Quando é para **revenda/industrialização** (entre contribuintes), o IPI **fica fora** da base do
> ICMS. (Art. 13 da LC 87/96.)

**Exemplo (venda interna SP 18%, produto R$ 1.000, frete R$ 100, sem IPI):**
```
Base = 1.000 + 100 = 1.100
ICMS = 1.100 × 18% = R$ 198,00   (débito do vendedor / crédito do comprador contribuinte)
```

### CST x CSOSN

- Regime Normal → **CST de ICMS** (Tabela B, 2 dígitos) com origem (Tabela A, 1 dígito): ex. `000`
  tributado integralmente, `060` ICMS já cobrado por ST, `040` isenta.
- Simples → **CSOSN** (3 dígitos): `101`/`201` (com crédito), `102`/`103`/`300`/`400` (sem
  crédito), `500` (ST/antecipação), `900` (outros). Ver `tabelas-fiscais.md`.

---

## ICMS-ST (substituição tributária)

Mecanismo em que **um contribuinte (o substituto, geralmente a indústria/importador) recolhe
antecipadamente** o ICMS de **toda a cadeia** até o consumidor final. Os elos seguintes
(distribuidor, varejo) **não destacam mais ICMS** naquela mercadoria (CST `060` / CSOSN `500`).

Aplica-se a produtos com **CEST** definido em **Convênio/Protocolo ICMS** entre as UFs (bebidas,
autopeças, cosméticos, eletrônicos, pneus…). **Depende do par origem/destino — confirme o
protocolo vigente.**

### Cálculo da ST

```
1. ICMS próprio (do substituto)   = Base_própria × Alíq_interestadual
2. Base ST = (Valor_produto + IPI + Frete + Seguro + Outras − Desconto) × (1 + MVA)
3. ICMS-ST = (Base_ST × Alíq_interna_destino) − ICMS_próprio
```

- **MVA / IVA-ST** = Margem de Valor Agregado (% definido por produto/UF). Há **MVA Ajustada**
  para operação interestadual:
```
MVA_ajustada = [(1 + MVA_original) × (1 − Alíq_inter) / (1 − Alíq_interna_destino)] − 1
```
- A **Alíquota interna é a da UF de DESTINO** (onde a mercadoria será vendida ao consumidor).

**Exemplo (produto R$ 1.000, MVA 40%, inter 12%, interna destino 18%):**
```
ICMS próprio = 1.000 × 12% = 120
Base ST = 1.000 × 1,40 = 1.400
ICMS-ST = (1.400 × 18%) − 120 = 252 − 120 = R$ 132,00  (recolhido por GNRE/antecipação)
```

> No XML, ST usa os campos `vBCST`, `pMVAST`, `vICMSST`. O destinatário que **revende** não
> credita nem debita ICMS dessa mercadoria — ela já está "fechada".

---

## DIFAL inter-UF (EC 87/2015)

Diferencial de alíquota na venda **interestadual para consumidor final**. Regras dependem de o
destinatário ser ou não contribuinte:

- **Destinatário NÃO contribuinte** (B2C, ex.: e-commerce p/ pessoa física em outra UF): o
  **remetente** recolhe o DIFAL para a **UF de destino** (LC 190/2022 — exigível desde 2022).
- **Destinatário contribuinte** que usa para **uso/consumo ou ativo**: o **próprio destinatário**
  recolhe o DIFAL na entrada.

```
DIFAL = Base × (Alíq_interna_destino − Alíq_interestadual)
```

Com **base dupla** em algumas UFs (a base inclui o próprio DIFAL — "por dentro"). No XML B2C vão
os campos `vBCUFDest`, `pICMSUFDest`, `vICMSUFDest`, `vICMSUFRemet`, e `vFCPUFDest` (FECP do
destino). **A partilha hoje é 100% para o destino** (a transição 2016–2019 já terminou).

**Exemplo (venda SP→MG, R$ 1.000, inter 12%, interna MG 18%):**
```
DIFAL = 1.000 × (18% − 12%) = R$ 60,00  (recolhido para MG)
```

---

## FECP / FCP

**Fundo de Combate à Pobreza**: adicional de ICMS (geralmente **1% a 2%**) sobre **produtos
específicos** em **algumas UFs** (ex.: RJ 2%, bebidas/supérfluos). Soma-se ao ICMS/ST/DIFAL
conforme o caso. Campos no XML: `vFCP`, `vFCPST`, `vFCPUFDest`. **Confirme se o NCM/UF tem FECP —
nem todo produto/UF tem.**

---

## IPI

Imposto federal sobre **produto industrializado**, devido na **saída do estabelecimento
industrial ou equiparado** (e na importação). Comércio puro **não** é contribuinte de IPI (revende
sem destacar).

- Alíquota pela **TIPI** (tabela por NCM) — varia de 0% a alíquotas altas (cigarro, bebida).
- Não-cumulativo: credita o IPI das entradas de insumos, debita na saída.
- **Fora da base do ICMS** quando a operação é entre contribuintes para revenda; **dentro** quando
  para consumidor final.

```
IPI = Valor_produto × Alíquota_TIPI
```

CST de IPI próprio (2 dígitos): `50` saída tributada, `51` isenta, `99` outras (ver
`tabelas-fiscais.md`). Campos: `vIPI`, `pIPI`, `vBC`.

> Na Reforma, o IPI tende a ser **zerado** (mantido só para preservar a competitividade da Zona
> Franca de Manaus). Sinalize isso em planejamento de médio prazo.

---

## PIS e COFINS

Contribuições federais sobre a **receita**. O regime depende do **regime de IRPJ**:

| Regime IRPJ | PIS/COFINS | Alíquota | Crédito? |
|---|---|---|---|
| Simples | dentro do DAS | — | não |
| Lucro Presumido | **cumulativo** | PIS 0,65% + COFINS 3,00% = **3,65%** | **não** |
| Lucro Real | **não-cumulativo** | PIS 1,65% + COFINS 7,60% = **9,25%** | **sim** |

### Não-cumulativo (Lucro Real) — créditos

Crédito de **1,65% (PIS) / 7,6% (COFINS)** sobre, entre outros (Leis 10.637/02 e 10.833/03):
- bens para revenda;
- **insumos** aplicados na produção/prestação de serviço (conceito de insumo = essencialidade e
  relevância, definido pelo STJ no REsp 1.221.170);
- energia elétrica e térmica;
- aluguéis de prédios/máquinas/equipamentos pagos a PJ;
- fretes na operação de venda;
- depreciação de máquinas/equipamentos do ativo imobilizado.

```
PIS a recolher    = Receita × 1,65% − Créditos × 1,65%
COFINS a recolher = Receita × 7,60% − Créditos × 7,60%
```

### Regimes especiais

- **Monofásico** (combustíveis, medicamentos, cosméticos, bebidas, autopeças…): o fabricante/
  importador recolhe com alíquota concentrada e os demais revendem com **alíquota zero**. Não
  confundir alíquota zero monofásica com isenção — o CST de PIS/COFINS muda (ver tabela).
- **Substituição** e **alíquota zero / suspensão / exportação** têm CSTs próprios (04, 06, 07,
  08, 09…).

### CST de PIS/COFINS

Sempre obrigatório no XML (grupo `PIS`/`COFINS`). Ex.: `01` tributável alíquota básica, `04`
monofásico (revenda alíq. zero), `06` alíquota zero, `07` isenta, `49` outras saídas. Ver
`tabelas-fiscais.md`.

> Na Reforma, PIS+COFINS viram **CBS** (não-cumulativa plena para todos). O cumulativo do
> Presumido deixa de existir nesse tributo.

---

## ISS

Imposto **municipal** sobre serviços da **Lista Anexa à LC 116/2003**. Alíquota **2% a 5%** (piso
e teto da LC). Recolhido ao município do **prestador** (regra) ou do **tomador** (exceções da LC,
ex.: construção civil, limpeza). Pode haver **ISS retido na fonte** pelo tomador. **Cumulativo**
(sem crédito). Não vai na NF-e modelo 55 — vai na **NFS-e** municipal (cada município com seu
padrão; há o padrão nacional NFS-e em adoção). Na Reforma, ISS → **IBS**.

---

## Apuração: juntando débito − crédito

No fim do período, por imposto não-cumulativo:

```
ICMS a recolher = Σ ICMS_débito(saídas) − Σ ICMS_crédito(entradas) − saldo_credor_anterior
```

- **ICMS/IPI**: apuração mensal no **SPED Fiscal (EFD ICMS/IPI)**; recolhe via guia estadual
  (ICMS) e DARF (IPI). Saldo credor transporta.
- **PIS/COFINS** (Real): **EFD-Contribuições**; DARF mensal.
- **IRPJ/CSLL**: ver `regimes-tributarios.md` (trimestral/anual).
- **Simples**: nada disso separado — tudo no **DAS** via PGDAS-D (mas a **segregação de receita**
  por ST/exportação/retenção reduz o DAS; ver `regimes-tributarios.md`).

> No Sistema Drop, os valores calculados por item ficam congelados em `NFE_NOTAS_ITENS`
> (`V_BC`, `V_ICMS`, `V_BC_ST`, `V_ICMS_ST`, `V_FECP`, `V_IPI`) e somados no cabeçalho
> `NFE_NOTAS`. A **apuração** (somatório do período) é leitura desses snapshots — nunca recalcular
> a nota já autorizada.
