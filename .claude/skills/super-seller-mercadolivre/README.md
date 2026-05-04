# Skill: super-seller-mercadolivre

Skill estratégica/comercial para te ajudar a desenvolver e crescer uma conta de vendedor no Mercado Livre — do zero ao MercadoLíder.

## O que essa skill faz

Quando você consulta o Claude sobre Mercado Livre **como vendedor** (não como desenvolvedor de integração), ele assume o papel de **consultor sênior** e te orienta em:

- **Abrir e configurar conta nova** (CPF vs CNPJ, MEI, primeiros 90 dias).
- **Escolher produtos** com base em demanda, concorrência, margem e logística.
- **Calcular taxas, fretes e precificar com lucro real** (não só faturamento).
- **Criar anúncios que vendem** (título, fotos, ficha técnica, SEO interno).
- **Manter reputação verde** com rotinas diárias, semanais e mensais.
- **Escalar logística** (Mercado Envios, Flex, Full) — quando usar cada um.
- **Investir em Mercado Ads** com ACOS controlado e estratégias por objetivo.
- **Aproveitar promoções** (oferta relâmpago, oferta do dia, campanhas subsidiadas, datas comerciais).

A skill **não fala de API ou código** — para isso, use a skill irmã `mercado-livre-api`. Esta aqui é pro **dono do negócio**.

## Estrutura

```
super-seller-mercadolivre/
├── SKILL.md                          ← visão estratégica e índice
└── references/
    ├── 01-abrindo-conta.md           ← do zero, primeiros 90 dias
    ├── 02-escolhendo-produtos.md     ← análise de mercado, mix
    ├── 03-taxas-fretes-precificacao.md ← cálculo de margem real
    ├── 04-anuncios-que-vendem.md     ← SEO, fotos, ficha técnica
    ├── 05-reputacao-manutencao.md    ← termômetro, MercadoLíder, rotina diária
    ├── 06-logistica-mercado-envios.md ← Flex, Full, frete grátis
    ├── 07-mercado-ads.md             ← Product Ads, ACOS, estratégias
    └── 08-promocoes-campanhas.md     ← ofertas, datas comerciais, calendário
```

## Como instalar

### Opção A — Skill global (todas suas conversas com Claude usam)

```bash
mkdir -p ~/.claude/skills
cp -r super-seller-mercadolivre ~/.claude/skills/
```

### Opção B — Skill em projeto específico (sincroniza via Git)

```bash
cd /caminho/do/seu/projeto
mkdir -p .claude/skills
cp -r super-seller-mercadolivre .claude/skills/
git add .claude/skills/super-seller-mercadolivre
git commit -m "chore: adiciona skill de Super Seller Mercado Livre"
git push
```

### Opção C — Claude.ai (mobile/web/desktop)

Em **Settings → Capabilities → Skills** (a interface pode ter mudado de nome — procure "Skills" no menu de configurações), faça upload do zip da skill.

## Como verificar que está funcionando

Abra um chat e pergunte algo como:

> "Estou começando a vender no Mercado Livre. Tenho R$ 5 mil pra investir e queria entender por onde começar. Como faço?"

Se a skill estiver ativa, o Claude vai:

1. Reconhecer que é tema de venda no ML
2. Provavelmente fazer 2-3 perguntas de diagnóstico (categoria de interesse, etapa atual, etc.)
3. Consultar `01-abrindo-conta.md` e `02-escolhendo-produtos.md`
4. Dar resposta estruturada com os princípios da skill (lucro líquido > faturamento, profissionalize cedo, dados antes de achismo)

Se ele responder de forma **genérica** (sem pedir diagnóstico, sem mencionar CPF vs CNPJ com detalhe, sem indicar dependência de reputação), a skill não está sendo carregada.

## Combinação com a skill `mercado-livre-api`

As duas skills são **complementares**:

| Pergunta do tipo... | Use a skill... |
|---|---|
| "Como precificar meu produto?" | `super-seller-mercadolivre` |
| "Como implementar o OAuth do ML em Python?" | `mercado-livre-api` |
| "Vale a pena investir em Ads agora?" | `super-seller-mercadolivre` |
| "Como receber webhook de venda?" | `mercado-livre-api` |
| "Estou desenvolvendo um sistema pra gerir minha conta ML — quais funcionalidades preciso?" | **Ambas** (estratégia + técnica) |

Se você está construindo um **sistema** pra gerir vendas no ML (como o SISTEMA_DROP), tê-las as duas no projeto cria um Claude que pensa **como dono de negócio E como dev** ao mesmo tempo — ele entende as decisões de design pelas necessidades reais do vendedor.

## Aviso importante

O Mercado Livre **muda regras com frequência**. Em 2026 várias mudanças significativas aconteceram (custo operacional variável para produtos < R$ 79, frete grátis no Flex, Mercado Shops virou Minha Página). A skill foi compilada com base na realidade de 2026, mas:

- **Sempre confirme valores exatos** no painel "Meus custos" do Seller Center antes de decisões financeiras grandes.
- **Tarifas, comissões e regras** podem ser reajustadas a qualquer momento.
- **Atualize a skill** quando notar que algo ficou desatualizado — basta editar o arquivo e commitar.

## Limitações honestas

A skill **não substitui**:

- **Contador especializado em e-commerce** (impostos, regime tributário, ICMS, NF-e).
- **Advogado** (registro de marca, contratos com fornecedores, disputas de PI).
- **Consultor financeiro** (decisão de empréstimos, capital de giro grande).
- **Experiência prática** — vender no ML exige tentativa, erro e ajuste constante.

A skill é seu **mentor 24/7 pra tirar dúvidas e estruturar decisões**. As decisões finais são suas.

## Atualizando a skill

Para customizar pra sua realidade específica:

1. Abra qualquer arquivo `.md` em `references/`.
2. Adicione seções sobre seu nicho (ex: se você vende eletrônicos, adicione informações específicas dessa categoria).
3. Adicione seus aprendizados práticos ("o que funcionou pra mim").
4. Commite no Git e a skill evolui com sua jornada.
