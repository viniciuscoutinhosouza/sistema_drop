# 06 — Logística e Mercado Envios

A escolha logística pode dobrar (ou cortar pela metade) suas vendas. Esta referência ajuda a decidir entre Mercado Envios padrão, Flex e Full, e como otimizar cada um.

## Sumário

1. [Visão geral das modalidades](#modalidades)
2. [Mercado Envios padrão](#mercado-envios-padrão)
3. [Mercado Envios Flex](#mercado-envios-flex)
4. [Mercado Envios Full (Fulfillment)](#mercado-envios-full)
5. [Frete grátis — quando ativar](#frete-grátis)
6. [Como o algoritmo prioriza por logística](#algoritmo-logística)
7. [Embalagem e expedição](#embalagem-e-expedição)
8. [Quando combinar modalidades](#combinar-modalidades)

## Modalidades

| Modalidade | Quem cuida | Velocidade | Frete grátis | Reputação afetada por atraso? | Requer CNPJ? |
|---|---|---|---|---|---|
| **Mercado Envios padrão** (cross-docking, agência) | Vendedor posta, ML transporta | 3–8 dias | Subsidiado conforme reputação | Sim (atraso da transportadora também) | Não |
| **Flex** | Vendedor entrega via parceiro local | Mesmo dia ou 24h | Sim para R$ 19–78,99 (desde nov/2025) | Sim | Não |
| **Full (Fulfillment)** | ML faz tudo (estoca, embala, envia) | 1–2 dias | Subsidiado, com cashback até 40% pra MercadoLíder | **Não — atrasos são responsabilidade do ML** | Sim |
| **Não logístico** (`not_specified`) | Vendedor combina por fora | Variável | Não | Sim | Não |

## Mercado Envios padrão

Modalidade básica: você imprime etiqueta gerada pelo ML, leva ao Correios ou agência ML, e o ML cuida do transporte e rastreamento.

### Como funciona na prática

1. Pedido entra → ML envia notificação.
2. Vendedor imprime etiqueta no painel.
3. Embala produto com a etiqueta.
4. Leva à agência ML, ponto de coleta, ou agência Correios.
5. ML/Correios transporta.
6. Cliente recebe.

### Vantagens

- Sem custo fixo mensal.
- Qualquer vendedor pode usar.
- Etiqueta vem com frete já pago (descontado da venda).
- Rastreio integrado.
- Cobertura nacional.

### Desvantagens

- Vendedor depende da agilidade dos Correios (atrasos comuns).
- Atrasos da transportadora **afetam sua reputação** (independente da causa).
- Sem entrega no mesmo dia.
- Limites de peso e dimensões: máx 50 kg, maior lado 200 cm, soma das medidas até 300 cm.

### Boas práticas

1. **Postar no mesmo dia da venda** quando possível. Cada dia de atraso na postagem é dia adicional na entrega.
2. **Usar agência ML em vez dos Correios** quando disponível — geralmente mais ágil.
3. **Imprimir etiquetas em lote** (várias por vez) pra economizar tempo.
4. **Conferir endereço de envio**: erro de digitação = pacote volta = atraso = reclamação.
5. **Embalar com proteção adequada** — Correios é áspero com pacotes.

## Mercado Envios Flex

Entrega rápida em raio definido, geralmente pelas próprias mãos do vendedor ou por motoboy/transportadora local parceira.

### Requisitos

- **Reputação amarela ou superior**.
- **Cobertura disponível na cidade** (consulta no painel).
- **Mercado Envios ativo nos anúncios**.
- **Acordo com transportadora local** ou estrutura própria de entrega.

### Como funciona

1. Vendedor configura **horário de corte** (ex: até 14h compra hoje, recebe hoje; depois disso, recebe amanhã).
2. Vendedor define **área de cobertura** (raio até ~70km, ajustável por bairro/CEP).
3. Pedido cai → vendedor separa, embala, e a transportadora parceira coleta.
4. Entrega no mesmo dia ou no dia seguinte.

### Vantagens

- **Velocidade**: cliente recebe hoje ou amanhã. Aumenta drasticamente conversão.
- **Selo "Entrega rápida"** ou **"Entrega hoje"** no anúncio — destaque visual gigante.
- **Frete grátis** automaticamente em produtos R$ 19–78,99 (mudança de novembro/2025).
- **Maior controle** que o ME normal — vendedor escolhe transportadora.
- **Boost de algoritmo** — Flex tem prioridade nas buscas.

### Desvantagens

- **Custo de transportadora local** pode ser alto.
- **Cobertura limitada** (não funciona em cidades pequenas).
- **Operação intensa**: você tem que estar pronto pra despachar várias vezes ao dia.
- **Atrasos afetam reputação** (igual ME normal).

### Quando vale ativar Flex

✅ Vendedor em capital ou cidade grande (SP, RJ, BH, Curitiba, POA, Recife, Salvador, etc.).
✅ Tem volume suficiente pra justificar acordo com transportadora.
✅ Produto leve e fácil de embalar.
✅ Margem permite absorver custo de Flex.

❌ Cidade pequena sem motoboy estruturado.
❌ Volume baixo (menos de 10 pedidos/dia).
❌ Produto muito grande/pesado (Flex prioriza pequeno).
❌ Margem apertadíssima.

### Estratégia de horário de corte

- **Corte às 14h** = padrão. Bom equilíbrio.
- **Corte às 17h** = mais pedidos capturados, mas exige expedição rápida.
- **Corte às 11h** = expedição tranquila, menos pedidos do dia.

⚠️ **Ajuste a área**: começar com raio menor (20–30km) e expandir conforme operação amadurece. Cobertura ampla com transportadora cara mata margem.

### Mudança importante (novembro 2025)

A partir de **25/nov/2025**, Flex passou a oferecer **frete grátis** em produtos de R$ 19 a R$ 78,99. Isso transformou o Flex no produto logístico mais atrativo pro comprador em grandes centros: **frete grátis + entrega rápida ao mesmo tempo**.

Estratégia: produtos nessa faixa de preço, em cidade com Flex ativo, **considerar Flex como prioridade** sobre Full (que tem prazo maior) e Mercado Envios padrão.

## Mercado Envios Full

O modelo de **fulfillment** do ML: você envia estoque pros centros de distribuição (CDs) do ML, e a partir daí, o ML faz **tudo** — armazena, separa, embala, despacha, atende dúvidas, processa devoluções.

### Requisitos

- **CNPJ ativo** (obrigatório).
- **Inscrição Estadual** ou isenção declarada.
- **Reputação verde** ou MercadoLíder (em geral; contas novas com volume podem ser convidadas).
- **Localização do depósito**: estados onde o ML tem operação de coleta (SP, RJ, MG, PR, SC, RS, BA, etc.).
- **Emissão de NF-e** funcionando (vendedor emite NF de remessa pro CD).
- **Limite de faturamento**: para microempresas, pode haver limites — verifique no momento do cadastro.

### Como funciona

1. Vendedor se cadastra no Full no painel.
2. Lista produtos elegíveis (novos, padronizados, com GTIN).
3. Cria "remessa" no painel: emite NF de remessa, embala produtos com etiquetas específicas.
4. Envia (ou ML coleta) pro CD do ML (Cajamar, Louveira, Extrema, Guarulhos, Governador Celso Ramos, etc.).
5. ML recebe, confere, armazena no estoque virtual.
6. Anúncios automaticamente migram pra "Full" e ganham boost de algoritmo.
7. Pedido cai → ML separa, embala, despacha. Vendedor recebe valor após pagamento.

### Custos

- **Armazenagem**: cobrado por unidade × dia, varia por volume do produto.
- **Coleta** (ou envio do vendedor): custo variável.
- **Envio ao cliente**: subsidiado pelo ML, com cashback de 40% pra MercadoLíder/Loja Oficial em produtos a partir de R$ 79 quando ≥ 50% das vendas são via Full.
- **Estoque parado** (>60-90 dias): **penalidade pesada**. Itens que não giram acumulam taxa.

### Vantagens

- **Boost de algoritmo enorme**: anúncios Full ranqueiam acima dos não-Full.
- **Selo "Full"** no anúncio — gera confiança e velocidade percebida.
- **Entrega no dia seguinte** ou em 1-2 dias na maior parte do Brasil (a partir de SP).
- **Atrasos não afetam sua reputação** (responsabilidade do ML).
- **Atendimento pós-venda do ML**: dúvidas e reclamações relacionadas a entrega são tratadas por eles.
- **Cashback de frete**: até 40% mensal pra MercadoLíder.
- **Mais crédito**: Mercado Crédito oferece 20% a mais com 10% menos juros pra Full.
- **Desconto em Mercado Ads** pra produtos Full (alguns benefícios).
- **Atendimento exclusivo** ao vendedor.

### Desvantagens

- **Custo de armazenagem** pode comer margem se produto não gira.
- **Penalidade por estoque parado** pesada — produtos com baixa rotação destroem rentabilidade.
- **Investimento inicial** alto: precisa antecipar capital pra estoque (que pode ficar parado dias até começar a girar).
- **Perda de controle**: ML embala como ele quiser. Brindes personalizados, embalagem com marca = não rola (ou muito limitado).
- **Regras rígidas de envio**: produtos têm que chegar perfeitos no CD, etiquetas específicas, embalagem padronizada. Falha = devolvem ao seu custo.
- **Devoluções**: ML processa, mas você arca se for por defeito ou descrição errada.
- **Exclusividade**: produto no Full só pode ser vendido via ML — não usar pra outros canais (sua loja virtual, Shopee, etc.).
- **Categoria limitada**: nem todos os produtos são elegíveis (perigosos, frágeis grandes, etc.).

### Quando vale entrar no Full

✅ Produto com **giro alto** (vende várias unidades por dia).
✅ Vendedor com **CNPJ + reputação verde**.
✅ Produto **leve, padronizado, durável**.
✅ Vendedor sem capacidade logística própria pra crescer.
✅ Vendedor com capital pra antecipar estoque.

❌ Produto com **baixo giro** (perigo de estoque parado).
❌ Vendedor sem capital de giro pra antecipar estoque.
❌ Produtos personalizados ou que precisam de embalagem especial com sua marca.
❌ Vendedor que vende em múltiplos canais simultâneos.
❌ Produto com **margem muito apertada** (taxas de Full reduzem ainda mais).

### Como começar no Full sem queimar

1. **Comece com 1-2 SKUs campeões**, não com mix inteiro.
2. **Envie quantidade conservadora** — estoque pra 30 dias, não 90.
3. **Monitore giro** semanalmente. Se algo trava, devolve antes de virar penalidade.
4. **Calcule margem incluindo armazenagem** — produtos com margem apertada quebram no Full.
5. **Mantenha catálogo paralelo no Mercado Envios padrão** pra mix completo.

## Frete Grátis

A oferta de frete grátis é **um dos fatores que mais aumenta conversão** no Mercado Livre. Compradores filtram por frete grátis ativamente.

### Mecânica

- **Produtos a partir de R$ 79**: ML subsidia parte do frete conforme reputação (até 50% pra verde/MercadoLíder).
- **Produtos R$ 19–78,99 com Flex** (desde nov/2025): frete grátis automático.
- **Produtos abaixo de R$ 19**: frete pago pelo cliente normalmente.

### Estratégias inteligentes

1. **Precifique com frete grátis embutido**: se sua margem cobre o subsídio, ative frete grátis.
2. **Preço logo acima de R$ 79** se o produto está em torno de R$ 70–78: subir um pouco e ativar frete grátis pode aumentar conversão drasticamente.
3. **Kits acima de R$ 79**: agrupe produtos baratos em kit pra atingir a faixa de subsídio.
4. **Frete grátis condicional**: ML também permite frete grátis acima de X unidades — boa pra incentivar volume.
5. **Frete grátis regional**: configure frete grátis só pra estados próximos (sai mais barato pra você).

### Erro comum: oferecer frete grátis sem calcular

Vendedor liga "frete grátis" achando que vai vender mais, mas não faz a conta. Resultado: cada venda dá menos lucro. Volume não compensa.

**Sempre calcule**: subsídio × reputação atual = custo real do frete grátis pra você.

## Algoritmo Logística

O algoritmo do ML prioriza nesta ordem aproximada:

1. **Full** (boost máximo).
2. **Flex** (boost grande, especialmente em grandes centros).
3. **Mercado Envios com frete grátis** (boost médio).
4. **Mercado Envios sem frete grátis** (neutro).
5. **Não logístico** (`not_specified`) (penalidade — fica no fim das buscas).

**Implicação**: se o seu concorrente está em Full e você no Mercado Envios padrão, mesmo com preço melhor, **você fica abaixo dele na busca**. Logística é diferencial competitivo gigante.

## Embalagem e Expedição

### Embalagem ideal

- **Caixa de papelão** firme — preferível a envelope plástico para a maioria dos produtos.
- **Plástico bolha** ou **enchimento** pra produtos frágeis.
- **Fita adesiva resistente** — não economize aqui.
- **Tamanho próximo ao produto** — caixa muito maior gera cubagem alta (frete caro).
- **Etiqueta visível e bem colada** — cobre com fita transparente pra não rasgar.

### Esteira de expedição

Se você tem volume (>20 pedidos/dia), monte uma esteira:

1. **Imprimir etiquetas** em lote (manhã).
2. **Separar produtos** em lote (puxar do estoque, agrupar por destino se necessário).
3. **Conferir** (item × etiqueta — evitar despachar produto errado).
4. **Embalar** (proteção + caixa + fita).
5. **Etiquetar** (etiqueta visível, sem dobras).
6. **Despachar** (pilha pra transportadora coletar ou levar à agência).

### Embalagem como diferencial

Se você não está no Full, sua embalagem é uma das poucas oportunidades de **construir marca** com o cliente. Vale:

- Caixa com sua logo (impressa ou adesivada).
- Cartão de "obrigado pela compra" (impresso, não digital — automação digital é proibida).
- Brinde pequeno (sticker, amostra) — gera surpresa positiva e avaliações boas.

## Combinar Modalidades

Vendedores maduros usam **mix de modalidades**:

- **Full** para top SKUs (best-sellers, produtos padronizados).
- **Flex** para produtos médios em região com cobertura.
- **Mercado Envios padrão** para SKUs de cauda longa, produtos grandes ou regiões sem Flex.

Não é "ou um ou outro". Para cada SKU, **decida a logística que maximiza margem × visibilidade**.

### Exemplo prático

Loja de acessórios de celular em SP capital, MercadoLíder Gold:

- **Capa de celular** (best-seller, R$ 35): **Flex** com frete grátis. Velocidade + frete grátis = conversão alta. Operação local.
- **Carregador rápido** (best-seller, R$ 120): **Full**. Volume justifica armazenagem, prazo nacional, frete grátis com subsídio máximo.
- **Cabo USB-C** (cauda longa, R$ 45): **Mercado Envios padrão**. Volume baixo, não vale Full nem Flex. Mantém vivo.
- **Hub USB** (R$ 350, item premium): **Full** para mercado nacional. Produto Premium com parcelamento.

## Próximos passos

- `07-mercado-ads.md` — como amplificar visibilidade dos top SKUs com Ads
- `08-promocoes-campanhas.md` — promoções pra acelerar giro de estoque parado no Full
- `05-reputacao-manutencao.md` — manutenção pra manter reputação que destrava todos os benefícios
