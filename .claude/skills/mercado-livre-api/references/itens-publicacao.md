# Itens — Publicação, atualização e busca

Tudo sobre criar, modificar, pausar, encerrar e buscar publicações na conta do vendedor.

## Sumário

1. [Publicar item simples](#publicar-item-simples)
2. [Categorias e atributos obrigatórios](#categorias-e-atributos-obrigatórios)
3. [Identificadores de produto (GTIN/MPN)](#identificadores-de-produto-gtinmpn)
4. [Variações](#variações)
5. [Catálogo](#catálogo)
6. [Atualizar (preço, estoque, título, status)](#atualizar-preço-estoque-título-status)
7. [API de Preços (multi-canal)](#api-de-preços-multi-canal)
8. [Buscar itens do vendedor](#buscar-itens-do-vendedor)
9. [Limites de publicações](#limites-de-publicações)
10. [User Products (novo modelo)](#user-products-novo-modelo)

## Publicar item simples

Endpoint: `POST https://api.mercadolibre.com/items`

Exemplo mínimo (Brasil, marketplace):

```bash
curl -X POST \
  -H 'Authorization: Bearer ACCESS_TOKEN' \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Item de Teste - Não Comprar",
    "category_id": "MLB437616",
    "price": 10,
    "currency_id": "BRL",
    "available_quantity": 1,
    "buying_mode": "buy_it_now",
    "listing_type_id": "gold_special",
    "condition": "new",
    "description": { "plain_text": "Descrição do produto..." },
    "pictures": [
      { "source": "https://meusistema.com.br/img/produto.jpg" }
    ],
    "attributes": [
      { "id": "BRAND", "value_name": "Marca X" },
      { "id": "MODEL", "value_name": "Modelo Y" }
    ]
  }' \
  https://api.mercadolibre.com/items
```

**Campos críticos:**

| Campo | Notas |
|---|---|
| `title` | Máx 60 chars (BR). Não pode conter promessas como "frete grátis", emojis, símbolos especiais. |
| `category_id` | Obrigatório, ID pré-definido. Use o **preditor de categorias** (ver abaixo). |
| `currency_id` | `BRL`, `ARS`, `MXN`, etc. Bate com o site_id. |
| `listing_type_id` | `gold_special` (Clássico), `gold_pro` (Premium). Pode ser alterado UMA vez depois. |
| `condition` | `new`, `used`, `not_specified`. |
| `pictures` | URLs públicas. Imagens em servidores lentos podem causar falha. Imagens precisam ser ≥ 500x500px. |
| `attributes` | Array de pares `{id, value_name}` ou `{id, value_id}`. Atributos obrigatórios variam por categoria. |

### Preditor de categorias

Não chute `category_id` — use o preditor:

```bash
curl -X POST \
  -H 'Content-Type: application/json' \
  -d '{"title": "Tênis Nike Air Max 90 Masculino"}' \
  https://api.mercadolibre.com/sites/MLB/category_predictor/predict
```

Resposta indica a categoria mais provável + alternativas.

### Listar atributos obrigatórios da categoria

```bash
curl -H 'Authorization: Bearer ACCESS_TOKEN' \
  https://api.mercadolibre.com/categories/MLB437616/attributes
```

Atributos vêm com **tags** importantes:

- `required` → sempre obrigatório.
- `new_required` → obrigatório se `condition: new`.
- `conditional_required` → obrigatório sob condições específicas (ex: GTIN para celulares).
- `read_only` → não pode ser enviado, apenas lido.
- `allow_variations` → atributo que pode definir variações (cor, tamanho).

**Sempre ler atributos da categoria antes de publicar.** Validações falham silenciosamente se você enviar atributos errados ou faltar obrigatórios.

## Identificadores de produto (GTIN/MPN)

Para muitas categorias, **GTIN é obrigatório** (especialmente celulares no MLB, e qualquer marca com mais de 30 GTINs publicados).

```json
{
  "attributes": [
    { "id": "GTIN", "value_name": "7898945080293" }
  ]
}
```

GTIN aceita 8, 10, 12, 13 ou 14 dígitos. Mesmo código com zeros à esquerda é considerado equivalente. **GTIN inválido bloqueia o POST** com erro `7810 / item.attribute.missing_conditional_required`.

Outros identificadores: `MPN` (Manufacturer Part Number), `BRAND`, `MODEL`.

## Variações

Para itens com variações (cor, tamanho, voltagem etc.):

```json
{
  "title": "Camiseta Básica",
  "category_id": "MLB31603",
  "price": 49.90,
  "currency_id": "BRL",
  "buying_mode": "buy_it_now",
  "listing_type_id": "gold_special",
  "condition": "new",
  "pictures": [...],
  "variations": [
    {
      "attribute_combinations": [
        { "id": "COLOR", "value_name": "Preto" },
        { "id": "SIZE", "value_name": "M" }
      ],
      "available_quantity": 5,
      "price": 49.90,
      "picture_ids": [...]
    },
    {
      "attribute_combinations": [
        { "id": "COLOR", "value_name": "Preto" },
        { "id": "SIZE", "value_name": "G" }
      ],
      "available_quantity": 3,
      "price": 49.90,
      "picture_ids": [...]
    }
  ]
}
```

⚠️ **Importante**: o item pai (sem variações) **não tem `available_quantity` próprio** — a soma vem das variações. Não enviar `available_quantity` no nível raiz quando há `variations`.

## Catálogo

ML migrou muitas categorias para **publicação no catálogo** — em vez de criar sua própria página de produto, você publica associado a um `catalog_product_id` existente.

```bash
curl -X POST \
  -H 'Authorization: Bearer ACCESS_TOKEN' \
  -H "Content-Type: application/json" \
  -d '{
    "catalog_product_id": "MLB15996654",
    "category_id": "MLB1055",
    "price": 999,
    "currency_id": "BRL",
    "available_quantity": 10,
    "listing_type_id": "gold_pro",
    "condition": "new",
    "sale_terms": [...],
    "shipping": {...}
  }' \
  https://api.mercadolibre.com/items
```

**Vantagem:** ficha técnica, imagens e título já vêm prontos. **Risco:** se o produto associado for diferente do que você vende, gera reclamações e pode levar a inabilitação para publicar no catálogo (e até suspensão).

Buscar produtos do catálogo:

```bash
curl -H 'Authorization: Bearer ACCESS_TOKEN' \
  'https://api.mercadolibre.com/products/search?status=active&site_id=MLB&q=iPhone+15+128GB'
```

Buscar por Part Number:

```bash
curl -H 'Authorization: Bearer ACCESS_TOKEN' \
  'https://api.mercadolibre.com/products/search?status=active&site_id=MLB&q=PART_NUMBER'
```

## Atualizar (preço, estoque, título, status)

### PUT genérico em /items/{ID}

```bash
curl -X PUT \
  -H 'Authorization: Bearer ACCESS_TOKEN' \
  -H "Content-Type: application/json" \
  -d '{ "title": "Novo título", "price": 1500 }' \
  https://api.mercadolibre.com/items/MLB1374737433
```

**Campos atualizáveis em item ativo:**
- `title`, `price`, `available_quantity`, `pictures`, `description`, `attributes`
- `listing_type_id` (apenas UMA vez)
- `status` (ver abaixo)

**Não atualizáveis após publicar:**
- `category_id` (precisa pausar e recriar).
- `condition`.
- `currency_id`.

### Mudar status

```bash
# Pausar (some das buscas, mas não encerra)
curl -X PUT -H 'Authorization: Bearer ACCESS_TOKEN' \
  -H "Content-Type: application/json" \
  -d '{"status":"paused"}' \
  https://api.mercadolibre.com/items/MLB123

# Reativar
curl -X PUT -H 'Authorization: Bearer ACCESS_TOKEN' \
  -H "Content-Type: application/json" \
  -d '{"status":"active"}' \
  https://api.mercadolibre.com/items/MLB123

# Encerrar definitivamente (irreversível!)
curl -X PUT -H 'Authorization: Bearer ACCESS_TOKEN' \
  -H "Content-Type: application/json" \
  -d '{"status":"closed"}' \
  https://api.mercadolibre.com/items/MLB123
```

⚠️ Status são case-sensitive em **minúsculo**. `"Active"` vai falhar.

### Substatuses importantes

- `out_of_stock` — pausado por falta de estoque. Adicionar estoque reativa **automaticamente**.
- `payment_required` — vendedor com pendência financeira. Item será reativado após pagamento.
- `under_review` (warning/waiting_for_patch) — sob revisão do ML. Corrigir em 2 dias.
- `freeze` — congelado por violação grave. Resolver no painel.

### Estoque zero (Fulfillment)

Para Fulfillment, é possível publicar com `available_quantity: 0` — o item fica pausado em `out_of_stock` até chegada de estoque, evitando vendas sem entrega.

## API de Preços (multi-canal)

ML separou o preço em **canais** (marketplace, mshops, mercadopago). Use a API de preços para diferenciar:

```bash
curl -X POST \
  -H 'Authorization: Bearer ACCESS_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{
    "prices": [
      {
        "conditions": { "context_restrictions": ["channel_marketplace"] },
        "amount": 400,
        "currency_id": "BRL"
      },
      {
        "conditions": { "context_restrictions": ["channel_mshops"] },
        "amount": 450,
        "currency_id": "BRL"
      }
    ]
  }' \
  https://api.mercadolibre.com/items/MLB123/prices/standard
```

Consultar preço efetivo (com promoções aplicadas):

```bash
curl -H 'Authorization: Bearer ACCESS_TOKEN' \
  'https://api.mercadolibre.com/items/MLB123/sale_price?context=channel_marketplace,buyer_loyalty_3'
```

**Atenção:** se o item tem **automação de preços ativa** e você fizer PUT em `price`, a automação é desabilitada. Sempre verificar antes.

## Buscar itens do vendedor

### Todos os itens do vendedor

```bash
curl -H 'Authorization: Bearer ACCESS_TOKEN' \
  'https://api.mercadolibre.com/users/SELLER_ID/items/search?status=active'
```

Por padrão retorna até 50 itens. Use `limit=100` (máx) e paginação.

### Por SKU customizado

```bash
# Pelo campo seller_custom_field
curl -H 'Authorization: Bearer ACCESS_TOKEN' \
  'https://api.mercadolibre.com/users/SELLER_ID/items/search?sku=MEU_SKU'

# Pelo atributo SELLER_SKU
curl -H 'Authorization: Bearer ACCESS_TOKEN' \
  'https://api.mercadolibre.com/users/SELLER_ID/items/search?seller_sku=MEU_SKU'
```

### Itens com problemas (saúde)

```bash
# Itens perdendo exposição (reclamações/cancelamentos)
curl -H 'Authorization: Bearer ACCESS_TOKEN' \
  'https://api.mercadolibre.com/users/SELLER_ID/items/search?health=unhealthy'

# Apenas em risco (ainda recuperável)
curl -H 'Authorization: Bearer ACCESS_TOKEN' \
  'https://api.mercadolibre.com/users/SELLER_ID/items/search?health=warning'
```

### Sem identificador de produto

```bash
curl -H 'Authorization: Bearer ACCESS_TOKEN' \
  'https://api.mercadolibre.com/users/SELLER_ID/items/search?missing_product_identifiers=true'
```

### Paginação acima de 1000 (scan)

Para vendedores com muitos itens, busca normal limita em 1000. Use scroll:

```bash
# Primeira chamada
curl -H 'Authorization: Bearer ACCESS_TOKEN' \
  'https://api.mercadolibre.com/users/SELLER_ID/items/search?search_type=scan'

# Próximas páginas (use scroll_id da resposta anterior)
curl -H 'Authorization: Bearer ACCESS_TOKEN' \
  'https://api.mercadolibre.com/users/SELLER_ID/items/search?search_type=scan&scroll_id=XXX'
```

`scroll_id` fica `null` quando acabou.

### Detalhes de um item

```bash
curl -H 'Authorization: Bearer ACCESS_TOKEN' \
  https://api.mercadolibre.com/items/MLB1374737433
```

Para múltiplos itens (até 20 por chamada):

```bash
curl -H 'Authorization: Bearer ACCESS_TOKEN' \
  'https://api.mercadolibre.com/items?ids=MLB1,MLB2,MLB3'
```

Resposta vem em formato verbose (cada item com `code` indicando sucesso ou erro).

## Limites de publicações

Cada vendedor tem um cap de itens ativos baseado em reputação:

```bash
curl -H 'Authorization: Bearer ACCESS_TOKEN' \
  https://api.mercadolibre.com/marketplace/users/cap
```

Antes de publicar massivamente, valide o cap restante para não falhar no meio da operação.

## User Products (novo modelo)

ML está migrando para um modelo onde "produto físico" (User Product) é separado de "condição de venda" (Item). Um UP pode ter múltiplos Items (ex: mesmo iPhone em 3 ofertas com preços diferentes).

**Como detectar se o vendedor está no novo modelo:**

```bash
curl -H 'Authorization: Bearer ACCESS_TOKEN' \
  https://api.mercadolibre.com/users/SELLER_ID
```

Procurar tag `user_product_seller` no array `tags`. Se presente, o vendedor opera no novo modelo.

**Identificar item migrado:** se `family_name` do item for diferente de `null`, está no novo modelo.

**Implicação prática:** PUT em `/items` que altera atributos do User Product (cor, modelo, marca) propaga **assincronamente** para todos os items associados. Não tente atualizar item por item — atualize o UP uma vez.

Documentação completa: `https://developers.mercadolivre.com.br/pt_br/user-products`

## Boas práticas finais

1. **Sempre validar atributos da categoria** antes de publicar (cache local com TTL de 24h).
2. **Sempre usar imagens hospedadas em CDN rápido** (Cloudflare, AWS CloudFront, S3). Imagens lentas reprovam a publicação.
3. **Não use POST `/items` para atualização** — use PUT no item específico.
4. **Para operações em lote**, espace as requisições. Não dispare 1000 POSTs em paralelo.
5. **Logue o `id` retornado** no POST para conseguir rastrear depois.
6. **Tags úteis para monitorar saúde**: `health`, `tags` (procure por `freeze`, `under_review`, `dirty_marketplace`).
