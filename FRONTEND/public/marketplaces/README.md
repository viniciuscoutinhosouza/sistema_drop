# Logos de Marketplaces

Pasta servida estaticamente pelo Vite. Arquivos aqui ficam acessíveis em `/marketplaces/*`.

## Arquivos esperados (salvar manualmente)

| Arquivo | Uso | Origem |
|---|---|---|
| `mercadolivre.png` | Logo completo Mercado Livre (texto + ícone) — uso futuro: cards grandes, dashboards | Imagem com "mercado livre" escrito |
| `mercadolivre-icon.png` | Apenas o ícone do handshake — usado em badges de tabelas (compacto) | Imagem só do círculo amarelo com aperto de mão |
| `shopee.png` | (futuro) Logo completo Shopee | — |
| `shopee-icon.png` | (futuro) Apenas o ícone Shopee | — |

## Referenciar no código

No template Vue:
```html
<img src="/marketplaces/mercadolivre-icon.png" alt="Mercado Livre" />
```

O `/` inicial é resolvido pra raiz de `public/`. Em dev (Vite) e em prod (build) funciona igual.

## Fallback

Se o arquivo não existir, o `<img>` quebra silenciosamente. O componente que renderiza o badge tem `@error` handler que esconde a imagem e mostra o texto "ML" como fallback.
