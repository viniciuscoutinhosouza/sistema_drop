# Autenticação, padrão RPC, erros, paginação e encoding

## Autenticação
- **apikey única por empresa**, no **header** `api`.
- SecurityScheme do OpenAPI: `ApiKeyAuth` → `{ type: apiKey, in: header, name: api }`.
- A apikey é sensível: **sempre HTTPS**; nunca logar/expor. No Sistema Drop fica em
  `cmig.eship_api_key` e nunca é devolvida pela nossa API (só `eship_api_key_set: bool`).
- Para descobrir/gerir apikeys existe `webServiceGetApikey` (módulo Usuário).

## Padrão de chamada (RPC, não REST)
Um único endpoint; a operação vai no query param `funcao`; método **sempre POST**; body JSON
(mesmo para leituras).

```
POST https://<tenant>.eship.com.br/v3/?api&funcao=<NomeDaFuncao>
Headers:
  api: <APIKEY>
  Content-Type: application/json
Body: { ...parâmetros... }
```

- `<tenant>`: subdomínio da empresa (ex.: `armazenaki`). O `servers` do spec mostra
  `http://localhost:8080/v3` — **placeholder de dev**, não usar.
- O nome da função é case-sensitive e segue o padrão `webService<Verbo><Entidade>`
  (`webServiceGetProduto`, `webServicePostOrdem`, `webServicePutProduto`, `webServiceDeleteProduto`).

Exemplo (Python, read-only):
```python
import json, urllib.request
def eship_call(base, apikey, funcao, payload):
    req = urllib.request.Request(
        f"{base}/?api&funcao={funcao}",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"api": apikey, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    data = json.loads(raw.decode("latin-1"))   # ISO-8859-1!
    if data.get("erros"):                       # HTTP 200 pode ser erro de negócio
        e = data["erros"][0].get("erro", {})
        raise RuntimeError(f"{e.get('codigo')}: {e.get('mensagem')}")
    return data
```

## Envelope de resposta
Sucesso típico:
```json
{ "erros": [], "corpo": { "body": { "dadosPaginacao": {...}, "dados": [ ... ] } } }
```
- Listas ficam em **`corpo.body.dados`**; a paginação em **`corpo.body.dadosPaginacao`**.
- Algumas escritas retornam o objeto criado sob uma chave própria (ex.: `webServicePostOrdem`
  responde `{"corpo": ..., "ordem": { "id": ..., "status": {...} }}` — o id da ordem é
  `ordem.id`, aninhado).

## Erros (HTTP 200 + campo `erros`)
```json
{ "erros": [ { "erro": { "mensagem": "Função 'webServiceX' não existe.", "codigo": "MAP0014" } } ],
  "corpo": {} }
```
- **`erros` não vazio ⇒ falha**, mesmo com HTTP 200. Sempre cheque antes de tratar como sucesso.
- Código conhecido: **`MAP0014` = "Função não existe"**. ⚠️ Uma função pode estar no OpenAPI e
  **não estar habilitada no tenant** — ex.: `webServiceGetStatusObjeto` existe no `Sistema.json`
  mas retorna `MAP0014` no tenant `armazenaki`. Antes de depender de uma função, confirme com uma
  chamada real.
- Respostas não-JSON (raras) devem ser tratadas como texto (`{"raw": <texto>}`).

## Paginação (funções `Get*`)
Parâmetros comuns de request: `pagina` (1-based), `quantidadeRegistros`, `ordenacao`,
`incrementar`, `completo`. Resposta em `corpo.body.dadosPaginacao`:
```json
{ "totalRegistros": 7594, "registrosPorPagina": 25, "quantidadePaginas": 304,
  "paginaAtual": 1, "objetosDestaPagina": 24, "totalObjetos": 6890 }
```
- Padrão **25/página** (ajustável por `quantidadeRegistros` em muitas funções).
- Para varrer tudo: leia a página 1, pegue `quantidadePaginas`, itere. Catálogos reais são grandes
  (ex.: 304 páginas de produtos, ~1.800 de ordens) — **paralelize com limite** e **não fixe um teto
  menor que `quantidadePaginas`** (ver gotcha do cap de páginas).

## Encoding
- Respostas em **ISO-8859-1 (latin-1)**. Decodifique como `latin-1`. Se você ver "Lan�ado" /
  "Expedi��o", você decodificou como utf-8 por engano.
- No request, envie JSON normal (UTF-8/ASCII). Datas no formato `YYYY-MM-DD`; valores monetários
  como **string com ponto decimal** (ex.: `"12.90"`).

## Boas práticas de cliente
- Timeout 30–60s; a API pode ser lenta em consultas grandes.
- **Retry com backoff** para `Get*` (idempotentes) — o rate limit do eShip não é documentado.
- Trate `erros`/`MAP0014` de forma explícita (não deixe cair num "sucesso vazio").
- Nunca chame `Post*`/`Put*`/`Delete*` em produção sem confirmação — teste em homologação.
