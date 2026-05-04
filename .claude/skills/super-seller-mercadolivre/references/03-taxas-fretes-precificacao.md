# 03 — Taxas, Fretes e Precificação

A diferença entre seller que cresce e seller que quebra está aqui. Esta é a referência mais importante. Domínio sobre custos = lucro real.

## Sumário

1. [Mapa completo de custos do seller](#mapa-de-custos)
2. [Comissão por categoria — faixas práticas](#comissão-por-categoria)
3. [Custo fixo e a armadilha do preço baixo](#custo-fixo)
4. [Frete grátis — quem paga e quanto](#frete-grátis)
5. [Clássico vs Premium — qual escolher](#clássico-vs-premium)
6. [Fórmula de precificação completa](#fórmula-de-precificação)
7. [Exemplos numéricos resolvidos](#exemplos-numéricos)
8. [Erros de precificação que destroem margem](#erros-de-precificação)
9. [Datas importantes de mudança de tarifas](#datas-importantes)

## Mapa de custos

Todo pedido no Mercado Livre tem **6 blocos de custos** que precisam estar na sua planilha:

1. **Custo do produto** (CP) — preço de aquisição + impostos de entrada (ICMS, IPI se aplicável).
2. **Comissão da categoria** — percentual sobre o valor da venda. Varia por categoria e tipo de anúncio.
3. **Custo fixo / operacional** — taxa adicional para produtos abaixo de R$ 79.
4. **Logística** — frete subsidiado (parte ou total quando há frete grátis), custos de Full ou Flex, embalagem.
5. **Mercado Pago** — taxa de antecipação se você optar por receber antes do prazo padrão.
6. **Mercado Ads** — quando ativo. Tratado como custo direto na precificação (10-15% do preço).

Mais os custos **fora do ML**: embalagem, mão de obra, impostos de saída (DAS MEI, Simples Nacional), aluguel/depósito, contador, energia, etc.

⚠️ **A maioria dos sellers iniciantes considera só 1 e 2.** Por isso "fatura R$ 50 mil" e "leva pra casa R$ 5 mil" — é matemática errada desde o começo.

## Comissão por categoria

A comissão varia de **10% a 19%** sobre o valor da venda, dependendo da categoria e do tipo de anúncio. Faixas médias praticadas (use como referência, **sempre confirme no Seller Center**):

| Categoria | Clássico (~) | Premium (~) |
|---|---|---|
| Eletrônicos / Celulares | 11–13% | 16–17% |
| Eletrodomésticos | 12–13% | 17–18% |
| Informática | 12–13% | 16–17% |
| Moda | 14% | 19% |
| Beleza | 14% | 19% |
| Esporte | 14% | 19% |
| Casa, móveis, decoração | 14% | 19% |
| Brinquedos | 13–14% | 18% |
| Ferramentas | 14% | 19% |
| Pet | 14% | 19% |
| Autopeças | 12–13% | 16–17% |
| Alimentos e bebidas | 12% | (regras especiais) |
| Livros | reduzida | reduzida |
| Supermercado | regras próprias | regras próprias |

⚠️ **Subcategorias variam.** "Eletrônicos > Áudio > Fones" pode ter percentual diferente de "Eletrônicos > TV". Sempre olhe a **subcategoria exata**.

A comissão é cobrada sobre o **valor total da venda**, **incluindo frete cobrado do comprador**. Se o cliente paga R$ 100 + R$ 20 de frete, a comissão incide sobre R$ 120.

## Custo fixo

Para produtos com preço abaixo de R$ 79 (e acima de R$ 12,50), o ML cobra **custo fixo por unidade vendida**, somado à comissão.

Valores históricos (referência, valida no Seller Center):

- Faixa R$ 12,50–R$ 19,99: ~R$ 5,50 por unidade
- Faixa R$ 20,00–R$ 78,99: ~R$ 6,00–R$ 6,75 por unidade

Para produtos abaixo de R$ 12,50: ML cobra **metade do valor do produto** como tarifa em vez de custo fixo. Ex: produto a R$ 8 → tarifa de R$ 4 + comissão sobre R$ 8.

⚠️ **Mudança em 2026**: o ML iniciou transição do "custo fixo único" para um **custo operacional variável** (baseado em peso, dimensões e preço). Produtos pequenos e leves abaixo de R$ 79 podem se beneficiar com custo menor; produtos grandes/pesados podem pagar mais. **Sempre verifique no Seller Center** a tarifa atualizada do seu SKU específico.

### Estratégias para escapar da armadilha de baixo ticket

1. **Kits**: combine 2-3 unidades pra ultrapassar R$ 79. Ex: cabo USB R$ 25/un → kit com 3 cabos por R$ 75 ou kit com 4 por R$ 100.
2. **Combos cross-sell**: cabo + carregador + capa, em vez de cada um separado.
3. **Aumentar valor agregado**: kit com brinde (mesmo barato), versão "premium" do produto.
4. **Anúncio Grátis** (com limites): só pra testar produto antes de investir.

## Frete grátis

ML criou um sistema de incentivo onde **anúncios com frete grátis recebem mais visibilidade**. Para produtos a partir de R$ 79, o ML **subsidia parte do frete** com desconto baseado na sua reputação.

### Desconto no subsídio de frete grátis (referência)

| Reputação | Desconto no frete grátis (produtos novos a partir de R$ 79 ou Premium) |
|---|---|
| Verde / MercadoLíder / Loja Oficial | até **50%** |
| Amarelo | ~40% |
| Laranja / Vermelho / Cinza | menor ou nenhum desconto |

Ou seja: se o frete custa R$ 30 e você é verde, o ML cobra R$ 15 de você (resto eles bancam). Se você é vermelho, paga R$ 30 inteiro.

### Como decidir se oferece frete grátis

Faça a conta:

```
Custo real do frete grátis para o vendedor =
  Custo total do frete × (1 − % desconto pela reputação)
```

Se o produto custa R$ 100, com frete original R$ 30, vendedor verde paga R$ 15 de frete.
- Sem frete grátis: vendedor recebe (R$ 100 − comissão) + cliente paga frete separado.
- Com frete grátis: vendedor recebe (R$ 100 − comissão − R$ 15 de frete subsidiado).

**Tradeoff**: frete grátis aumenta conversão (cliente prefere) mas reduz margem direta. Vale quando o aumento de conversão compensa.

### Quando frete grátis vale a pena

- Produto a partir de R$ 100 onde frete é < 15% do preço.
- Categoria muito competitiva onde concorrentes têm frete grátis.
- Vendedor verde/MercadoLíder (mais subsídio).
- Produto leve (frete barato em valor absoluto).

### Quando NÃO vale

- Produto pesado/volumoso (frete come margem).
- Produto barato (R$ 30) onde frete é 50%+ do preço.
- Vendedor com reputação baixa (sem subsídio decente).
- Categorias onde concorrentes não oferecem frete grátis (não há pressão).

## Clássico vs Premium

Decisão crítica em cada produto. Não há resposta universal.

### Clássico

- Comissão **menor** (~10–14%).
- **Sem parcelamento sem juros** pelo ML — comprador parcela com juros do cartão.
- Posição neutra no algoritmo.
- Sem benefícios extras.

**Bom para**: produtos com margem apertada, ticket baixo onde parcelamento não importa, produtos de impulso.

### Premium

- Comissão **maior** (~15–19%).
- **Parcelamento em até 12x sem juros** pago pelo ML.
- **Posição prioritária** nos resultados de busca.
- Mais visibilidade e conversão.

**Bom para**: produtos de ticket médio/alto (R$ 200+) onde parcelamento destrava conversão, produtos onde você quer dominar visibilidade, produtos com margem boa.

### Como escolher na prática

Faça a conta da margem em ambos os tipos. Se em **Premium você ainda fica com 15%+ de margem líquida**, e o ticket é alto, vai de Premium — o aumento de conversão compensa a comissão extra.

Se a margem em Premium fica abaixo de 10%, fique no Clássico. Se a margem em Clássico já é apertada, considere subir o preço ou abandonar o produto.

**Regra prática**: itens > R$ 300 quase sempre Premium. Itens < R$ 100 quase sempre Clássico. Itens entre R$ 100–300, depende da categoria e concorrência.

## Fórmula de precificação

A fórmula completa para descobrir **lucro líquido por venda**:

```
LUCRO LÍQUIDO = PREÇO DE VENDA
              − CUSTO DO PRODUTO (com impostos de entrada)
              − COMISSÃO ML (% × preço)
              − CUSTO FIXO (se preço < R$ 79)
              − FRETE SUBSIDIADO (parcial se frete grátis)
              − EMBALAGEM
              − IMPOSTO DE SAÍDA (DAS MEI ou Simples)
              − RESERVA ADS (10–15% do preço, se ativo)
              − RESERVA DEVOLUÇÃO (~2%)
              − ANTECIPAÇÃO MERCADO PAGO (se aplicável)
```

E a **margem líquida** = LUCRO LÍQUIDO ÷ PREÇO DE VENDA × 100.

### Para descobrir o preço necessário pra atingir margem alvo

Inverta a fórmula. Se você quer **20% de margem líquida**:

```
Preço de venda = (Custo + Custo fixo + Frete + Embalagem + Antecipação) ÷ 
                 (1 − Comissão − Imposto − Reserva Ads − Reserva devolução − 0.20)
```

Use planilha. Não tente fazer na cabeça.

## Exemplos numéricos

### Exemplo 1 — Fone de ouvido bluetooth, Clássico, R$ 110, frete grátis

```
Receita: R$ 110,00
Custo do produto: R$ 45,00
Embalagem: R$ 2,00
Comissão (Eletrônicos Clássico, 13%): R$ 14,30
Custo fixo: R$ 0 (preço > R$ 79)
Frete subsidiado (verde, 50% off de R$ 30): R$ 15,00
Imposto saída (Simples 6%): R$ 6,60
Reserva Ads (10%): R$ 11,00
Reserva devolução (2%): R$ 2,20
─────────────────────────────────────
Lucro líquido: R$ 13,90
Margem líquida: 12,6%
```

Nessa configuração, margem está apertada. Opções: subir preço pra R$ 119, baixar custo do produto, ou cortar Ads.

### Exemplo 2 — Mesmo fone em Premium, R$ 119, frete grátis

```
Receita: R$ 119,00
Custo do produto: R$ 45,00
Embalagem: R$ 2,00
Comissão (Premium, 17%): R$ 20,23
Frete subsidiado: R$ 15,00
Imposto saída (Simples 6%): R$ 7,14
Reserva Ads (10%): R$ 11,90
Reserva devolução (2%): R$ 2,38
─────────────────────────────────────
Lucro líquido: R$ 15,35
Margem líquida: 12,9%
```

Premium subiu a comissão em ~R$ 6, mas o preço subiu R$ 9 (parcelamento permite isso). Margem similar, mas conversão tende a ser maior. Decisão: Premium se conversão for ≥ 20% melhor.

### Exemplo 3 — Cabo USB, R$ 35, Clássico (armadilha do baixo ticket)

```
Receita: R$ 35,00
Custo do produto: R$ 8,00
Embalagem: R$ 1,50
Comissão (Eletrônicos Clássico, 13%): R$ 4,55
Custo fixo (preço < R$ 79): R$ 6,00
Frete (cobrado do cliente): R$ 0 (sem frete grátis)
Imposto saída (Simples 6%): R$ 2,10
Reserva Ads (10%): R$ 3,50
Reserva devolução (2%): R$ 0,70
─────────────────────────────────────
Lucro líquido: R$ 8,65
Margem líquida: 24,7%
```

Margem boa em %, mas absoluta (R$ 8,65/un) é baixa. Pra ganhar R$ 5.000/mês de lucro precisa vender ~580 unidades — operação intensa.

### Exemplo 4 — Kit de 3 cabos USB por R$ 79, Clássico, frete grátis

```
Receita: R$ 79,00
Custo dos produtos (3×R$ 8): R$ 24,00
Embalagem: R$ 2,50
Comissão (Eletrônicos Clássico, 13%): R$ 10,27
Custo fixo: R$ 0 (=R$ 79, na faixa de subsídio)
Frete subsidiado (verde, 50%): R$ 12,00
Imposto saída (Simples 6%): R$ 4,74
Reserva Ads (10%): R$ 7,90
Reserva devolução (2%): R$ 1,58
─────────────────────────────────────
Lucro líquido: R$ 16,01
Margem líquida: 20,3%
```

Lucro absoluto quase 2× maior que a venda individual. **Kit é a saída pra produtos baixos.**

## Erros de precificação

### 1. Markup fixo (multiplicar custo por 2,5 e pronto)

Não funciona. Categorias têm comissões diferentes. Frete varia. Custo fixo só atinge < R$ 79. **Calcule cada SKU individualmente.**

### 2. Esquecer impostos

DAS do MEI parece pouco mas vira 100% de margem em alguns produtos. Simples 6% sobre faturamento alto soma rápido. Inclua sempre.

### 3. Não reservar pra Ads

Você pode não estar usando Ads hoje, mas vai usar. Provisione 10% no preço. Se não usar, vira lucro extra. Se precisar usar, está coberto.

### 4. Ignorar devoluções

Mesmo o melhor seller tem 1-3% de devoluções. Provisionar 2% evita surpresa.

### 5. Não revisar preço quando custo muda

Fornecedor reajustou? Câmbio subiu? Comissão da categoria foi alterada? **Revise preço imediatamente**. Tem seller que descobre 3 meses depois que está vendendo no prejuízo.

### 6. Antecipar Mercado Pago indiscriminadamente

A taxa de antecipação some 1-3% por mês de antecipação. Se vc antecipa 30 dias = 1-3% direto. Use só pra capital de giro emergencial. Se possível, espere o prazo natural.

### 7. Definir preço pelo concorrente cego

"Vou cobrar R$ 1 a menos que o líder" sem fazer sua conta. Talvez o líder tenha custo R$ 20 menor que você. Você vende com prejuízo achando que está esperto.

### 8. Ignorar a curva de preço por canal

ML diferencia preço por canal (marketplace, mshops, mercadopago). Use a API de Preços ou painel para ajustar. Pode ter promoção em um canal e preço cheio em outro.

### 9. Não recalcular após reajuste de tarifa

ML reajusta tarifas algumas vezes por ano. Em 2026 várias mudaram (especialmente o custo operacional para produtos < R$ 79). Reagende: a cada reajuste, audite todos os SKUs.

### 10. Confiar 100% em calculadora externa

Calculadoras online (Toolspace, Hunter, Koncili, GoSmarter) ajudam, mas use sempre a calculadora oficial do ML como referência final, especialmente em decisões de R$ 1.000+ em pedido.

## Datas importantes

⚠️ **Em 2026 o Mercado Livre fez mudanças significativas:**

- Mudança do custo fixo único para **custo operacional variável** em produtos abaixo de R$ 79 (afetou todos sellers).
- Reajuste nas tarifas de frete grátis para produtos a partir de R$ 79.
- Flex passou a oferecer **frete grátis** para produtos R$ 19–78,99 a partir de **25 de novembro de 2025**.
- Mercado Shops virou "Minha Página" com modelo de assinatura mensal (~R$ 99/mês a partir de 2026).

Como o ML reajusta periodicamente, **sempre confirme valores no painel "Meus custos" do Seller Center antes de decisões financeiras grandes**.

## Checklist mensal de revisão de preços

No primeiro dia útil do mês, audite:

- [ ] Houve reajuste de comissão em alguma categoria?
- [ ] Custo de fornecedor mudou?
- [ ] Câmbio (se importado) mudou >5%?
- [ ] Tabela de frete subsidiado mudou?
- [ ] Algum SKU está com margem < 10%? (Avaliar pausar ou reajustar)
- [ ] Algum SKU está com margem > 35%? (Pode estar caro demais e perdendo conversão)
- [ ] Reservas (Ads, devolução) ainda fazem sentido?
- [ ] Há promoção subsidiada que vale a pena aceitar?

Esse checklist sozinho diferencia seller amador de profissional.
