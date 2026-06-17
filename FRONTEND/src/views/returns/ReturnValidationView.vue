<template>
  <div>
    <div v-if="loading" class="text-center py-5">
      <i class="fas fa-spinner fa-spin fa-2x text-muted"></i>
    </div>

    <div v-else-if="!ret" class="alert alert-danger">
      <i class="fas fa-exclamation-triangle mr-2"></i>
      Devolução não encontrada ou não está aguardando validação.
    </div>

    <div v-else>
      <!-- Info do pedido -->
      <div class="card mb-3">
        <div class="card-header">
          <h3 class="card-title">
            <i class="fas fa-search mr-2 text-warning"></i>
            Validar Devolução #{{ ret.id }}
          </h3>
        </div>
        <div class="card-body">
          <div class="row">
            <div class="col-md-6">
              <dl class="row mb-0">
                <dt class="col-sm-4">Pedido</dt>
                <dd class="col-sm-8">{{ ret.order_id || '—' }}</dd>
                <dt class="col-sm-4">Motivo</dt>
                <dd class="col-sm-8">{{ ret.reason || '—' }}</dd>
                <dt class="col-sm-4">Rastreio</dt>
                <dd class="col-sm-8">
                  <a v-if="ret.tracking_url" :href="ret.tracking_url" target="_blank">
                    {{ ret.tracking_code || '—' }}
                    <i class="fas fa-external-link-alt ml-1" style="font-size:10px"></i>
                  </a>
                  <span v-else>{{ ret.tracking_code || '—' }}</span>
                </dd>
              </dl>
            </div>
            <div class="col-md-6">
              <dl class="row mb-0">
                <dt class="col-sm-4">Transportadora</dt>
                <dd class="col-sm-8">{{ ret.carrier || '—' }}</dd>
                <dt class="col-sm-4">Descrição</dt>
                <dd class="col-sm-8">{{ ret.description || '—' }}</dd>
                <dt class="col-sm-4">Data</dt>
                <dd class="col-sm-8"><small>{{ formatDateTime(ret.created_at) }}</small></dd>
              </dl>
            </div>
          </div>
        </div>
      </div>

      <!-- NF-e de devolução -->
      <div v-if="ret.devolution_invoice_id" class="card mb-3">
        <div class="card-header">
          <h3 class="card-title">
            <i class="fas fa-file-invoice mr-2 text-info"></i>
            NF-e de Devolução #{{ devInvoice?.nfe_number || ret.devolution_invoice_id }}
          </h3>
        </div>
        <div class="card-body">
          <p v-if="ret.referenced_access_key" class="small mb-2">
            <strong>NF-e de venda referenciada:</strong>
            <code>{{ ret.referenced_access_key }}</code>
          </p>
          <p class="small text-muted mb-2">
            A quantidade abaixo (da NF-e) será a que volta ao estoque (apto) ou vai para descarte (inapto).
          </p>
          <table class="table table-sm mb-0" v-if="devInvoice?.items?.length">
            <thead class="thead-light">
              <tr><th>Item</th><th>SKU/EAN</th><th>Casado</th><th class="text-right">Qtd</th></tr>
            </thead>
            <tbody>
              <tr v-for="it in devInvoice.items" :key="it.id">
                <td>{{ it.description }}</td>
                <td><small>{{ it.sku || it.ean || '—' }}</small></td>
                <td>
                  <span v-if="it.catalog_product_id || it.cmig_product_id" class="badge badge-success">Sim</span>
                  <span v-else class="badge badge-warning">Não</span>
                </td>
                <td class="text-right">{{ Number(it.quantity) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Formulário de validação -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">
            <i class="fas fa-clipboard-check mr-2 text-info"></i>
            Inspeção do Produto
          </h3>
        </div>
        <div class="card-body">

          <!-- Upload de fotos -->
          <div class="form-group">
            <label class="font-weight-bold">
              <i class="fas fa-camera mr-1 text-secondary"></i>
              Fotos do produto recebido
            </label>
            <div class="d-flex flex-wrap" style="gap:8px">
              <div
                v-for="(url, i) in photos"
                :key="i"
                class="position-relative"
                style="width:120px;height:120px"
              >
                <img
                  :src="url"
                  style="width:120px;height:120px;object-fit:cover;border-radius:4px;border:1px solid #dee2e6"
                  @click="openPhoto(url)"
                  class="cursor-pointer"
                />
                <button
                  type="button"
                  class="btn btn-danger btn-xs position-absolute"
                  style="top:2px;right:2px;padding:1px 6px;font-size:11px"
                  @click="removePhoto(i)"
                >
                  ×
                </button>
              </div>

              <!-- Botão de upload -->
              <label
                class="d-flex flex-column align-items-center justify-content-center bg-light border"
                style="width:120px;height:120px;border-radius:4px;cursor:pointer;border-style:dashed!important"
              >
                <i v-if="uploading" class="fas fa-spinner fa-spin fa-2x text-muted"></i>
                <template v-else>
                  <i class="fas fa-plus fa-2x text-muted mb-1"></i>
                  <small class="text-muted">Adicionar foto</small>
                </template>
                <input
                  type="file"
                  accept="image/*"
                  multiple
                  style="display:none"
                  :disabled="uploading"
                  @change="uploadPhotos"
                />
              </label>
            </div>
            <small class="text-muted">Tire fotos do estado do produto para registrar a inspeção.</small>
          </div>

          <!-- Notas de validação -->
          <div class="form-group">
            <label class="font-weight-bold">
              <i class="fas fa-sticky-note mr-1 text-secondary"></i>
              Notas da inspeção
            </label>
            <textarea
              v-model="notes"
              class="form-control"
              rows="4"
              placeholder="Descreva o estado do produto recebido: embalagem, avarias, funcionamento, etc."
            ></textarea>
          </div>
        </div>

        <div class="card-footer d-flex justify-content-between align-items-center">
          <RouterLink to="/returns/aguardando-validacao" class="btn btn-secondary">
            <i class="fas fa-arrow-left mr-1"></i> Voltar
          </RouterLink>
          <div>
            <button
              class="btn btn-danger mr-2"
              @click="validate(false)"
              :disabled="saving"
            >
              <i class="fas fa-times-circle mr-1"></i>
              {{ saving && !approving ? 'Reprovando...' : 'Reprovar — Produto Inapto' }}
            </button>
            <button
              class="btn btn-success"
              @click="validate(true)"
              :disabled="saving"
            >
              <i class="fas fa-check-circle mr-1"></i>
              {{ saving && approving ? 'Aprovando...' : 'Aprovar — Produto OK' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Modal de foto ampliada -->
    <div v-if="photoModal" class="photo-modal" @click="photoModal = null">
      <img :src="photoModal" style="max-width:90vw;max-height:90vh;border-radius:8px" />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { formatDateTime } from '@/utils/formatters'

const route = useRoute()
const router = useRouter()
const toast = useToast()

const ret = ref(null)
const devInvoice = ref(null)
const loading = ref(true)
const notes = ref('')
const photos = ref([])
const uploading = ref(false)
const saving = ref(false)
const approving = ref(false)
const photoModal = ref(null)

async function load() {
  loading.value = true
  try {
    const { data } = await api.get(`/returns/${route.params.id}`)
    if (data.status !== 'awaiting_validation') {
      ret.value = null
    } else {
      ret.value = data
      if (data.devolution_invoice_id) {
        try {
          const { data: inv } = await api.get(`/invoices/${data.devolution_invoice_id}`)
          devInvoice.value = inv
        } catch {
          devInvoice.value = null
        }
      }
    }
  } catch {
    ret.value = null
  } finally {
    loading.value = false
  }
}

async function uploadPhotos(event) {
  const files = Array.from(event.target.files)
  if (!files.length) return
  uploading.value = true
  try {
    for (const file of files) {
      const form = new FormData()
      form.append('file', file)
      const { data } = await api.post(`/returns/${route.params.id}/upload-photo`, form)
      photos.value.push(data.url)
    }
  } catch {
    toast.error('Erro ao enviar foto.')
  } finally {
    uploading.value = false
    event.target.value = ''
  }
}

function removePhoto(index) {
  photos.value.splice(index, 1)
}

function openPhoto(url) {
  photoModal.value = url
}

async function validate(approved) {
  saving.value = true
  approving.value = approved
  try {
    await api.post(`/returns/${route.params.id}/validate`, {
      approved,
      notes: notes.value,
      photos: photos.value,
    })
    if (approved) {
      toast.success('Devolução aprovada! Produto voltou ao estoque disponível.')
    } else {
      toast.warning('Devolução reprovada. Produto registrado como inapto.')
    }
    router.push('/returns/aguardando-validacao')
  } catch (err) {
    toast.error(err.response?.data?.detail || 'Erro ao validar devolução.')
  } finally {
    saving.value = false
    approving.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.cursor-pointer { cursor: pointer; }
.photo-modal {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.85);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  cursor: pointer;
}
</style>
