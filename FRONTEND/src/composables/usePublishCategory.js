import api from '@/composables/useApi'

/**
 * Persiste a categoria escolhida no modal de publicação dentro de
 * product_marketplace_categories. Usado pelas telas de catálogo e
 * pelo wizard de anúncios após publish bem-sucedido.
 *
 * sel: { category_id, category_name, category_path_json?, attributes,
 *        pmc_id?, isNew }
 *
 * Best-effort: erros são engolidos (não derrubam a publicação que já
 * aconteceu). 409 (duplicata) é tratado como sucesso silencioso.
 */
export async function persistCategoryToProduct(sel, ownerType, ownerId, marketplace) {
  if (!sel || !sel.category_id || !ownerType || !ownerId || !marketplace) return

  const attributesJson = JSON.stringify(sel.attributes || [])

  try {
    if (sel.pmc_id) {
      // Categoria já existe no produto → atualiza atributos (e path se disponível).
      const body = { attributes_json: attributesJson }
      if (sel.category_path_json) body.category_path_json = sel.category_path_json
      await api.put(`/product-categories/${sel.pmc_id}`, body)
    } else {
      // Categoria nova ou edição em que a categoria do listing ainda
      // não havia sido cadastrada no produto → cria.
      const body = {
        marketplace,
        category_id: sel.category_id,
        category_name: sel.category_name || null,
        category_path_json: sel.category_path_json || null,
        attributes_json: attributesJson,
      }
      body[`${ownerType}_product_id`] = ownerId
      await api.post('/product-categories', body)
    }
  } catch (e) {
    if (e?.response?.status === 409) return
    console.warn('[usePublishCategory] não foi possível salvar categoria:', e?.response?.data || e?.message)
  }
}
