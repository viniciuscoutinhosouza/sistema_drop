<template>
  <div class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
    <div class="modal-dialog modal-lg">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title"><i class="fas fa-file-import mr-2"></i>Importar XML de Devolução</h5>
          <button type="button" class="close" @click="$emit('close')"><span>&times;</span></button>
        </div>

        <div class="modal-body">
          <p class="text-muted small">
            Faça upload do XML da NF-e de devolução (modelo 55). O sistema casa o pedido
            original pela NF-e referenciada e registra a devolução aguardando inspeção
            (apto/não apto). A quantidade considerada é a da NF-e (devolução parcial é suportada).
          </p>

          <!-- CMIG -->
          <div class="form-group">
            <label class="small mb-1">CMIG <span class="text-danger">*</span></label>
            <select v-model="cmigId" class="form-control" :disabled="uploading">
              <option :value="null">Selecione...</option>
              <option v-for="c in cmigs" :key="c.id" :value="c.id">
                {{ c.company_name }} ({{ c.cnpj }})
              </option>
            </select>
          </div>

          <!-- Drop zone -->
          <div
            class="border border-dashed rounded p-4 text-center"
            :class="{'bg-light': !file, 'bg-success-light': file}"
            style="border-style: dashed !important; cursor: pointer;"
            @click="fileInput?.click()"
            @dragover.prevent
            @drop.prevent="onDrop">
            <input ref="fileInput" type="file" accept=".xml,application/xml,text/xml" class="d-none"
                   @change="onFileChange">
            <div v-if="!file">
              <i class="fas fa-cloud-upload-alt fa-3x text-muted mb-2"></i>
              <p class="mb-0">Clique para selecionar ou arraste o arquivo XML aqui</p>
            </div>
            <div v-else>
              <i class="fas fa-file-code fa-2x text-success mb-2"></i>
              <p class="mb-1"><strong>{{ file.name }}</strong></p>
              <small class="text-muted">{{ formatSize(file.size) }}</small>
              <button class="btn btn-sm btn-link" @click.stop="resetFile">Trocar arquivo</button>
            </div>
          </div>

          <!-- Resultado -->
          <div v-if="result" class="alert alert-success mt-3">
            <h6><i class="fas fa-check-circle mr-1"></i>Devolução importada!</h6>
            <p class="mb-1 small">
              <strong>Devolução #{{ result.return_id }}</strong> — NF-e #{{ result.invoice_id }}
              <span :class="`badge badge-${result.status === 'unlinked' ? 'secondary' : 'warning'} ml-1`">
                {{ result.status === 'unlinked' ? 'Sem produto casado' : 'Ag. Validação' }}
              </span>
            </p>
            <p class="mb-0 small">
              Pedido original: <strong>{{ result.order_id || '—' }}</strong> —
              <span class="badge badge-success">{{ result.items_matched }} de {{ result.items_total }} itens casados</span>
              <span class="badge badge-info ml-1">{{ result.received_qty }} un. recebidas</span>
            </p>
          </div>

          <div v-if="error" class="alert alert-danger mt-3">
            <i class="fas fa-exclamation-triangle mr-1"></i>{{ error }}
          </div>
        </div>

        <div class="modal-footer">
          <button class="btn btn-secondary" @click="$emit('close')">{{ result ? 'Fechar' : 'Cancelar' }}</button>
          <button v-if="!result" class="btn btn-primary" :disabled="!canSubmit" @click="submit">
            <i class="fas" :class="uploading ? 'fa-spinner fa-spin' : 'fa-upload'"></i>
            {{ uploading ? 'Importando...' : 'Importar' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useCmigStore } from '@/stores/cmig'
import api from '@/composables/useApi'

const emit = defineEmits(['close', 'imported'])

const cmigStore = useCmigStore()
const { cmigs } = storeToRefs(cmigStore)

const fileInput = ref(null)
const cmigId = ref(null)
const file = ref(null)
const uploading = ref(false)
const result = ref(null)
const error = ref('')

const canSubmit = computed(() => !!cmigId.value && !!file.value && !uploading.value)

function onFileChange(e) {
  const f = e.target.files?.[0]
  if (f) file.value = f
}

function onDrop(e) {
  const f = e.dataTransfer?.files?.[0]
  if (f && f.name.toLowerCase().endsWith('.xml')) file.value = f
}

function resetFile() {
  file.value = null
  if (fileInput.value) fileInput.value.value = ''
}

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

async function submit() {
  if (!canSubmit.value) return
  uploading.value = true
  error.value = ''
  result.value = null

  const formData = new FormData()
  formData.append('cmig_id', cmigId.value)
  formData.append('xml_file', file.value)

  try {
    const { data } = await api.post('/returns/import-xml', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    result.value = data
    emit('imported', data)
  } catch (e) {
    error.value = e.response?.data?.detail || 'Erro ao importar XML de devolução'
  } finally {
    uploading.value = false
  }
}

onMounted(async () => {
  if (cmigs.value.length === 0) await cmigStore.fetchCmigs()
  if (!cmigId.value && cmigs.value.length > 0) {
    cmigId.value = cmigs.value[0].id
  }
})
</script>

<style scoped>
.bg-success-light {
  background-color: #d4edda !important;
}
</style>
