# Documentos de transporte — CT-e, MDF-e e transporte na NF-e

Referência dos documentos fiscais ligados ao **transporte** e de como declarar frete/transporte
**dentro da NF-e**.

## Sumário

1. [Visão geral dos documentos](#visão-geral-dos-documentos)
2. [Modalidade de frete na NF-e (`modFrete`)](#modalidade-de-frete-na-nf-e-modfrete)
3. [Grupo de transporte da NF-e](#grupo-de-transporte-da-nf-e)
4. [CT-e — Conhecimento de Transporte (modelo 57)](#ct-e--conhecimento-de-transporte-modelo-57)
5. [MDF-e — Manifesto de Documentos Fiscais (modelo 58)](#mdf-e--manifesto-de-documentos-fiscais-modelo-58)
6. [Quem emite o quê](#quem-emite-o-quê)

---

## Visão geral dos documentos

| Modelo | Documento | Emite | Para quê |
|---|---|---|---|
| 55 | NF-e | vendedor/remetente | acoberta a **mercadoria** |
| **57** | **CT-e** | **transportadora** | acoberta o **serviço de transporte** (tem ICMS próprio sobre o frete) |
| **58** | **MDF-e** | transportador / remetente com frete próprio | **agrupa** as NF-e/CT-e de um carregamento num único manifesto por veículo/viagem |
| 67 | CT-e OS | transportadora | transporte de pessoas / outros serviços |

> A NF-e **não** substitui o CT-e: a NF-e cobre a mercadoria, o **CT-e cobre o serviço de
> transporte** quando há transportador contratado (frete por conta de terceiros). Se o próprio
> remetente transporta (frota própria), não há CT-e, mas pode haver MDF-e.

---

## Modalidade de frete na NF-e (`modFrete`)

Campo `transp/modFrete` — **quem paga/responsabiliza pelo frete**:

| Código | Modalidade | Quem contrata/paga |
|---|---|---|
| **0** | Por conta do **emitente** (CIF) | vendedor |
| **1** | Por conta do **destinatário/remetente** (FOB) | comprador |
| **2** | Por conta de **terceiros** | um terceiro |
| **3** | Transporte próprio por conta do **remetente** | remetente, frota própria |
| **4** | Transporte próprio por conta do **destinatário** | destinatário, frota própria |
| **9** | **Sem transporte** (ex.: serviço, retirada no balcão) | — |

> **CIF** = Cost, Insurance and Freight (emitente arca e geralmente embute no preço → entra na
> base de ICMS). **FOB** = Free On Board (destinatário arca; frete cobrado à parte pela
> transportadora via CT-e). A escolha afeta a **base de cálculo do ICMS** (frete CIF compõe a
> base).

---

## Grupo de transporte da NF-e

Dentro de `transp`:
- `modFrete` (acima).
- `transporta`: dados da transportadora (CNPJ/CPF, IE, xNome, endereço, UF) — quando conhecida.
- `veicTransp` / `reboque`: placa e UF do veículo (quando aplicável).
- `vol` (volumes): `qVol` (quantidade), `esp` (espécie: caixa, palete…), `marca`, `nVol`,
  `pesoL` (peso líquido kg), `pesoB` (peso bruto kg).

No Drop, esses dados saem de `NFE_TRANSPORTADORAS` + `NFE_NOTAS.TRANSPORTE_MODALIDADE`.

---

## CT-e — Conhecimento de Transporte (modelo 57)

Documento fiscal do **serviço de transporte**. Tem **ICMS próprio sobre o valor do frete**
(alíquota de transporte da UF; operação interestadual usa a alíquota inter). Estrutura análoga à
NF-e (autorização SEFAZ, chave de 44 dígitos, eventos próprios).

**Atores do CT-e:**
- **Remetente** — quem despacha a mercadoria.
- **Destinatário** — quem recebe.
- **Tomador** — quem **paga o frete** (pode ser remetente, destinatário ou terceiro). O tomador é
  quem toma o **crédito de ICMS** do transporte (se contribuinte e a operação permitir).
- **Expedidor / Recebedor** — em redespacho/subcontratação.

**Tipos de serviço (`tpServ`):** 0 normal, 1 subcontratação, 2 redespacho, 3 redespacho
intermediário, 4 serviço vinculado a multimodal.

**Eventos do CT-e:** Carta de Correção (CC-e CT-e), cancelamento (prazo da UF), e
**CT-e de Anulação / CT-e Substituto** (quando o erro não cabe em CC-e — análogo à
complementar/ajuste da NF-e).

---

## MDF-e — Manifesto de Documentos Fiscais (modelo 58)

**Agrupa** todos os documentos (NF-e e/ou CT-e) de **um carregamento**, por **veículo + viagem**,
num único manifesto. Obrigatório quando há **carga fracionada** de vários documentos no mesmo
transporte, em operação interestadual, e em transporte próprio do remetente.

- Vincula as **chaves** das NF-e/CT-e transportadas.
- Informa veículo, motorista (CPF), UF de início e fim do percurso, e o **CIOT** quando aplicável.
- Eventos: **encerramento** (obrigatório ao fim da viagem — sem encerrar, o MDF-e fica "aberto" e
  trava emissões futuras), cancelamento, inclusão de motorista/DF-e, registro de passagem.

> **Pegadinha operacional:** esquecer de **encerrar** o MDF-e é o erro mais comum — ele fica
> pendente e a SEFAZ pode bloquear novos manifestos. Encerre ao concluir a entrega.

---

## Quem emite o quê

| Cenário | NF-e (55) | CT-e (57) | MDF-e (58) |
|---|---|---|---|
| Venda com frete por transportadora (FOB/CIF terceirizado) | remetente | transportadora | transportadora |
| Venda com frota própria do remetente, interestadual / carga fracionada | remetente | — | remetente |
| Venda com retirada no balcão (sem transporte) | remetente (`modFrete=9`) | — | — |
| Transporte de carga de múltiplos remetentes num caminhão | cada remetente | transportadora (1 por carga/tomador) | transportadora (1 por veículo/viagem) |

> Para a **regra fiscal do ICMS sobre o frete** (base, alíquota, crédito do tomador), ver
> `credito-debito-impostos.md`. Para a **implementação** dos webservices (CT-e/MDF-e têm WS SOAP
> próprios, separados dos da NF-e), seguir o padrão do guia de implementação e estender o catálogo
> de endpoints por UF.
