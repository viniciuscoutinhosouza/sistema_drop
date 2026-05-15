# ADR-0003 — JWT armazenado em localStorage

**Status:** Accepted  
**Data:** 2026-05-15

## Contexto

O sistema é um painel administrativo acessado apenas por usuários autenticados (não há conteúdo público). Precisa de autenticação persistente entre abas e sessões, com suporte a refresh automático de token.

## Decisão

Armazenar access token e refresh token em `localStorage`. O Axios injeta `Authorization: Bearer <token>` em todo request via interceptor. Em 401, o interceptor tenta refresh automático e refaz o request original; se falhar, redireciona para `/login`.

## Alternativas Consideradas

| Alternativa | Motivo para Rejeitar |
|-------------|---------------------|
| httpOnly Cookie | Requer configuração CORS/CSRF mais complexa; complicaria o proxy Vite em dev |
| sessionStorage | Não persiste entre abas; experiência ruim para operadores que trabalham com múltiplas abas abertas |
| Memória (in-memory) | Perde autenticação ao recarregar a página |

## Consequências

- **Positivo**: Simples de implementar; persiste entre abas e sessões; compatível com proxy Vite.
- **Negativo**: Vulnerável a XSS se o sistema tiver vetores de injeção — mitigado pelo fato de ser painel admin sem conteúdo de terceiros.
- **Regra derivada**: Nunca renderizar HTML não sanitizado no frontend para evitar XSS.
- **Regra derivada**: `ACCESS_TOKEN_EXPIRE_MINUTES=30` e `REFRESH_TOKEN_EXPIRE_DAYS=7` configurados via env.
