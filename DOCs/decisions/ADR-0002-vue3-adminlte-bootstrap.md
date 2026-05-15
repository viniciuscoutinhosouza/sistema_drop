# ADR-0002 — Vue 3 + AdminLTE 3 + Bootstrap 5 sem TypeScript

**Status:** Accepted  
**Data:** 2026-05-15

## Contexto

O sistema é um painel administrativo (back-office) para dropshippers e operadores de galpão. Precisa de componentes ricos (tabelas, cards, sidebars, modais), responsividade e velocidade de desenvolvimento. A equipe tem experiência em Vue e não tem necessidade imediata de tipagem estática.

## Decisão

Usar Vue 3 Composition API com `<script setup>`, AdminLTE 3 (baseado em Bootstrap 5) como design system, Font Awesome 5 para ícones, e JavaScript puro sem TypeScript.

## Alternativas Consideradas

| Alternativa | Motivo para Rejeitar |
|-------------|---------------------|
| React + Material UI | Curva de aprendizado adicional; preferência de equipe por Vue |
| Nuxt 3 | Overhead de SSR desnecessário para painel admin autenticado |
| TypeScript | Introduziria fricção sem benefício imediato dado o contexto do projeto |
| Vuetify / PrimeVue | AdminLTE já inclui o design system necessário; evitar dependências extras |

## Consequências

- **Positivo**: Desenvolvimento rápido; componentes AdminLTE prontos para uso; sem configuração de TS/ESLint.
- **Negativo**: Sem type safety em tempo de compilação; bugs de tipo detectados apenas em runtime.
- **Regra derivada**: Manter JS puro — não introduzir TypeScript sem acordo explícito.
- **Regra derivada**: Composable `useApi` obrigatório (não usar `axios` diretamente); `useToast()` para feedback.
