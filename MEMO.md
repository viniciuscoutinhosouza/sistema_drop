(quality-guardian + consistency-auditor + adr-consistency-checker)


Como a API do Mercado Turbo está sendo utilizada
Consegui mapear completamente o funcionamento interno da API. Aqui está o que foi descoberto:

🔧 Estrutura da API do Mercado Turbo
O sistema usa uma arquitetura Jakarta EE (Java) com PrimeFaces para o frontend. As chamadas acontecem em dois níveis:
1. Busca de anúncios na listagem (JSF/PrimeFaces via AJAX):
POST /sistema/anuncio/anuncios
Content-Type: application/x-www-form-urlencoded
X-Requested-With: XMLHttpRequest

jakarta.faces.partial.ajax=true
jakarta.faces.source=form-filtros-por-termo:j_idt537
form-filtros-por-termo:j_idt537_input=3   ← (3 = ID Anúncio MLB)
form-filtros-por-termo:input-filtro=MLB43822463
jakarta.faces.ViewState=[token_de_sessao]
2. Busca de detalhes de um anúncio (REST JSON real):
GET /rest/anuncios/anuncio/{ITEM_ID}
→ Retorna JSON com todos os dados do item via API do Mercado Livre
3. Busca de anúncios do vendedor:
GET /rest/usuario/anuncios/conta?id_conta_filtro={SELLER_ID}&limit={N}
→ Retorna dados do seller + lista de itens
A conta conectada tem seller_id: 2471116577 (nickname: MADE_IN_GROUP).

❌ Resultado para MLB43822463
Ao chamar diretamente o endpoint REST:
GET /rest/anuncios/anuncio/MLB43822463
A resposta foi:
json[{
  "code": 404,
  "body": {
    "id": "MLB43822463",
    "message": "Item with id MLB43822463 not found",
    "error": "not_found",
    "status": 404
  }
}]
O anúncio MLB43822463 não existe na API do Mercado Livre. Esse ID é inválido — os IDs válidos nessa conta têm 13 dígitos (ex: MLB4794270619), enquanto MLB43822463 tem apenas 11. Verifique se o número está correto — pode estar faltando algum dígito.