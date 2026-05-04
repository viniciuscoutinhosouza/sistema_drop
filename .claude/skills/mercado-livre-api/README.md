# Skill: mercado-livre-api

Skill personalizada para auxiliar no desenvolvimento de integrações com as APIs do Mercado Livre, Mercado Envios e Mercado Pago.

## O que essa skill faz

Quando você está trabalhando num sistema que se integra ao Mercado Livre, o Claude consulta esta skill automaticamente para:

- Implementar autenticação OAuth (com refresh, race conditions, gotchas)
- Publicar e gerenciar anúncios (items, variações, catálogo, GTIN, preços)
- Processar vendas, packs, envios (ME1/ME2/Flex/Full)
- Receber e processar webhooks corretamente (fila, idempotência, missed feeds)
- Integrar Mercado Pago (pagamentos, refunds, PIX, OAuth)
- Tratar erros, rate limits, e evitar antipadrões que geram banimento

A skill traz endpoints, exemplos de código (Node/TypeScript), boas práticas oficiais, e os "gotchas" que só aparecem em produção.

## Estrutura

```
mercado-livre-api/
├── SKILL.md                          ← índice e visão geral
└── references/
    ├── autenticacao.md               ← OAuth, refresh, usuários de teste
    ├── itens-publicacao.md           ← criar, atualizar, buscar items
    ├── pedidos-envios.md             ← orders, packs, shipments, fraude
    ├── webhooks-notificacoes.md      ← tópicos, fila, idempotência
    ├── mercado-pago.md               ← pagamentos, refunds, PIX
    └── erros-rate-limits.md          ← retry, antipadrões, checklist
```

## Como instalar

### Opção A — Skill global (todos os seus projetos veem)

```bash
mkdir -p ~/.claude/skills
cp -r mercado-livre-api ~/.claude/skills/
```

Faça isso nas duas máquinas (casa e escritório).

### Opção B — Skill no projeto (sincroniza via Git)

Recomendado pro seu cenário de duas máquinas:

```bash
# Dentro da raiz do projeto que vai integrar com ML
mkdir -p .claude/skills
cp -r mercado-livre-api .claude/skills/

git add .claude/skills/mercado-livre-api
git commit -m "chore: adiciona skill de integração ML"
git push
```

Na outra máquina, basta `git pull` — a skill já estará disponível.

### Opção C — Claude.ai (desktop ou web)

A skill funciona também no Claude.ai. No menu de configurações, vá em "Skills" → "Upload skill" e mande a pasta zipada. (A interface pode mudar — se não achar, procure na documentação atualizada.)

## Como verificar se está funcionando

Abra o Claude Code (ou Claude.ai) e pergunte algo do tipo:

> "Preciso implementar o fluxo de OAuth do Mercado Livre. Como faço o refresh token de forma segura?"

O Claude deve consultar a skill (você verá referência a `autenticacao.md`) e responder com o template completo, lock distribuído e tudo. Se ele responder por conhecimento geral sem consultar a skill, a descrição pode precisar de ajuste — abra `SKILL.md` e fortaleça a parte do `description`.

## Aviso importante

A documentação oficial do Mercado Livre **muda com frequência** — endpoints novos, atributos obrigatórios diferentes por categoria, mudanças no modelo (User Products, multi-canal de preços, etc.). Esta skill foi compilada em 2026 e cobre os fluxos principais, mas:

- Para casos específicos (categorias raras, integrações complexas com Full, Global Selling), **sempre verifique a documentação oficial** antes de implementar.
- Se notar que algo na skill ficou desatualizado, edite o arquivo correspondente em `references/` e commite.

Links oficiais úteis:

- https://developers.mercadolivre.com.br/pt_br/api-docs-pt-br
- https://developers.mercadolivre.com.br/devcenter
- https://www.mercadopago.com.br/developers/pt
- https://global-selling.mercadolibre.com/devsite/introduction-globalselling
- https://developers.mercadoenvios.com/

## Atualizando a skill

A skill é só markdown — abra qualquer arquivo, ajuste, salve. Em ambiente versionado (Opção B), commite as mudanças. Toda nova sessão do Claude vai ler a versão atualizada.
