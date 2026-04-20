<template>
  <div class="card card-outline card-primary">
    <div class="card-header d-flex align-items-center">
      <h5 class="card-title mb-0"><i class="fas fa-bullhorn mr-2"></i> Anúncios no Marketplace</h5>
      <button class="btn btn-sm btn-primary ml-auto" @click="openAddModal">
        <i class="fas fa-plus mr-1"></i> Adicionar anúncio
      </button>
    </div>

    <div class="card-body p-0">
      <div v-if="loading" class="text-center py-4">
        <i class="fas fa-spinner fa-spin"></i> Carregando...
      </div>

      <div v-else-if="listings.length === 0" class="text-center text-muted py-4">
        <i class="fas fa-bullhorn fa-2x mb-2 d-block"></i>
        Nenhum anúncio cadastrado. Adicione uma conta e vincule ou crie um anúncio.
      </div>

      <table v-else class="table table-sm table-hover mb-0">
        <thead>
          <tr>
            <th>Conta</th>
            <th>ID Anúncio</th>
            <th>Preço</th>
            <th>Título alternativo</th>
            <th>Status</th>
            <th class="text-center">Ações</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="l in listings" :key="l.id">
            <td>
              <span :class="platformBadge(l.platform)" class="badge mr-1">{{ platformLabel(l.platform) }}</span>
              {{ l.account_name }}
            </td>
            <td>
              <a v-if="l.platform_item_id && l.platform === 'mercadolivre'"
                 :href="`https://produto.mercadolivre.com.br/${l.platform_item_id}`"
                 target="_blank" rel="noopener">
                {{ l.platform_item_id }}
              </a>
              <span v-else-if="l.platform_item_id">{{ l.platform_item_id }}</span>
              <span v-else class="text-muted">—</span>
            </td>
            <td>R$ {{ Number(l.sale_price).toFixed(2) }}</td>
            <td>
              <span v-if="l.title_override" class="text-truncate d-inline-block" style="max-width:180px" :title="l.title_override">
                {{ l.title_override }}
              </span>
              <span v-else class="text-muted">—</span>
            </td>
            <td>
              <span :class="statusBadge(l.status)" class="badge">{{ statusLabel(l.status) }}</span>
              <small v-if="l.error_message" class="text-danger d-block" :title="l.error_message">
                <i class="fas fa-exclamation-circle"></i> Erro
              </small>
            </td>
            <td class="text-center text-nowrap">
              <button class="btn btn-xs btn-outline-secondary mr-1" title="Editar" @click="openEditModal(l)">
                <i class="fas fa-edit"></i>
              </button>
              <button v-if="l.status === 'draft' || l.status === 'error'"
                      class="btn btn-xs btn-outline-success mr-1" title="Publicar" @click="openPublishModal(l)">
                <i class="fas fa-upload"></i>
              </button>
              <button v-if="l.status === 'published'"
                      class="btn btn-xs btn-outline-warning mr-1" title="Pausar" @click="pauseListing(l)">
                <i class="fas fa-pause"></i>
              </button>
              <button class="btn btn-xs btn-outline-danger" title="Remover" @click="removeListing(l)">
                <i class="fas fa-trash"></i>
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- Modal: Adicionar / Editar anúncio -->
  <div v-if="showModal" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
    <div class="modal-dialog">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title">{{ editingListing ? 'Editar anúncio' : 'Adicionar anúncio' }}</h5>
          <button class="close" @click="closeModal"><span>&times;</span></button>
        </div>
        <div class="modal-body">
          <div v-if="!editingListing" class="form-group">
            <label>Conta <span class="text-danger">*</span></label>
            <select v-model="form.account_id" class="form-control">
              <option value="">Selecione uma conta...</option>
              <option v-for="acc in integrations" :key="acc.id" :value="acc.id">
                {{ platformLabel(acc.platform) }} – {{ acc.platform_username || acc.description }}
              </option>
            </select>
          </div>
          <div class="form-group">
            <label>Preço de venda (R$) <span class="text-danger">*</span></label>
            <input v-model.number="form.sale_price" type="number" step="0.01" min="0" class="form-control" />
          </div>
          <div class="form-group">
            <label>Título alternativo <small class="text-muted">(deixe vazio para usar o título do produto)</small></label>
            <input v-model="form.title_override" type="text" class="form-control" maxlength="500" />
          </div>
          <div class="form-group">
            <label>ID de categoria</label>
            <input v-model="form.category_id" type="text" class="form-control" placeholder="Ex: MLB1000 ou ID Shopee" />
          </div>
          <div class="form-group">
            <label>Tipo de anúncio (ML)</label>
            <select v-model="form.listing_type" class="form-control">
              <option value="">Selecione...</option>
              <option value="gold_special">Ouro Especial</option>
              <option value="gold_pro">Ouro Pro</option>
              <option value="gold">Ouro</option>
              <option value="silver">Prata</option>
              <option value="bronze">Bronze</option>
              <option value="free">Grátis</option>
            </select>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="closeModal">Cancelar</button>
          <button class="btn btn-primary" :disabled="saving" @click="saveListing">
            {{ saving ? 'Salvando...' : (editingListing ? 'Salvar' : 'Adicionar') }}
          </button>
        </div>
      </div>
    </div>
  </div>

  <!-- Modal: Publicar anúncio -->
  <div v-if="showPublishModal" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
    <div class="modal-dialog">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title">Publicar anúncio</h5>
          <button class="close" @click="showPublishModal = false"><span>&times;</span></button>
        </div>
        <div class="modal-body">
          <p class="text-muted">Conta: <strong>{{ publishTarget?.account_name }}</strong></p>

          <div class="form-group">
            <label>Modo de publicação</label>
            <div class="custom-control custom-radio mb-2">
              <input id="mode-link" type="radio" v-model="publishForm.mode" value="link" class="custom-control-input" />
              <label for="mode-link" class="custom-control-label">Vincular anúncio existente</label>
            </div>
            <div class="custom-control custom-radio">
              <input id="mode-create" type="radio" v-model="publishForm.mode" value="create" class="custom-control-input" />
              <label for="mode-create" class="custom-control-label">Criar novo anúncio via API</label>
            </div>
          </div>

          <div v-if="publishForm.mode === 'link'" class="form-group">
            <label>ID do anúncio existente <span class="text-danger">*</span></label>
            <input v-model="publishForm.platform_item_id" type="text" class="form-control"
                   :placeholder="publishTarget?.platform === 'mercadolivre' ? 'MLB123456789' : 'ID do item Shopee'" />
          </div>

          <div v-if="publishForm.mode === 'create'" class="alert alert-info">
            <i class="fas fa-info-circle mr-1"></i>
            O anúncio será criado com o título e preço configurados. Certifique-se de ter preenchido
            <strong>categoria</strong> e <strong>tipo de anúncio</strong> antes de continuar.
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="showPublishModal = false">Cancelar</button>
          <button class="btn btn-success" :disabled="publishing" @click="doPublish">
            <i class="fas fa-upload mr-1"></i>
            {{ publishing ? 'Publicando...' : 'Publicar' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '@/composables/useApi'

const props = defineProps({ productId: { type: Number, required: true } })

const listings = ref([])
const integrations = ref([])
const loading = ref(false)
const saving = ref(false)
const publishing = ref(false)
const showModal = ref(false)
const showPublishModal = ref(false)
const editingListing = ref(null)
const publishTarget = ref(null)

const defaultForm = () => ({
  account_id: '',
  sale_price: '',
  title_override: '',
  category_id: '',
  listing_type: '',
})
const form = ref(defaultForm())
const publishForm = ref({ mode: 'link', platform_item_id: '' })

async function load() {
  loading.value = true
  try {
    const [listRes, intRes] = await Promise.all([
      api.get(`/products/${props.productId}/listings`),
      api.get('/accounts'),
    ])
    listings.value = listRes.data
    integrations.value = intRes.data.filter(i => i.is_active)
  } finally {
    loading.value = false
  }
}

function openAddModal() {
  editingListing.value = null
  form.value = defaultForm()
  showModal.value = true
}

function openEditModal(listing) {
  editingListing.value = listing
  form.value = {
    account_id: listing.account_id,
    sale_price: listing.sale_price,
    title_override: listing.title_override || '',
    category_id: listing.category_id || '',
    listing_type: listing.listing_type || '',
  }
  showModal.value = true
}

function closeModal() {
  showModal.value = false
  editingListing.value = null
}

function openPublishModal(listing) {
  publishTarget.value = listing
  publishForm.value = { mode: 'link', platform_item_id: listing.platform_item_id || '' }
  showPublishModal.value = true
}

async function saveListing() {
  if (!editingListing.value && !form.value.account_id) return
  if (!form.value.sale_price) return
  saving.value = true
  try {
    if (editingListing.value) {
      await api.put(`/products/${props.productId}/listings/${editingListing.value.id}`, form.value)
    } else {
      await api.post(`/products/${props.productId}/listings`, form.value)
    }
    closeModal()
    await load()
  } finally {
    saving.value = false
  }
}

async function removeListing(listing) {
  if (!confirm('Remover este anúncio?')) return
  await api.delete(`/products/${props.productId}/listings/${listing.id}`)
  await load()
}

async function doPublish() {
  if (publishForm.value.mode === 'link' && !publishForm.value.platform_item_id) return
  publishing.value = true
  try {
    await api.post(`/products/${props.productId}/listings/${publishTarget.value.id}/publish`, publishForm.value)
    showPublishModal.value = false
    await load()
  } finally {
    publishing.value = false
  }
}

async function pauseListing(listing) {
  if (!confirm('Pausar este anúncio no marketplace?')) return
  await api.post(`/products/${props.productId}/listings/${listing.id}/pause`)
  await load()
}

function platformLabel(platform) {
  return { mercadolivre: 'ML', shopee: 'Shopee', bling: 'Bling' }[platform] || platform
}
function platformBadge(platform) {
  return { mercadolivre: 'badge-warning', shopee: 'badge-danger', bling: 'badge-info' }[platform] || 'badge-secondary'
}
function statusLabel(status) {
  return { draft: 'Rascunho', published: 'Publicado', paused: 'Pausado', error: 'Erro' }[status] || status
}
function statusBadge(status) {
  return {
    draft: 'badge-secondary',
    published: 'badge-success',
    paused: 'badge-warning',
    error: 'badge-danger',
  }[status] || 'badge-secondary'
}

onMounted(load)
</script>
