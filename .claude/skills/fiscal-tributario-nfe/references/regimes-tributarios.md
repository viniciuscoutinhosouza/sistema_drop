# Regimes tributários — Simples, Presumido, Real (cálculo e apuração)

Referência para **enquadrar** a empresa e **apurar** os tributos em cada regime. Leia por inteiro
antes de calcular DAS, IRPJ/CSLL/PIS/COFINS ou orientar enquadramento.

## Sumário

1. [Como o regime decide tudo](#como-o-regime-decide-tudo)
2. [Simples Nacional](#simples-nacional)
3. [Lucro Presumido](#lucro-presumido)
4. [Lucro Real](#lucro-real)
5. [Comparativo e escolha](#comparativo-e-escolha)
6. [Reforma Tributária e os regimes](#reforma-tributária-e-os-regimes)

---

## Como o regime decide tudo

O regime define **três coisas** que cascateiam para a NF-e e a apuração:

1. **Como o lucro/receita é tributado** (DAS unificado vs. tributos separados).
2. **Qual grupo de imposto vai no XML** — Simples → **CSOSN** + `CRT=1`; Regime Normal
   (Presumido/Real) → **CST** + `CRT=3`.
3. **Se há direito a crédito** de ICMS/IPI/PIS/COFINS na entrada.

No Sistema Drop, o regime mora em `NFE_EMPRESAS.CRT`:

| CRT | Regime |
|---|---|
| 1 | Simples Nacional |
| 2 | Simples Nacional — MEI / excesso de sublimite (microempreendedor) |
| 3 | Regime Normal (Lucro Presumido **ou** Lucro Real) |
| 4 | Simples Nacional — com excesso de sublimite de ICMS/ISS |

> O CRT **não** distingue Presumido de Real (ambos são `3` na NF-e) — essa distinção é só na
> apuração dos tributos federais, não no XML.

---

## Simples Nacional

Base legal: **LC 123/2006** + Resoluções **CGSN** (a vigente é a **Res. CGSN 140/2018**).

### Quem pode

- Receita Bruta nos últimos 12 meses (**RBT12**) **≤ R$ 4.800.000,00/ano**.
- Não exercer atividade vedada (art. 17 da LC 123), não ter sócio PJ, não ser filial de empresa
  estrangeira etc.
- **Sublimite estadual de R$ 3.600.000,00**: acima dele, ICMS e ISS saem do DAS e passam a ser
  recolhidos **fora** do Simples (regime normal estadual/municipal) — é o caso do `CRT=4`.

### O DAS unifica 8 tributos

IRPJ, CSLL, PIS, COFINS, IPI, ICMS, ISS e **CPP** (contribuição patronal previdenciária — exceto
Anexo IV, onde a CPP é recolhida à parte em GPS).

### Os 5 anexos

| Anexo | Atividade | Alíquota nominal inicial |
|---|---|---|
| **I** | Comércio (revenda) | 4,00% |
| **II** | Indústria | 4,50% |
| **III** | Serviços (instalação, reparo, agências, e serviços do art. 18-§5º-B/C) | 6,00% |
| **IV** | Serviços (construção, limpeza, vigilância, advocacia) — **CPP fora do DAS** | 4,50% |
| **V** | Serviços intelectuais/técnicos (TI, engenharia, publicidade…) | 15,50% |

### Fator R — decide entre Anexo III e V

Para algumas atividades de serviço, o anexo depende da **folha de salários**:

```
Fator R = Folha de salários (12 meses, inclui pró-labore e encargos) / RBT12

Fator R ≥ 28%  → Anexo III  (mais barato)
Fator R < 28%  → Anexo V    (mais caro)
```

### Cálculo da alíquota EFETIVA (o ponto que mais erra)

A alíquota do anexo é **nominal**. O DAS usa a **efetiva**:

```
Alíquota efetiva = (RBT12 × Alíquota_nominal − Parcela_a_Deduzir) / RBT12

DAS do mês = Receita_bruta_do_mês × Alíquota_efetiva
```

`RBT12`, `Alíquota_nominal` e `Parcela_a_Deduzir` saem da **tabela do anexo por faixa de receita**
(6 faixas). **Sempre consulte a tabela vigente do anexo** — os valores das faixas mudam por norma.

**Exemplo (Anexo I, comércio):** empresa com RBT12 = R$ 720.000 cai na 2ª faixa (R$ 180.000,01 a
R$ 360.000... — *confirme a faixa na tabela vigente*). Suponha nominal 7,30% e PD = R$ 5.940:

```
Efetiva = (720.000 × 0,073 − 5.940) / 720.000 = (52.560 − 5.940) / 720.000 = 6,475%
Faturou R$ 60.000 no mês → DAS = 60.000 × 0,06475 = R$ 3.885,00
```

> Cada tributo dentro do DAS tem um **percentual de repartição** próprio por faixa (a parcela de
> ICMS, de PIS etc.). Isso importa quando há **segregação de receita** (ex.: parte com ST, parte
> com retenção, exportação) — nessas a alíquota daquele tributo é zerada/reduzida proporcionalmente.

### Segregação de receita (reduz o DAS)

- **Mercadoria com ICMS-ST já recolhido** → o percentual de ICMS daquela receita **não** entra no
  DAS de novo (senão paga ICMS duas vezes). Marca-se a receita como "com substituição/antecipação".
- **Exportação** → PIS/COFINS/ICMS/ISS daquela receita são desonerados.
- **Receita com retenção na fonte (ISS retido)** → não recolhe o ISS de novo no DAS.

### Obrigações

- **PGDAS-D** mensal (cálculo + declaração), vencimento dia **20** do mês seguinte.
- **DEFIS** anual (declaração de informações socioeconômicas).
- MEI: **DAS-MEI** valor fixo + **DASN-SIMEI** anual.

---

## Lucro Presumido

Base legal: **RIR/2018** + Lei 9.249/95 + Lei 9.430/96. PIS/COFINS no **regime cumulativo**.

### Quem pode

- Receita Bruta **≤ R$ 78.000.000,00/ano** (R$ 6,5 mi × meses, se < 12 meses).
- Não ser obrigado ao Lucro Real (bancos, factoring, certas atividades).

### IRPJ e CSLL — sobre lucro PRESUMIDO

O lucro é **presumido** por um percentual da receita bruta (não pela contabilidade real):

| Atividade | Presunção IRPJ | Presunção CSLL |
|---|---|---|
| Revenda de combustível | 1,6% | 12% |
| **Comércio, indústria, transporte de cargas** | **8%** | **12%** |
| Transporte de passageiros | 16% | 12% |
| **Serviços em geral** | **32%** | **32%** |
| Serviços hospitalares/equiparados | 8% | 12% |

```
Base IRPJ  = Receita_trimestral × presunção_IRPJ  (+ ganhos de capital, financeiras)
IRPJ       = Base_IRPJ × 15%  + adicional 10% sobre o que exceder R$ 20.000 × nº de meses do período
Base CSLL  = Receita_trimestral × presunção_CSLL
CSLL       = Base_CSLL × 9%
```

Apuração **trimestral** (31/mar, 30/jun, 30/set, 31/dez). O adicional de IRPJ é 10% sobre a base
que exceder **R$ 60.000 no trimestre** (= R$ 20.000/mês).

**Exemplo (comércio, trimestre com receita R$ 600.000):**
```
Base IRPJ = 600.000 × 8% = 48.000
IRPJ      = 48.000 × 15% = 7.200  (não passa de 60.000 → sem adicional)
Base CSLL = 600.000 × 12% = 72.000
CSLL      = 72.000 × 9% = 6.480
```

### PIS e COFINS — CUMULATIVO (sem crédito)

```
PIS    = Receita × 0,65%
COFINS = Receita × 3,00%
```

Apuração **mensal**, **sem direito a crédito** de entradas. Recolhidos em DARF separados.

### ICMS/IPI/ISS

Apurados normalmente (não-cumulativos, com crédito) — ver `credito-debito-impostos.md`. Presumido
só muda IRPJ/CSLL/PIS/COFINS.

---

## Lucro Real

Base legal: **RIR/2018**. PIS/COFINS no **regime não-cumulativo** (com crédito).

### Quem é obrigado / quem escolhe

Obrigatório se: receita > R$ 78 mi/ano; bancos e instituições financeiras; lucros/rendimentos do
exterior; benefícios fiscais de isenção/redução; factoring. Demais empresas **podem optar**
(vantajoso quando a margem real é baixa — paga imposto sobre o lucro efetivo, não presumido).

### IRPJ e CSLL — sobre lucro REAL (contábil ajustado)

```
Lucro Real = Lucro_líquido_contábil
             + Adições (despesas não dedutíveis: multas, brindes, parte de provisões…)
             − Exclusões (receitas não tributáveis, dividendos recebidos…)
             − Compensação de prejuízos fiscais (limitada a 30% do lucro do período)

IRPJ = Lucro_Real × 15% + adicional 10% sobre o que exceder R$ 20.000/mês
CSLL = Base_CSLL_ajustada × 9%
```

O ajuste é controlado no **LALUR / e-LALUR (parte A e B)** e na **ECF**. Apuração **trimestral**
ou **anual com estimativas mensais** (por balancete de suspensão/redução).

### PIS e COFINS — NÃO-CUMULATIVO (com crédito)

```
PIS    = (Receita × 1,65%) − créditos × 1,65%
COFINS = (Receita × 7,60%) − créditos × 7,60%
```

Crédito sobre **insumos, energia, aluguéis, fretes, depreciação** etc. (Leis 10.637/02 e
10.833/03) — ver `credito-debito-impostos.md`. É o que torna o não-cumulativo viável apesar da
alíquota nominal muito maior (9,25% vs 3,65%).

### Obrigações

ECD (escrituração contábil digital), ECF (escrituração contábil fiscal), EFD-Contribuições
(PIS/COFINS), SPED Fiscal (ICMS/IPI). DARF mensal de PIS/COFINS; DARF trimestral/mensal de
IRPJ/CSLL.

---

## Comparativo e escolha

| Critério | Simples | Presumido | Real |
|---|---|---|---|
| Teto de receita | R$ 4,8 mi | R$ 78 mi | sem teto |
| Tributos | DAS unificado | separados | separados |
| PIS/COFINS | dentro do DAS | cumulativo 3,65% | não-cumulativo 9,25% c/ crédito |
| Crédito PIS/COFINS | não | não | sim |
| IRPJ/CSLL sobre | receita (anexo) | lucro presumido | lucro real |
| Melhor quando | receita baixa, folha alta (Fator R) | margem alta, poucos insumos | margem baixa, muitos insumos/créditos |
| Complexidade | baixa | média | alta |

Regra prática: **margem de lucro real baixa** ou **muitos créditos** → Real tende a ganhar.
**Margem alta e estrutura enxuta** → Presumido. **Receita pequena** → Simples (mas cheque o Fator
R e a segregação de ST). **A escolha é anual e exige cálculo comparativo — recomende o contador.**

---

## Reforma Tributária e os regimes

EC 132/2023 + LC 214/2025:

- **Simples Nacional permanece**, mas o optante poderá escolher recolher **IBS/CBS por fora** do
  DAS para **transferir crédito** ao cliente (hoje o Simples transfere crédito limitado). Quem
  vende para outras empresas pode passar a preferir essa via.
- **Presumido e Real**: PIS/COFINS → **CBS**; ICMS/ISS → **IBS**; ambos **totalmente
  não-cumulativos** (crédito amplo, "imposto sobre imposto" tende a acabar). IPI tende a zerar
  (salvo concorrência com a ZFM), surgindo o **IS** sobre itens específicos.
- Transição **2026–2033**. Em 2026 há alíquota-teste (CBS 0,9% / IBS 0,1%) só para calibrar.
  Ao orientar planejamento, **confirme a vigência do ano** — as regras mudam a cada fase.
