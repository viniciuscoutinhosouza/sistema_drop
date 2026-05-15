# Lições Aprendidas — Global

> Aprendizados universais — valem para qualquer projeto, qualquer contexto.
> Lições específicas de projeto ficam em `docs/lessons-learned.md` dentro do projeto.
> Localização: `C:\_Projetos_Sistemas\licoes-aprendidas.md`

---

## 🛠️ Sobre ferramentas e setup

### L-001 — Notepad do Windows não é confiável pra arquivos `.md`
**Contexto:** criação de arquivos de configuração do setup Claude Code.
**O que aconteceu:** Notepad inseriu backslashes escapando markdown e usou codificação ANSI/Latin-1 em vez de UTF-8. Resultado: arquivos com `\#`, `\---`, e acentos corrompidos como `ConfiguraÃ§Ã£o`.
**Lição:** sempre usar VS Code pra criar ou editar arquivos `.md`.
**Como evitar:** nunca usar Notepad pra qualquer arquivo lido por ferramentas modernas.

### L-002 — Conversões de codificação são perigosas
**Contexto:** tentativa de consertar acentos errados via PowerShell.
**O que aconteceu:** lemos o arquivo (que estava em UTF-8) tratando como Latin-1 e re-salvamos como UTF-8. Resultado: erros dobraram. `responsável` virou `responsÃƒÂ¡vel`.
**Lição:** se você não sabe a codificação atual, NÃO converta. Investigue primeiro.
**Como evitar:** sempre criar arquivos novos em ferramenta confiável em vez de tentar corrigir arquivos com codificação suspeita.

### L-003 — Varredura de qualidade ao retomar projeto após pausa
**Contexto:** retomada do projeto Hard Solution após período parado, primeira sessão com o novo setup do Claude Code.
**O que aconteceu:** ao abrir o projeto e pedir varredura geral, o quality-guardian encontrou 12 problemas reais — 2 críticos de segurança, 4 funcionalidades quebradas em produção. Nenhum havia sido detectado antes. O setup novo não criou os problemas: revelou os que já existiam.
**Lição:** projeto "entregue" não significa projeto sem problemas latentes. Varredura com quality-guardian ao retomar projeto após pausa revela o que estava escondido antes de o cliente encontrar.
**Como aproveitar:** ao retomar qualquer projeto após período parado, primeira ação é sempre rodar varredura completa — antes de qualquer trabalho novo.

---

## ✏️ Como adicionar lição nova

```markdown
### L-NNN — Título curto
**Contexto:** quando aconteceu, em qual projeto.
**O que aconteceu:** descrição factual.
**Lição:** o que aprendemos.
**Como evitar/aproveitar:** ação concreta.
```

Numeração sequencial a partir de L-003. Não reutilizar números. Lição obsoleta marca como obsoleta, não apaga.

---

## Histórico de versões

- **2026-05-14** — Arquivo criado do zero. Mantidas apenas L-001 e L-002 do histórico anterior por terem valor universal. Todo o resto era específico de projeto e foi descartado do global.
