<template>
  <div v-if="show" class="modal fade show d-block" tabindex="-1" style="background: rgba(0,0,0,.5)">
    <div class="modal-dialog modal-lg modal-dialog-scrollable">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title"><i class="fas fa-file-excel text-success mr-2"></i>Importar produtos por planilha</h5>
          <button type="button" class="close" @click="close"><span>&times;</span></button>
        </div>
        <div class="modal-body">
          <p class="text-muted small mb-2">
            Cadastre vários produtos <strong>simples</strong> de uma vez. Baixe o modelo, preencha e envie.
            O estoque entra depois pela nota/pedido (como no cadastro normal).
          </p>
          <button class="btn btn-sm btn-outline-secondary mb-3" @click="downloadTemplate" :disabled="downloading">
            <i class="fas fa-download mr-1"></i> {{ downloading ? 'Baixando...' : 'Baixar modelo (.xlsx)' }}
          </button>

          <div class="form-group">
            <label class="font-weight-bold small">Planilha preenchida (.xlsx)</label>
            <input ref="fileInput" type="file" accept=".xlsx" class="form-control-file" @change="onFile" />
          </div>
          <button class="btn btn-primary btn-sm" :disabled="!file || importing" @click="doImport">
            <i class="fas mr-1" :class="importing ? 'fa-spinner fa-spin' : 'fa-upload'"></i> Importar
          </button>

          <div v-if="report" class="mt-3">
            <div class="alert py-2" :class="report.erros && report.erros.length ? 'alert-warning' : 'alert-success'">
              <strong>{{ report.criados }}</strong> produto(s) criado(s) de {{ report.total }}.
              <span v-if="report.erros && report.erros.length"> — {{ report.erros.length }} com erro.</span>
            </div>
            <div v-if="report.erros && report.erros.length">
              <h6 class="text-danger mb-1">Erros</h6>
              <table class="table table-sm table-bordered">
                <thead><tr><th style="width:70px">Linha</th><th>SKU</th><th>Motivo</th></tr></thead>
                <tbody>
                  <tr v-for="(e, i) in report.erros" :key="'e' + i">
                    <td>{{ e.row }}</td><td>{{ e.sku }}</td><td>{{ e.motivo }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-if="report.avisos && report.avisos.length">
              <h6 class="text-warning mb-1">Avisos</h6>
              <ul class="small mb-0">
                <li v-for="(a, i) in report.avisos" :key="'a' + i">
                  Linha {{ a.row }} ({{ a.sku }}): {{ a.aviso }}
                </li>
              </ul>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary btn-sm" @click="close">Fechar</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { saveBlobResponse } from '@/utils/download'

const props = defineProps({
  show: { type: Boolean, default: false },
  endpoint: { type: String, required: true },     // POST .../import
  templateUrl: { type: String, required: true },  // GET  .../import/template
})
const emit = defineEmits(['close', 'imported'])
const toast = useToast()
const XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

const downloading = ref(false)
const importing = ref(false)
const file = ref(null)
const fileInput = ref(null)
const report = ref(null)

async function downloadTemplate() {
  downloading.value = true
  try {
    const resp = await api.get(props.templateUrl, { responseType: 'blob' })
    saveBlobResponse(resp, 'modelo_produtos.xlsx', XLSX_MIME)
  } catch {
    toast.error('Falha ao baixar o modelo.')
  } finally {
    downloading.value = false
  }
}

function onFile(e) {
  file.value = (e.target.files && e.target.files[0]) || null
  report.value = null
}

async function doImport() {
  if (!file.value) return
  importing.value = true
  try {
    const fd = new FormData()
    fd.append('file', file.value)
    const { data } = await api.post(props.endpoint, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    report.value = data
    if (data.criados > 0) {
      toast.success(`${data.criados} produto(s) importado(s).`)
      emit('imported')
    } else if (data.erros && data.erros.length) {
      toast.warning('Nenhum produto importado — verifique os erros.')
    }
  } catch (err) {
    toast.error(err?.response?.data?.detail || 'Falha ao importar a planilha.')
  } finally {
    importing.value = false
  }
}

function close() {
  file.value = null
  report.value = null
  if (fileInput.value) fileInput.value.value = ''
  emit('close')
}
</script>
