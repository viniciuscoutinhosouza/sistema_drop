---
name: fiscal-tributario-nfe
description: Conhecimento fiscal-tributário e de documentos fiscais eletrônicos brasileiros. Use SEMPRE que o usuário mencionar imposto, tributo, Simples Nacional, Lucro Presumido, Lucro Real, apuração, DAS, DARF, alíquota, base de cálculo, crédito/débito de imposto, ICMS, ICMS-ST, DIFAL, FECP, IPI, PIS, COFINS, ISS, CST, CSOSN, CFOP, NCM, CEST, NF-e, NFC-e, CT-e, MDF-e, DANFE, Carta de Correção (CC-e), cancelamento de nota, inutilização, manifestação do destinatário, nota complementar/ajuste/devolução, certificado A1, SEFAZ, ou regime tributário de empresa. Cobre cálculo e apuração de impostos nos três regimes, regras de crédito e débito (não-cumulatividade), emissão e configuração de NF-e/NFC-e, e todo o ciclo de eventos fiscais (correção, cancelamento, devolução, transporte). Use também ao projetar, configurar ou depurar o módulo fiscal do Sistema Drop.
---

# Fiscal e Tributário (Brasil) — Skill de conhecimento

Esta skill concentra o conhecimento necessário para **calcular impostos**, **apurar tributos** nos
três regimes (Simples Nacional, Lucro Presumido, Lucro Real), aplicar corretamente as regras de
**crédito e débito** e **emitir, configurar e corrigir documentos fiscais eletrônicos** (NF-e 55,
NFC-e 65, CT-e 57, MDF-e 58) e seus eventos. Ela prioriza a regra correta e fundamentada — erro
fiscal vira multa, autuação e bloqueio de Inscrição Estadual.

## Como usar esta skill

A skill segue **progressive disclosure**: este arquivo dá a visão geral e aponta a referência
detalhada. **Sempre leia o arquivo de referência relevante antes de calcular um imposto, escolher
um CST/CSOSN/CFOP ou orientar sobre um evento fiscal** — o detalhe que evita o erro está lá.

| Tarefa do usuário | Leia primeiro |
|---|---|
| Enquadrar regime, calcular DAS/Simples, IRPJ/CSLL/PIS/COFINS no Presumido ou Real, apuração | `references/regimes-tributarios.md` |
| Crédito x débito, não-cumulatividade, ICMS-ST, DIFAL, FECP, IPI, PIS/COFINS, ISS | `references/credito-debito-impostos.md` |
| Configurar emitente, emitir NF-e 55 / NFC-e 65, campos da nota, fluxo SEFAZ, ambientes | `references/emissao-nfe.md` |
| Carta de Correção, cancelar, inutilizar, manifestar, nota complementar/ajuste/devolução | `references/eventos-fiscais.md` |
| CT-e, MDF-e, dados de transporte na NF-e, modalidade de frete | `references/documentos-transporte.md` |
| Tabelas: CST ICMS, CSOSN, CST PIS/COFINS/IPI, CFOP, NCM, CEST, origem, indicadores | `references/tabelas-fiscais.md` |

Para a **implementação técnica** no backend do Sistema Drop (DDL Oracle, camada `fiscal/` em
Python, webservices SOAP da SEFAZ, mTLS, assinatura A1, fila/worker, numeração atômica), a fonte
canônica é [DOCs/guia-implementacao-nfe-oracle.md](../../../DOCs/guia-implementacao-nfe-oracle.md).
Esta skill cobre a **regra fiscal**; aquele guia cobre o **código**.

## Princípios não-negociáveis (violar = passivo fiscal)

- **Alíquota e base variam por UF e por período.** ICMS, ICMS-ST/MVA, FECP, DIFAL e prazos de
  evento mudam por UF e por vigência. Nunca crave um número sem amarrar à UF e ao período; quando
  variar, **diga "confirme no RICMS de {UF}"**.
- **Regime define a coluna do imposto.** Simples Nacional usa **CSOSN** e recolhe tudo no **DAS**;
  Regime Normal (Presumido/Real) usa **CST** e destaca ICMS/IPI/PIS/COFINS na nota. Não misture.
- **Crédito só onde a lei permite.** ICMS/IPI são não-cumulativos por natureza. PIS/COFINS só dão
  crédito no **não-cumulativo (Lucro Real)** — no cumulativo (Presumido) e no Simples **não há
  crédito de entrada**.
- **Cada erro tem o seu instrumento.** Carta de Correção corrige só o que **não** muda valor,
  imposto, destinatário nem a operação. Para o resto: complementar, ajuste, devolução,
  cancelamento ou inutilização — ver `eventos-fiscais.md`.
- **Documento fiscal autorizado é imutável.** Depois do `cStat=100` o XML não se altera — só se
  acrescentam **eventos**. Snapshot do item (NCM/CFOP/CSOSN/alíquota) é congelado na emissão.
- **Nunca confunda nominal com efetivo no Simples.** A alíquota do anexo é nominal; aplica-se a
  **efetiva** = `(RBT12 × Nominal − Parcela a Deduzir) / RBT12`.
- **Você orienta; o contador assina.** Em decisão tributária material, recomende validar com a
  contabilidade. A skill não substitui profissional habilitado.

## Mapa-relâmpago dos tributos brasileiros

| Tributo | Competência | Incide sobre | Não-cumulativo? |
|---|---|---|---|
| **ICMS** | Estadual | Circulação de mercadoria, transporte, comunicação | Sim |
| **ICMS-ST** | Estadual | Antecipação do ICMS de toda a cadeia (substituto recolhe) | — (encerra a cadeia) |
| **DIFAL** | Estadual (partilha origem/destino) | Diferença de alíquota inter-UF (EC 87/2015) | — |
| **FECP/FCP** | Estadual | Adicional p/ Fundo de Combate à Pobreza (alguns produtos/UFs) | — |
| **IPI** | Federal | Produto industrializado (saída da indústria/importação) | Sim |
| **PIS** | Federal | Faturamento/receita | Só no Lucro Real |
| **COFINS** | Federal | Faturamento/receita | Só no Lucro Real |
| **IRPJ** | Federal | Lucro (presumido ou real) | — |
| **CSLL** | Federal | Lucro (base presumida ou real) | — |
| **ISS / ISSQN** | Municipal | Serviços (Lista LC 116/2003) | — |
| **DAS** | Unificado (Simples) | Receita bruta — recolhe IRPJ/CSLL/PIS/COFINS/IPI/ICMS/ISS/CPP juntos | — |

### Reforma Tributária (EC 132/2023 + LC 214/2025) — em transição

O modelo atual (ICMS + ISS + PIS + COFINS + IPI) está sendo substituído por **IVA dual**:
- **CBS** (federal) substitui PIS + COFINS (e o IPI tende a zerar, salvo ZFM).
- **IBS** (estadual+municipal) substitui ICMS + ISS.
- **IS** (Imposto Seletivo, "imposto do pecado") sobre bens prejudiciais à saúde/meio ambiente.

Transição **2026–2033** (2026 alíquota-teste; 2027 CBS cheia + IS; 2029–2032 IBS progressivo;
2033 modelo pleno). A NF-e já tem grupos para IBS/CBS/IS via **NT 2025.002**. Ao orientar algo de
médio prazo, **sinalize que a Reforma muda as regras** e confirme a vigência. Detalhes em
`regimes-tributarios.md` e `credito-debito-impostos.md`.

## Fluxo recomendado ao atacar uma tarefa fiscal

1. **Identifique o regime** da empresa emitente (`NFE_EMPRESAS.CRT`) — define CSOSN vs CST e a
   apuração. → `regimes-tributarios.md`
2. **Classifique o produto/operação**: NCM, CEST, origem, CFOP (intra/inter-UF, finalidade) e se
   há ST. → `tabelas-fiscais.md`
3. **Calcule os tributos** da operação (ICMS próprio, ST, DIFAL, FECP, IPI, PIS/COFINS conforme
   regime), mostrando base e alíquota. → `credito-debito-impostos.md`
4. **Monte/emita o documento** com os grupos corretos no XML 4.00. → `emissao-nfe.md`
5. **Se algo deu errado depois de autorizada**, escolha o evento certo (correção, cancelamento,
   inutilização, devolução…). → `eventos-fiscais.md`
6. **Apure no fim do período** (DAS, apuração ICMS, DARF de PIS/COFINS/IRPJ/CSLL). →
   `regimes-tributarios.md`

## Convenções ao responder

- Sempre que calcular, **mostre a conta** (base × alíquota = valor; débitos − créditos = a
  recolher). Números redondos sem memória de cálculo são suspeitos.
- Cite a **norma** (LC 123 art./anexo, RICMS de {UF}, Lei 10.833, NT da NF-e) e a **vigência**.
- Declare brevemente qual referência está consultando ("vou conferir `credito-debito-impostos.md`
  antes de calcular a ST") para o usuário acompanhar o raciocínio.
- Em dúvida sobre número que muda por UF/período: **não invente — sinalize a variável**.
