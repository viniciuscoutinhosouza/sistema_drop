# 07 — Mercado Ads (Publicidade Paga)

Mercado Ads é a plataforma de publicidade do ML. Bem usado, multiplica vendas. Mal usado, queima dinheiro. Esta referência ensina a usar bem.

## Sumário

1. [Quando começar a investir em Ads](#quando-começar)
2. [Tipos de campanha](#tipos-de-campanha)
3. [Product Ads — o feijão com arroz](#product-ads)
4. [Métricas que importam](#métricas)
5. [ACOS — o número mágico](#acos)
6. [Estratégias por objetivo](#estratégias)
7. [Palavras-chave e segmentação](#palavras-chave)
8. [Gestão de campanhas — modo personalizado](#modo-personalizado)
9. [Otimização contínua](#otimização)
10. [Erros que queimam dinheiro](#erros)

## Quando começar

⚠️ **Nem todo seller deveria fazer Ads.** Pré-requisitos:

✅ **Reputação amarela ou superior** (mínimo). Verde idealmente.
✅ **Pelo menos 30 vendas concluídas** no histórico.
✅ **Anúncios com Score de Qualidade ≥ 80**.
✅ **Margem com reserva de 10–15% pra Ads** já incluída no preço.
✅ **Estoque garantido** dos produtos que vai promover.

Sem esses pré-requisitos:
- Reputação ruim → ML cobra CPC mais alto (algoritmo penaliza).
- Anúncios com score baixo → cliques caros que não convertem.
- Margem apertada → ACOS estrangula o lucro.
- Estoque baixo → vai gastar Ads e cancelar venda por falta.

**Investir em Ads sem fundamentos é como ligar o motor de um carro sem pneus.**

## Tipos de Campanha

Mercado Ads tem três grandes famílias de produtos publicitários:

### 1. Product Ads (performance)

**O foco da maioria dos sellers.** Anúncios patrocinados que aparecem em **posições de destaque** dentro do Mercado Livre — primeiras posições da busca, carrosséis de "produtos patrocinados", páginas de produto.

- **Cobrança**: CPC (custo por clique).
- **Objetivo**: vendas diretas.
- **Quem usa**: praticamente todo seller que faz Ads.

### 2. Brand Ads (marca)

Anúncios de **marca**, não de produto individual. Foca em construir reconhecimento.

- **Cobrança**: CPM (custo por mil impressões) ou CPC.
- **Objetivo**: brand awareness, presença no topo da busca por keywords da marca.
- **Quem usa**: lojas oficiais, marcas estabelecidas.

### 3. Display Ads (banners)

Banners visuais em espaços de alto impacto — home do ML, páginas de categoria, carrosséis especiais.

- **Cobrança**: CPM ou pacote fixo.
- **Objetivo**: alcance massivo, datas comerciais, lançamentos.
- **Quem usa**: marcas grandes em datas como Black Friday, Natal.

Para o vendedor médio (PME, MercadoLíder), **Product Ads é onde 95% do orçamento deve ir**. Brand Ads e Display são pra grandes marcas com orçamento de marketing.

## Product Ads

### Como funciona

Você ativa Product Ads → seus anúncios entram em **leilão** de palavras-chave → quando comprador busca termo relacionado, ML decide se mostra seu anúncio (e em que posição) baseado em:

- **Lance** (quanto você está disposto a pagar por clique — CPC).
- **Ad Score** (qualidade do anúncio: palavras-chave, preço, fotos, perguntas, ficha técnica, reputação, reclamações).
- **Ad Rank** = CPC × Ad Score.

Quanto **maior o Ad Rank**, melhor sua posição. Ou seja: você não precisa ter o lance mais alto se seu Ad Score for excelente.

### Onde aparecem

- **Posições 1 e 2 da busca** (rotuladas como "Patrocinado" / "Produto patrocinado").
- **Carrosséis de produtos patrocinados** em páginas de categoria.
- **Páginas de produto de concorrentes** (recomendações cruzadas).
- **App e desktop** ambos.

### Custo

- Modelo CPC: você paga **só quando alguém clica**.
- CPC varia por categoria e palavra-chave (de ~R$ 0,50 a R$ 5,00+).
- **Orçamento diário** definido por você (pode começar com R$ 30/dia).
- Se ninguém clicar, não gasta nada.

### Como ativar

1. Painel de Vendas → **Publicidade** → Product Ads.
2. ML mostra anúncios elegíveis (precisam de reputação + score mínimos).
3. Selecione produtos.
4. Defina orçamento diário e estratégia.
5. Ative.

## Métricas

### Métricas básicas

- **Impressões**: quantas vezes seu anúncio apareceu.
- **Cliques**: quantos cliques recebeu.
- **CTR** (Click-Through Rate): cliques ÷ impressões. Indica relevância visual do anúncio.
- **CPC** (Custo por Clique): valor médio pago por clique.
- **Vendas atribuídas**: quantas vendas vieram de cliques no anúncio (em janela de atribuição).
- **Receita atribuída**: faturamento gerado por vendas atribuídas.
- **Investimento**: total gasto em Ads no período.

### Métricas críticas

- **ACOS** (Advertising Cost of Sales) = Investimento ÷ Receita × 100.
- **Conversão** = Vendas ÷ Cliques × 100.
- **CPV** (Custo por Venda) = Investimento ÷ Vendas.
- **ROAS** (Return on Ad Spend) = Receita ÷ Investimento. (inverso do ACOS)

### Métricas internas do ML

- **Ad Score**: pontuação de qualidade do anúncio (0–100). Influencia posição.
- **Ad Rank**: pontuação de leilão (CPC × Ad Score). Define posição final.

## ACOS

ACOS é **o número que determina se sua campanha dá lucro ou prejuízo**.

### Fórmula

```
ACOS = (Investimento em Ads ÷ Receita gerada) × 100
```

Exemplo: gastou R$ 200 em Ads, gerou R$ 1.000 em vendas → ACOS = 20%.

### Qual ACOS é bom?

Depende da **margem do produto**. Regra geral:

```
ACOS máximo viável = Margem líquida do produto (em %)
```

Se seu produto tem margem líquida de 25%, ACOS de 25% significa **break-even** (não dá lucro nem prejuízo). ACOS abaixo de 25% = lucro. Acima de 25% = prejuízo direto.

### ACOS por estratégia

- **ACOS 5–15%**: campanha super eficiente. Geralmente em produtos best-sellers já consolidados.
- **ACOS 15–25%**: campanha boa. Equilíbrio entre crescimento e lucro.
- **ACOS 25–40%**: aceitável **se** for produto novo (fase de aquisição) ou se margem for alta (>30%).
- **ACOS > 40%**: alerta. Geralmente prejuízo. Precisa otimizar ou pausar.

### Trade-off entre ACOS baixo e volume

Se você quer **ACOS baixíssimo**, lance baixo, fica em poucas posições, vende pouco volume.
Se você quer **volume alto**, lance maior, ACOS sobe.

A meta não é ACOS minimizado — é **lucro líquido total maximizado**. Às vezes ACOS de 30% gerando R$ 50 mil em vendas vale mais que ACOS de 10% gerando R$ 5 mil.

## Estratégias

Mercado Ads permite escolher uma **estratégia por campanha**. As principais:

### Estratégia de Rentabilidade

- Foco: **manter ROI alto**.
- Como: ML conserva o ACOS baixo, mesmo que limite volume.
- **Ideal para**: produtos best-sellers já consolidados, com margem apertada, onde você quer "manter as vendas que já tem" com pouco esforço extra.
- ACOS típico: 10–20%.

### Estratégia de Crescimento

- Foco: **equilíbrio entre exposição e ROI**.
- Como: ML aumenta exposição, ACOS sobe um pouco, volume cresce.
- **Ideal para**: produtos médios, onde você quer escalar mantendo lucro razoável.
- ACOS típico: 20–30%.

### Estratégia de Visibilidade

- Foco: **ganhar posição máxima na busca**.
- Como: ML investe agressivamente em CPC pra te colocar nas posições 1-2.
- **Ideal para**: produtos novos (precisam de tração inicial), categorias muito concorridas onde você precisa "comprar" presença.
- ACOS típico: 30–50% (aceito porque é fase de aquisição).

### Como escolher

Não existe "a melhor". Cada produto tem sua estratégia ideal:

- Produto **novo, categoria concorrida** → Visibilidade nos primeiros 30 dias, depois Crescimento, depois Rentabilidade.
- Produto **maduro, best-seller** → Rentabilidade.
- Produto **médio, quer crescer** → Crescimento.

## Palavras-chave

ML não dá controle granular sobre palavras-chave como Google ou Amazon. O sistema é **automatizado** — o algoritmo escolhe pra que palavras seu produto aparece baseado em título, ficha técnica, descrição.

### Como influenciar indiretamente

1. **Título otimizado**: as palavras no título são as primeiras consideradas pelo algoritmo. Inclua termos de busca relevantes.
2. **Ficha técnica completa**: campos preenchidos viram filtros e palavras-chave indexadas.
3. **Descrição rica**: complemento de palavras-chave secundárias.
4. **Atributos específicos**: marca, modelo, características técnicas.

### Como descobrir as palavras-chave certas

- **Dados do próprio painel de Mercado Ads**: ele mostra **termos de busca** que geraram cliques no seu anúncio. Use isso pra otimizar título.
- **Autocompletar do ML**: digite o produto na busca e veja sugestões reais.
- **Ferramentas externas** (Nubimetrics, Hunter): rankings de palavras-chave por categoria.
- **Pensar como comprador**: o que ele digitaria? Não use jargão técnico se cliente não usa.

### Estrutura ideal do título com keywords

```
[Palavra-chave principal] [Marca] [Modelo] [Spec1] [Spec2]
```

Exemplo: `Mouse Gamer Logitech G502 Hero 25K DPI 11 Botões RGB`

A palavra-chave principal ("Mouse Gamer") fica no início, capturando buscas amplas. Marca e modelo capturam buscas específicas. Specs capturam filtros.

## Modo Personalizado

Por padrão, Product Ads vem em **modo automático**: 1 campanha com todos os anúncios e 1 orçamento global. **Não recomendado.**

### Por que mudar para Personalizado

- Permite **estratégias diferentes** para grupos de produtos.
- Permite **orçamentos separados** por categoria.
- Permite **ACOS objetivo** diferente por campanha.
- Você consegue **pausar campanhas ruins** sem afetar as boas.

### Como mudar

No painel de Publicidade → Configurações (canto superior direito) → **Modo Personalizado**.

### Estrutura recomendada de campanhas

Para vendedor com 50–100 SKUs, sugestão:

- **Campanha 1: Top Sellers (Rentabilidade)** — 5–10 best-sellers, ACOS objetivo baixo.
- **Campanha 2: Crescimento (Crescimento)** — 15–20 SKUs médios, ACOS objetivo médio.
- **Campanha 3: Lançamentos (Visibilidade)** — produtos novos, ACOS objetivo alto temporariamente.
- **Campanha 4: Datas Comerciais (Visibilidade)** — ativada só em Black Friday, Dia das Mães, etc.
- **Campanha 5: Liquidação (Rentabilidade extrema)** — produtos parados, queima de estoque.

## Otimização

Ads não é "configurar e esquecer". Otimização contínua:

### Diariamente

- Verificar gasto vs orçamento.
- Identificar campanhas com gasto disparado e venda baixa (problema).

### Semanalmente

- **ACOS por campanha**: ajustar lances ou pausar quem está acima do alvo.
- **Adicionar produtos novos** que estão começando a vender bem organicamente — Ads acelera ainda mais.
- **Pausar produtos com ACOS muito alto** que não justifica.
- **Verificar Ad Score**: anúncios com score baixo têm CPC mais alto. Otimize o anúncio.

### Mensalmente

- **Análise consolidada**: quanto investiu, quanto retornou, ACOS médio.
- **Lifetime Value**: cliente que compra via Ads volta a comprar? Se sim, ACOS pode ser mais agressivo.
- **Reajustar estratégias**: produtos que viraram best-sellers podem migrar para Rentabilidade. Produtos que não respondem podem sair.
- **Investimento total vs receita Ads**: % do faturamento que vem de Ads (saudável: 15-30% para sellers em crescimento).

### Otimizar o anúncio em si (não só a campanha)

Se um anúncio gasta muito em Ads e não converte, o problema não é Ads — é o **anúncio**:

- Foto principal não atrativa? Troque.
- Título sem palavra-chave forte? Refaça.
- Preço desalinhado com mercado? Ajuste.
- Ficha técnica incompleta? Preencha.
- Sem frete grátis enquanto concorrente tem? Reavalie.

**Ads amplifica o que existe.** Se anúncio orgânico não vende, Ads não vai resgatar — só vai tornar o problema mais caro.

## Erros

### 1. Ativar Ads em conta nova / cinza

CPC sai caro, Ad Score baixo, conversão zero. Espere reputação verde.

### 2. Modo automático com 100 SKUs misturados

Orçamento queima nos SKUs errados. **Sempre Personalizado**.

### 3. Não definir ACOS objetivo

Sem alvo, não há otimização. Defina ACOS objetivo por campanha (ex: Rentabilidade = 15%, Crescimento = 25%).

### 4. ACOS alto e não pausar

Vendedor vê ACOS de 60% e acha que "vai melhorar". Não vai. Pause, otimize anúncio, reative.

### 5. Tirar Ads dos best-sellers achando que "já vendem sozinhos"

Se você desliga Ads, concorrente liga. Você cai posição. Mantém Ads moderado nos best-sellers (estratégia Rentabilidade).

### 6. Investir igual em produtos com margens diferentes

Produto com 40% de margem aguenta ACOS 30%. Produto com 12% de margem não aguenta ACOS 15%. Diferencie campanhas.

### 7. Esquecer que Ads gasta mesmo sem venda

CPC é cobrado por clique, não por venda. Se anúncio está caro e converte mal, você gasta sem retorno.

### 8. Não correlacionar com promoções

Quando ativa promoção (oferta relâmpago, oferta do dia), aumente Ads naquele SKU pra alavancar visibilidade x desconto. Combo poderoso.

### 9. Achar que Ads substitui SEO orgânico

Ads é **alavanca temporária**. SEO orgânico é o **alicerce permanente**. Vendedor maduro tem 60-70% de vendas orgânicas e usa Ads pra acelerar/proteger.

### 10. Não olhar dados, só intuição

Ads é dado. Olhe relatórios semanais. Decida com números.

## Próximos passos

- `08-promocoes-campanhas.md` — combinar Ads com promoções pra alavancar
- `04-anuncios-que-vendem.md` — otimizar anúncio antes de Ads
- `03-taxas-fretes-precificacao.md` — calcular margem com reserva pra Ads
