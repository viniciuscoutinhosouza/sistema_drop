# Bling — Passo a passo para registrar o aplicativo (OAuth)

> Guia para o **dono** criar o aplicativo no Bling e obter as credenciais (`client_id` / `client_secret`)
> que o Sistema Drop usa para conectar cada CMIG. Feito a partir do portal oficial do Bling
> (Central de Extensões → Área do Integrador). Os rótulos abaixo são os da tela do Bling.

## O que você vai obter no final
- **Client ID**
- **Client Secret**
- (e ter cadastrado o **Link de redirecionamento** e os **escopos** certos)

Esses três me passa para eu colocar no `.env` do servidor. **Nunca** poste o `client_secret` em local
público (chat de grupo, print aberto) — ele é uma senha.

---

## Pré-requisito — liberar "Cadastro de aplicativos" (uma vez)
A conta Bling precisa de um usuário com essa permissão:
1. No Bling, vá em **Preferências → Sistema → Usuários**.
2. **Incluir usuário** (ou editar o seu).
3. Em **Cadastros**, marque **Cadastro de aplicativos**. Salve.

*(Se você já é o administrador da conta Bling, provavelmente já tem acesso — pode pular.)*

---

## Passo 1 — Abrir a criação do aplicativo
1. Entre na **Central de Extensões**.
2. Clique em **Área do Integrador**.
3. Clique em **Criar aplicativo**.

## Passo 2 — Visibilidade
- Escolha a visibilidade e clique em **Próximo**. Para uso interno nosso, escolha a opção **privada**
  (não é um app público para a loja de extensões). *(Se a tela só oferecer "público", tudo bem — o
  fluxo OAuth é o mesmo; só não precisamos preencher as imagens/telas de divulgação.)*

## Passo 3 — Dados do aplicativo
Preencha:
- **Nome:** `Sistema Drop - MIG` (ou o que preferir).
- **Categoria:** a que mais se aproximar (ex.: "Gestão" / "ERP" / "Integração").
- **Descrição / Descrição curta:** algo como *"Integração do Sistema Drop (MIG Ecommerce) com o Bling
  para importar catálogo e sincronizar operações."*
- **Link de redirecionamento** → **cole EXATAMENTE isto** (tem de bater caractere por caractere):

  ```
  https://ecommerce.madeingroup.com.br/api/v1/integrations/bling/callback
  ```

  ⚠️ É o campo mais importante. Se ficar diferente do que o sistema usa, a autorização falha com
  `invalid_grant`. Sem barra extra no fim, sem `http` (tem de ser `https`).
- **Nome do desenvolvedor / Email / Celular:** seus dados de contato.

## Passo 4 — Escopos (permissões)
1. Na seção de escopos, clique em **Adicionar**.
2. Use a **busca** no topo para achar e **marque** os módulos abaixo. (O app só enxerga o que você
   marcar; e **mudar escopo depois obriga todo mundo a reautorizar** — então já marque o conjunto do
   nosso roadmap agora.)

   Marque (procure por estes termos):
   - **Produtos** (ler/consultar) — necessário para importar o catálogo.
   - **Categorias de produtos** (ler) — para importar as categorias.
   - **Estoques / Depósitos** (ler) — para a fase de estoque.
   - **Contatos** (ler) — clientes/fornecedores (fase de pedidos).
   - *(opcional, só se formos emitir NF-e pelo Bling no futuro:)* **Notas fiscais / NF-e**.

   > Se não tiver certeza do nome exato de um escopo, marque o que for de **leitura/consulta** daquele
   > módulo. Dá para ajustar depois (lembrando que ajustar re-autoriza todos).
3. Clique em **Adicionar** para confirmar os escopos selecionados.

## Passo 5 — Salvar
- Clique em **Salvar**. O botão só habilita depois de **pelo menos 1 escopo** incluído.

## Passo 6 — Pegar as credenciais
1. Após criar, abra a aba **Informações do app**.
2. Copie o **Client Id**.
3. Clique no **ícone de olho** para revelar o **Client Secret** e copie.
4. *(Se algum dia precisar trocar o segredo: **Redefinir client secret** — isso invalida o anterior e
   eu preciso atualizar o `.env`.)*

---

## Me envie (em canal seguro)
- `Client ID`
- `Client Secret`
- Confirmação de que o **Link de redirecionamento** cadastrado foi exatamente o do Passo 3.
- Quais **escopos** você acabou marcando.

Com isso eu ponho no `.env` do servidor (`BLING_CLIENT_ID`, `BLING_CLIENT_SECRET`,
`BLING_REDIRECT_URI`) e a gente testa a conexão de uma CMIG ponta a ponta.

## Observações
- **Um app, várias CMIGs:** você cria **um** aplicativo; cada CMIG autoriza ele na conta Bling dela.
  Não precisa de um app por CMIG.
- **Produção vs. teste:** o Link de redirecionamento aponta para o servidor de produção. O Bling não tem
  sandbox — a autorização é sempre na conta real. (Para testar localmente, me avise que eu uso um app/URL
  de teste separado.)
- **Sem sandbox:** qualquer autorização é na conta real do Bling — mas **conectar** não altera nada nos
  seus dados; só concede leitura/escrita conforme os escopos.
