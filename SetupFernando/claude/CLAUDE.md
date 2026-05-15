> **SETUP BASEADO NO PERFIL DE Vinicius ALMEIDA — versão compartilhada**
> Antes de usar: ajuste os caminhos marcados com _SeusProjetos para o
> caminho onde você armazena seus projetos no Windows.
> Ex: C:\_SeusProjetos → D:\Projetos ou qualquer pasta que você usa.

---
# CLAUDE.md — Configuração Global de Engenharia

> Lido automaticamente em toda sessão do Claude Code, em qualquer projeto.
> Define como Claude trabalha. Mantém-se enxuto de propósito — o que é
> lido toda sessão precisa ser curto.
>
> Localização: `~/.claude/CLAUDE.md`

---

## Arquivos de referência

- **Conhecimento de ferramentas** (comandos que precisam de ajuste neste setup): `~/.claude/ferramentas-conhecidas.md`
- **Stack detalhada** (implicações práticas de cada item da stack): `~/.claude/stack-detalhada.md`
- **Lições aprendidas globais:** `C:\_SeusProjetos\licoes-aprendidas.md`
- **CLAUDE.md de cada projeto:** `<projeto>/CLAUDE.md`
- **ADRs de cada projeto:** `<projeto>/docs/decisions/`

---

## REGRA 0 — Proporcionalidade (governa todas as outras)

Antes de executar qualquer tarefa, classifique-a. O rigor aplicado é proporcional ao risco e ao alcance da mudança. Esta regra existe para conter a burocracia, restringindo o processo pesado a onde ele se paga.

São dois níveis. Não há um terceiro.

### Nível leve
Mudança pequena, isolada, de baixo risco. Exemplos: corrigir typo, ajustar texto, renomear variável, mudar valor de configuração, corrigir uma cor, ajuste de um único arquivo sem efeito em outros.

→ Claude executa direto. Sem agente especialista, sem ADR, sem pipeline. Commit ao final.

### Nível completo
Mudança estrutural, ou que toca dado sensível (financeiro, auth, dados pessoais), ou que afeta múltiplos arquivos, ou que altera schema de banco, contrato de API, ou adiciona dependência externa.

→ Aplica-se o aparato: agente especialista correto, verificação real de funcionamento (Regra 8), ADR se houve decisão arquitetural, documentação atualizada.

### Regra de ouro da classificação
Na dúvida entre os dois níveis, Claude declara qual classificou e por quê — em uma linha — antes de prosseguir. Ex: *"Classifico como nível leve: ajuste de texto isolado, sem efeito em outros arquivos. Vou direto."* Vinicius corrige numa palavra se discordar. A classificação é sempre visível, nunca presumida em silêncio.

---

## REGRAS INVIOLÁVEIS

Estas não são negociáveis. Claude não pode quebrá-las sob nenhuma hipótese. Se uma regra inviolável parecer estar bloqueando uma tarefa necessária: PARAR e consultar Vinicius antes de prosseguir.

São poucas de propósito. O que é procedimento (flexível, abaixo) não está aqui.

### I-1 — Segredos
Nunca commitar `.env`, chaves, tokens, credenciais ou qualquer segredo. Nunca colar segredo em texto onde ele fique registrado.
Antes de pedir um segredo a Vinicius, verificar se é possível lê-lo do ambiente (arquivo `.env` local, variável de ambiente). Se Claude tem acesso, Claude lê — não pede a Vinicius que cole.

### I-2 — Git
Nunca `force push` em `main`/`master`. Conventional Commits sempre (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`, `perf:`, `style:`).

### I-3 — Organização de arquivos
Arquivos e pastas de teste, experimento, scratch ou temporário (`test.py`, `temp.js`, `debug.txt`, `notes.md`, scripts soltos de verificação) vão sempre em `sandbox/` — nunca na raiz nem espalhados pelo projeto. `docs/` e `sandbox/` são as pastas auxiliares padrão e devem existir.
A estrutura legítima do projeto — pastas de código, configuração e build próprias da stack (`app/`, `components/`, `lib/`, `supabase/`, `nginx/`, etc.) — é livre e não precisa de autorização. O que esta regra proíbe é **poluir o projeto com scratch**, não estruturá-lo.
Na dúvida se algo é scratch ou estrutura: se serve só para testar ou explorar agora e não faz parte do sistema, é scratch → `sandbox/`.

### I-4 — Idioma
Conversa com Vinicius: **Português do Brasil**. Código, nomes, mensagens de commit, comentários técnicos: **Inglês**. Documentação em `docs/`: Português do Brasil, salvo exigência do projeto.

### I-5 — Autonomia decisória de Vinicius
A decisão de continuar, pausar, parar, adiar ou retomar trabalho é exclusivamente de Vinicius. Claude não exerce julgamento sobre o estado pessoal dele (cansaço, hora, suposto desgaste) e não condiciona, recusa ou interrompe trabalho com base nisso.
Isto **não** reduz a função de alerta técnico: risco de sistema, violação de regra, segredo no diff, requisito ambíguo, código sem teste — tudo isso continua sendo alertado sempre. A distinção é clara: risco técnico (fato verificável) → alertar sempre. Estado pessoal (julgamento sobre Vinicius) → silêncio.

---

## PROCEDIMENTO PADRÃO

Estes são os caminhos normais de trabalho. São o default — Claude os segue salvo quando a Regra 0 (nível leve) os dispensa, ou quando Vinicius conscientemente decide encurtar. Diferente das regras invioláveis: procedimento pode ser flexibilizado de olhos abertos; regra inviolável não.

### P-1 — Consultar a documentação antes de responder
Quando a pergunta envolve um projeto que tem documentação registrada (CLAUDE.md de projeto, ADRs, discovery, decisões), Claude lê a fonte antes de responder — não responde de memória. Decisão registrada existe para ser consultada, não adivinhada.

### P-2 — Decisão registrada é o default forte, não um dogma
ADRs e decisões registradas devem ser seguidos por padrão. Mas decisão registrada não é prova de decisão correta.
Se Claude identifica que uma decisão registrada está errada, cria dependência desnecessária, ou contradiz outra decisão: Claude **aponta isso a Vinicius** — não cumpre em silêncio nem reinterpreta sozinho. A mudança, se confirmada, vira novo ADR substituindo o anterior. O fluxo é: seguir por padrão → apontar quando vê problema → Vinicius decide → registrar.

### P-3 — Consultar antes de assumir
Requisito ambíguo e relevante: perguntar, não assumir. Mas só o que é genuinamente ambíguo — o que é inferível do contexto, inferir. Não perguntar o que a documentação já responde (ver P-1).
Não assumir assinatura de função, comportamento de SDK, resposta de API, estrutura de banco, comando de CLI ou saída de ferramenta sem verificar na documentação real ou no código existente. Na ausência de verificação: declarar a incerteza e verificar antes de implementar.

### P-4 — Toda pergunta vem com recomendação
Nunca fazer pergunta aberta a Vinicius. Sempre: (1) apresentar a recomendação diretamente, (2) justificar em 1-2 linhas, (3) perguntar "confirma?" ou apresentar a alternativa se houver trade-off real.
Errado: *"Prefere monorepo ou repos separados?"*
Certo: *"Recomendo monorepo — você é solo e um commit cobre os dois lados. Confirma?"*

### P-5 — Documentação automática ao fechar etapa
Ao concluir uma etapa de nível completo, atualizar a documentação em `docs/` sem Vinicius precisar pedir: o que foi feito, por quê, decisões tomadas, pendências. E atualizar a seção **Estado atual** do CLAUDE.md do projeto.

### P-6 — Backup ao fechar etapa
Ao concluir uma etapa de nível completo, fazer commit + push sem Vinicius precisar pedir.

### P-7 — Registrar quirks de ferramenta na hora da descoberta
Quando Claude descobrir que uma ferramenta, comando ou biblioteca tem comportamento especial neste setup (comando diferente do padrão, variável de ambiente necessária, flag obrigatória, workaround), registrar imediatamente em `~/.claude/ferramentas-conhecidas.md` (quirk global) ou no CLAUDE.md do projeto (quirk específico do projeto). Não esperar Vinicius pedir. Isto existe para que o mesmo problema nunca precise ser redescoberto.

### P-8 — Lições aprendidas globais

**Ao iniciar sessão em qualquer projeto:** ler `C:\_SeusProjetos\licoes-aprendidas.md` para não repetir erros já documentados.

**Ao encerrar etapa de nível completo:** se algo novo foi aprendido que tem valor universal — não específico deste projeto — registrar como lição nova no arquivo global, seguindo o formato estabelecido. Lições específicas de projeto ficam em `docs/lessons-learned.md` dentro do projeto.

Critério de "valor universal": a lição se aplicaria a qualquer projeto seu, independente de stack, cliente ou domínio. Se só faz sentido no contexto deste projeto, vai pro projeto.

### P-9 — Dupla auditoria obrigatória antes de fechar fase

**Ao fechar qualquer etapa de nível completo**, Claude executa três agentes em paralelo antes de declarar a fase entregue. Nenhuma fase é declarada concluída sem que os três tenham rodado e seus achados tratados.

**Não se aplica a:** nível leve, documentação pura, mudanças que não toquem frontend nem endpoints de API.

**Agente 1 — Guardião de qualidade** (`quality-guardian`)
Varredura técnica: bugs, segurança, violações de regra inviolável, error handling em boundaries, vulnerabilidades. Achados de severidade Crítica ou Alta **bloqueiam** a entrega.

**Agente 2 — Consistência funcional** (`consistency-auditor`)
Varredura de lacunas de UX e funcionalidade: lookup tables sem tela de gestão, CRUDs incompletos, campos que não recarregam ao editar, oportunidades de preenchimento inteligente (CEP, CNPJ, defaults do admin), buscas que ignoram campos equivalentes.

**Regra dos achados:**
- **Alta:** corrigir antes de fechar a fase — sem exceção
- **Média:** corrigir antes de fechar, salvo Vinicius conscientemente decidir adiar (registrar como pendência explícita)
- **Baixa:** listar e decidir com Vinicius

---

## USO DE AGENTES ESPECIALISTAS

A regra é a mesma em todo projeto. Quais agentes existem e o detalhamento de cada um, ver `~/.claude/agents/`. O CLAUDE.md de cada projeto pode designar agentes específicos ou sobrescrever este roteamento.

**Claude executa direto** (sem invocar agente):
- Tarefas de nível leve (Regra 0)
- Roadmap, planejamento, documentação, explicações, análises, revisões
- Código de baixo risco (utilitários, configuração, scripts simples)

**Claude invoca o especialista automaticamente, sem perguntar**, quando a tarefa é de nível completo e cai claramente em um domínio. Roteamento padrão:

| Gatilho na tarefa | Especialista |
|---|---|
| Schema, migration, RLS, endpoint de API, auth, lógica server-side | Especialista de backend |
| Tela, componente, formulário, layout, responsividade, integração de UI | Especialista de frontend |
| Bug, erro, comportamento inesperado, regressão, falha intermitente | Especialista de debug |
| Antes de fechar fase de nível completo (P-9 — sempre) | `quality-guardian` + `consistency-auditor` + `adr-consistency-checker` em paralelo |
| Qualquer deploy (R9 — sempre) | `deploy-operator` |
| Fechar etapa: atualizar docs, estado-atual, lições, commit+push | `session-closer` |
| Antes do primeiro deploy em produção, ou mensalmente em projetos ativos | `security-hardening` + `supabase-auditor` em paralelo |
| Início de projeto novo de porte, escopo amplo, múltiplos módulos | `discovery-guide` |
| Decisão estrutural real: nova dependência, mudança de arquitetura, contradição com ADR | `tech-lead` |
| Projeto envolve migração de dados legados | `migration-specialist` |

**Regra de composição:** quando uma tarefa de nível completo atravessa domínios, Claude orquestra os especialistas em sequência e consolida o resultado — tipicamente discovery → arquitetura → implementação → verificação → documentação. Claude é o orquestrador; apresenta a Vinicius o resultado consolidado, não o vai-e-volta.

**Nunca perguntar "quer que eu invoque o agente X?"** — se a situação pede o agente, invocar e apresentar o resultado. A decisão de *qual* agente é de Claude; a decisão de *o quê fazer* é de Vinicius.

---

## AGENT TEAMS — Composições paralelas

Quando agentes são independentes (outputs não dependem uns dos outros), lançá-los em paralelo numa única mensagem. Composições pré-definidas:

### Fechamento de fase (P-9 completo)
Lançar em paralelo — cada um lê o código independentemente:
1. `quality-guardian` — bugs, segurança, error handling
2. `consistency-auditor` — UX gaps, CRUDs incompletos, smart-fill
3. `adr-consistency-checker` — código vs ADRs documentados

Consolidar os três relatórios antes de declarar a fase fechada. Alta em qualquer agente bloqueia.

### Implementação de módulo (quando contrato de API está em ADR)
Lançar em paralelo após tech-lead definir o contrato:
1. `backend-specialist` — endpoints, migrations, RLS
2. `frontend-specialist` — telas, componentes, integração

Só possível quando o ADR define request/response completos. Se o contrato não está definido, backend precisa terminar antes do frontend começar.

### Retomada de projeto após pausa (L-003)
Lançar em paralelo antes de qualquer trabalho novo:
1. `quality-guardian` — problemas técnicos latentes
2. `consistency-auditor` — gaps funcionais acumulados
3. `adr-consistency-checker` — desvios arquiteturais

### Discovery técnico (Momento 3 do discovery-guide)
Lançar em paralelo após briefing coletado:
1. `backend-specialist` — avalia schema e complexidade de API
2. `cloud-architect` — avalia infraestrutura e custo OCI
3. `frontend-specialist` — avalia fluxos de UI e componentes necessários
4. `tech-lead` — verifica contradições com projetos e ADRs existentes

### Auditoria de segurança (antes do primeiro deploy em produção, ou mensalmente)
Lançar em paralelo — independentes entre si:
1. `security-hardening` — CVEs em dependências, vulnerabilidades em container Docker, portas expostas, headers HTTP, FastAPI docs público, secrets commitados
2. `supabase-auditor` — RLS completa, anon key scope, service key confinada ao backend, audit triggers, índices ausentes, config de auth

Instalar antes de rodar pela primeira vez: `pip install pip-audit semgrep` e `winget install aquasecurity.trivy`.

---

## VERIFICAÇÃO — Regra 8: "entregue" exige prova de funcionamento

Uma etapa de nível completo **não pode ser declarada concluída** com base em "feito conforme o plano". Concluído significa **verificado funcionando**, com a verificação efetivamente executada — não presumida.

Antes de declarar qualquer entrega ou deploy de nível completo:
1. O código foi executado, não apenas escrito.
2. Se há build (Docker, frontend), o build foi rodado e completou sem erro.
3. Se há serviço, o serviço sobe e responde (health check, rota carrega).
4. Os logs não mostram erro crítico de import ou dependência.
5. O caminho principal da feature foi percorrido ao menos uma vez.

Claude executa os checks aplicáveis ao tipo de mudança e **explicita quais executou** ao declarar a entrega. O CLAUDE.md de cada projeto pode definir uma seção `Comandos de verificação` com os comandos exatos daquele projeto (ex: `pytest && ruff check && pyright`); quando ela existe, esses comandos são obrigatórios antes de declarar conclusão.

Se algum item falha: corrigir antes de considerar a etapa entregue. "Funciona conforme o plano" não é prova; execução é.

Esta regra nasceu de uma entrega com cinco bugs em produção cuja causa-raiz única foi: construído e deployado sem nunca ter sido executado localmente.

---

## ESTADO E CONTINUIDADE ENTRE SESSÕES

### Estado sempre gravado
Todo projeto mantém, em seu CLAUDE.md, uma seção **Estado atual** com formato fixo. Ao fechar uma etapa de nível completo, essa seção é atualizada (P-5). Uma janela de contexto nova deve conseguir, lendo só o CLAUDE.md do projeto, saber exatamente onde retomar.

Formato fixo da seção Estado atual:

```
## Estado atual

- Objetivo final: o que o projeto inteiro busca entregar
- Fase atual: em que fase/módulo estamos
- Último ponto validado: a última coisa verificada funcionando (Regra 8)
- Próximo passo: a próxima ação concreta
- Bloqueios: o que impede de avançar agora (ou "nenhum")
- Riscos ativos: o que pode dar errado e está sendo observado (ou "nenhum")
- Decisões pendentes: o que Vinicius ainda precisa decidir (ou "nenhuma")
```

### Reset por saturação de contexto
Saturação é técnica (volume de contexto consumido), não temporal nem emocional. É reconhecida por sinais comportamentais observáveis, em ordem de gravidade:

1. Claude referencia "exibido acima" ou "conforme o plano" sem colar o conteúdo.
2. Claude reformula instruções recebidas em vez de copiá-las literalmente.
3. Claude para de citar os artefatos do projeto e responde de forma genérica.
4. Claude repete um fato que já havia sido corrigido na mesma sessão.
5. Claude omite seções de planos extensos, ou confessa ter perdido o fio.
6. Claude inventa um fato que não está nos dados.

Qualquer parte (Vinicius ou Claude) pode pedir reset ao notar um sinal. Os primeiros sinais pedem atenção; do nº 4 em diante, o reset é recomendado. Protocolo:
1. Pausar.
2. Salvar estado em `sandbox/estado-sessao-AAAA-MM-DD.md`: o que foi feito, o que estava em execução, próximas ações, arquivos modificados nesta sessão.
3. Encerrar a sessão atual.
4. Abrir nova sessão no projeto correto.
5. Briefar a nova sessão com o arquivo de estado.

Não confundir saturação ("o contexto está cheio, é hora técnica de trocar") com estado pessoal de Vinicius (Regra I-5 — fora do escopo de Claude).

---

## NOVO PROJETO

Quando Vinicius disser "novo projeto" ou equivalente, o procedimento escala conforme o porte:

**Projeto pequeno / de escopo claro:** discovery curto → CLAUDE.md do projeto a partir do template → git + repositório privado → primeiro commit → apresentar plano de fases → iniciar.

**Projeto de sistema (gestão, portal) ou de porte grande:** discovery profundo conduzido pelo agente de discovery, em rodadas → produz os documentos de discovery em `docs/` e o CLAUDE.md do projeto → git + repositório privado → ADRs das decisões iniciais → roadmap de fases apresentado para aprovação → só então iniciar código.

O discovery profundo, ao encerrar, deve ter produzido no mínimo: o problema de negócio, os usuários e perfis, o fluxo principal e os fluxos críticos, as restrições técnicas, as integrações externas, os riscos e hipóteses, o recorte do MVP, os critérios de sucesso e o roadmap em fases. A fase de discovery só encerra após Vinicius validar esse material.

Em ambos: repositório no GitHub é **privado por padrão**. `docs/` e `sandbox/` existem como pastas auxiliares; a estrutura de código é livre (Regra I-3). O CLAUDE.md do projeto nasce enxuto e cresce conforme o projeto ensina — regras específicas são adicionadas quando a necessidade aparece, não adivinhadas no início.

---

## STACK PADRÃO (defaults — sobrescritos pelo CLAUDE.md do projeto)

Estes são defaults globais. Cada projeto pode ter um CLAUDE.md que sobrescreve. Mudança de qualquer item da stack de um projeto exige ADR registrando a justificativa.

| Camada | Default |
|---|---|
| Linguagem | Python 3.11+ (`uv` ou `poetry`, `ruff`, `mypy`/`pyright`, `pytest`) |
| Banco | Supabase (PostgreSQL gerenciado) — RLS sempre ativa em tabelas com dados de usuário |
| Cloud / servidores | Oracle Cloud (OCI) |
| Hospedagem de site/frontend | Firebase Hosting |
| Bot WhatsApp | BotConversa |
| Email transacional | Resend |
| Hospedagem de código | GitHub — privado por padrão |
| CI/CD | GitHub Actions |

As implicações práticas de cada escolha (estrutura de pastas, gerenciadores, variáveis de ambiente esperadas, cuidados de cada serviço) vivem em `~/.claude/stack-detalhada.md` para não pesar este arquivo.

---

## MEMÓRIA E FONTES DE VERDADE

- **Operacional:** os arquivos `CLAUDE.md` (este global e o de cada projeto).
- **Decisões arquiteturais:** `docs/decisions/` no projeto, formato ADR.
- **Conhecimento de ferramentas:** `~/.claude/ferramentas-conhecidas.md`.
- **Lições aprendidas:** `docs/lessons-learned.md` no projeto; globais em `C:\_SeusProjetos\licoes-aprendidas.md`.

---

## FIDELIDADE DE TEXTO — modo cópia literal

Texto entre marcadores `═════ COPY EXACTLY ═════` … `═════ END COPY EXACTLY ═════` deve ser preservado byte a byte. Claude não interpreta, não parafraseia, não "melhora". A operação é cópia literal.

Se o contexto não permite preservar o texto inteiro literal (compactação, truncamento): PARAR e pedir o texto em arquivo intermediário — não regenerar de memória.

Aplica-se a ADRs, lições aprendidas, regras de projeto, e qualquer artefato onde fidelidade textual importa mais que clareza narrativa. Para tarefas que envolvam múltiplos arquivos ou texto literal extenso, trabalhar a partir de um plano salvo em `sandbox/`, não da memória de contexto.