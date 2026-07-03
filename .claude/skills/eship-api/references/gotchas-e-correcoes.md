# Armadilhas do eShip + backlog de correções do Sistema Drop

Este arquivo tem duas partes: (A) armadilhas gerais da API eShip; (B) o backlog priorizado de
correções da integração em `BACKEND/integrations/eship/`, com evidência real. **Consulte antes de
mexer no módulo.** As correções ainda **não foram aplicadas** (documentadas para execução sob
demanda).

## A. Armadilhas gerais da API

1. **HTTP 200 ≠ sucesso.** Erro de negócio vem em 200 no campo `erros`. Sempre inspecione.
2. **`MAP0014` = "Função não existe".** Uma função pode estar no OpenAPI e **não** estar habilitada
   no tenant (ex.: `webServiceGetStatusObjeto` → MAP0014 em `armazenaki`). Confirme com chamada real.
3. **Encoding ISO-8859-1.** Decodifique respostas como `latin-1`. Nunca compare status por texto
   (acento vira mojibake) — use `id`.
4. **Status são objetos `{id, descricao, cor}`**, não strings. Mapeie pelo `id`.
5. **Sempre POST**, mesmo para leitura; a operação vai no query `funcao`.
6. **Sem webhooks** — só polling. Respeite o rate limit (desconhecido): use backoff.
7. **Multi-tenant:** o mesmo WMS hospeda várias empresas; na ordem, `tipo` = a empresa/cliente
   (não "tipo de ordem"). Filtre pelo seu `numeroOrigem`/CNPJ.
8. **Catálogos são grandes** (6.890 produtos/304 pág; 44.886 ordens/~1.796 pág). Pagine com limite e
   nunca fixe um teto menor que `quantidadePaginas`.
9. **`servers` do spec = `localhost:8080`** (placeholder). Use `https://<tenant>.eship.com.br/v3`.

## B. Backlog de correções (priorizado)

### ALTO

**1. Sincronização de status quebrada** — `status_map.py` + `service.extract_status`
- **Evidência:** o `status` da ordem é objeto `{id, descricao}`; o `GetOrdem` devolve lista em
  `corpo.body.dados[]`. O `extract_status` procura `status` no topo (não navega `corpo.body.dados`)
  e o `status_map` é keyed em rótulos **inventados** (`"separado"`, `"expedido"`…) que não existem.
  `normalize()` ainda chama `.strip()` — quebra se receber o dict.
- **Correção:** `extract_status` deve navegar `corpo.body.dados[0].status.id`; `map_status` deve
  mapear **por id numérico** usando a tabela real (`ordens-emissao.md`):
  `1→handling, 2→handling, 3→handling, 6→ready_to_ship(separated), 7→shipped, 8→shipped,
  10→cancelled`. Confirmar ids 4/5/9/11+ em homolog (entregue/não entregue/devolvido).

**2. Cancelamento chama função inexistente**
- **Evidência:** `service.FUNC_CANCELAR_ORDEM = "webServiceCancelarOrdem"`; no spec a função é
  **`webServiceCancelaOrdem`** (sem "r"). A atual retorna `MAP0014`.
- **Correção:** renomear a constante para `webServiceCancelaOrdem`.

**3. Extração do id da ordem devolve dict serializado**
- **Evidência:** `PostOrdem` responde `{"ordem": {id, ...}}`. `extract_order_id` itera
  `("idOrdem","ordem","id",...)` no topo → `resp.get("ordem")` (dict, truthy) → `str(dict)`. O
  `eship_order_id` guardado vira `"{'transportes': ...}"`.
- **Correção:** ler `resp["ordem"]["id"]` (e fallbacks). Guardar o id numérico do eShip.

**4. `GetOrdem` sem `incluirInfo` (obrigatório)**
- **Evidência:** o schema de `webServiceGetOrdem` exige `incluirInfo*` (boolean). O sync envia só
  `{numeroOrigem}`.
- **Correção:** enviar `{"numeroOrigem": ..., "incluirInfo": true, "pagina": 1}`; `numeroOrigem`
  **é** filtro válido (a correlação por ele funciona).

**5. Filtro de saldo errado**
- **Evidência:** `get_saldo_estoque` envia `{"codigoSKU": sku}`; o `GetSaldoEstoque` não tem esse
  campo — o filtro por produto é `codigoProduto` (ou `codigoItem`/`idProduto`).
- **Correção:** enviar `{"codigoProduto": sku}`.

**6. Cap de páginas trunca o catálogo**
- **Evidência:** `_PRODUTOS_MAX_PAGES = 300` < 304 páginas reais → `truncado=True` sempre e ~100
  produtos somem.
- **Correção:** elevar/parametrizar o teto (ou derivar de `quantidadePaginas` com um limite alto).

### MÉDIO

**7. Anexos com campo inexistente + fluxo desligado**
- **Evidência:** `webServicePostArquivoOrdem` **não tem `idTipoAnexo`**; o tipo vem das flags
  `inserirFiscal`/`atualizarTransporte`/`extensao`. As constantes `ANEXO_XML_NFE=4`/`ETIQUETA=7` e o
  campo `idTipoAnexo` não existem no spec. Além disso `attach_nfe_xml`/`attach_label`/
  `push_order_by_xml` **não têm rota/UI** (código morto).
- **Correção:** ajustar o payload de anexo (flags, sem `idTipoAnexo`); decidir expor endpoints +
  botões (fluxo fiscal→WMS §5/§6) ou remover. Usar `webServiceGetAnexosOrdem` para conferência.

**8. Payload da ordem — o que **está** certo (não mexer)**
- As grafias `valorunitrioproduto`, `nmerolinha` e as chaves `"ORDCanal de Venda"`/`"ORDChave"`/
  `"ORDValor da ordem"` **são os nomes reais do spec**. `codigoProduto`/`quantidadeProduto` também.
  Ou seja, `build_ordem_payload` está aderente — a suspeita inicial de "grafia mangled" foi
  descartada pela leitura do `Ordem.json`.

**9. Rastreio real vem do módulo Transporte**
- Hoje só lemos `GetOrdem`. Avaliar `GetTransporte`/`GetEmbarque` (ou o `codigoRastreamento` da
  ordem) para popular `tracking_code`/`tracking_url` de forma confiável.

**10. Dupla configuração**
- A tela admin `EShipConfigView` grava em `eship_config` (por galpão), **ignorada** pelo service
  (que usa credenciais da CMIG). Deprecar/remover ou unificar para evitar confusão.

### BAIXO

**11. Retry/backoff** no `client.call` para `Get*` idempotentes (rate limit desconhecido).
**12. apikey em texto puro** em `cmigs.eship_api_key` — cifrar em repouso (padrão Fernet do
ADR-0015). Paridade/LGPD com o certificado NF-e.
**13. Forçar https** da `base_url` em produção (a apikey vai no header).

## Como validar uma correção
1. Leia o schema real no `<Modulo>.json` (`swagger.eship.com.br/docs/WMS/`).
2. Teste **read-only** (`Get*`) contra o tenant com a apikey — confirme shape/campos.
3. Para escrita, teste **só em homologação** (com aval do dono) e cheque o campo `erros`.
4. `pytest BACKEND/tests/test_eship*.py -m "not integration"`.
5. Smoke do caminho: push produto → push ordem → `GetOrdem` refletindo `status.id` real →
   cancelar com `webServiceCancelaOrdem`.
