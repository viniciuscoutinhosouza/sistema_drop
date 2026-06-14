<template>
  <div class="icm-overlay" @click.self="cancel">
    <div class="icm-modal card">
      <div class="card-header py-2 d-flex align-items-center">
        <strong><i class="fas fa-crop-alt mr-2"></i>Ajustar imagem ao padrão</strong>
        <button class="btn btn-xs btn-light ml-auto" @click="cancel" :disabled="busy"><i class="fas fa-times"></i></button>
      </div>
      <div class="card-body">
        <div class="row">
          <div class="col-md-6 text-center">
            <img v-if="previewUrl" :src="previewUrl" style="max-width:100%;max-height:240px;object-fit:contain;border:1px solid #dee2e6;border-radius:4px" />
          </div>
          <div class="col-md-6">
            <p class="small mb-1"><strong>Padrão {{ marketplaceLabel }}:</strong>
              {{ spec.aspect }}, rec. {{ spec.rec_px }}px<span v-if="spec.max_mb">, máx {{ spec.max_mb }}MB</span>
            </p>
            <p class="small mb-1" v-if="info">Sua imagem: {{ info.width }}×{{ info.height }}px,
              {{ info.sizeMB.toFixed(1) }}MB, {{ info.format }}</p>
            <ul v-if="info && info.issues.length" class="small text-danger pl-3 mb-2">
              <li v-for="(iss, i) in info.issues" :key="i">{{ iss }}</li>
            </ul>
            <p v-else-if="info" class="small text-success mb-2"><i class="fas fa-check mr-1"></i>Dentro do padrão.</p>

            <div class="d-flex flex-column" style="gap:6px">
              <button class="btn btn-sm btn-primary" :disabled="busy" @click="doCrop">
                <i class="fas fa-crop mr-1"></i> Ajustar (cortar para {{ spec.aspect }})
              </button>
              <button class="btn btn-sm btn-info" :disabled="busy" @click="doPad">
                <i class="fas fa-border-style mr-1"></i> Adicionar borda (sem cortar)
              </button>
              <button v-if="aiEdit" class="btn btn-sm btn-outline-warning" :disabled="busy" @click="doAi">
                <i class="fas fa-magic mr-1"></i> Estender com IA (custo ~US$0,03)
              </button>
              <button class="btn btn-sm btn-outline-secondary" :disabled="busy" @click="useAsIs">
                Usar como está
              </button>
            </div>
            <p v-if="busy" class="small text-muted mt-2"><i class="fas fa-spinner fa-spin mr-1"></i>{{ busyMsg }}</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useToast } from '@/composables/useToast'
import api from '@/composables/useApi'
import { validateImage, parseAspect, cropToAspect, padToAspect } from '@/composables/useImageStandard'

const props = defineProps({
  file: { type: Object, required: true },          // File
  imageSpec: { type: Object, default: () => ({}) },// { aspect, rec_px, min_px, max_mb, formats }
  marketplace: { type: String, default: '' },
  marketplaceLabel: { type: String, default: '' },
  uploadUrl: { type: String, default: '/anuncios/upload-image' }, // endpoint p/ subir o blob corrigido
  aiEdit: { type: Boolean, default: true },
})
const emit = defineEmits(['done', 'cancel'])

const toast = useToast()
const spec = computed(() => props.imageSpec || {})
const info = ref(null)
const previewUrl = ref('')
const busy = ref(false)
const busyMsg = ref('')

onMounted(async () => {
  previewUrl.value = URL.createObjectURL(props.file)
  try { info.value = await validateImage(props.file, spec.value) } catch { /* ignore */ }
})
onBeforeUnmount(() => { if (previewUrl.value) URL.revokeObjectURL(previewUrl.value) })

function cancel() { if (!busy.value) emit('cancel') }

async function _uploadBlob(blob, name) {
  const fd = new FormData()
  fd.append('file', new File([blob], name, { type: blob.type || 'image/jpeg' }))
  const { data } = await api.post(props.uploadUrl, fd, { headers: { 'Content-Type': 'multipart/form-data' } })
  return data.url
}

async function _run(fn, msg) {
  busy.value = true; busyMsg.value = msg
  try {
    const url = await fn()
    if (url) emit('done', url)
  } catch (e) {
    toast.error(e?.response?.data?.detail || 'Falha ao processar a imagem')
    // mantém o modal aberto para o usuário tentar outra opção (crop/borda)
  } finally {
    busy.value = false; busyMsg.value = ''
  }
}

function doCrop() {
  const { w, h } = parseAspect(spec.value.aspect)
  _run(async () => {
    const blob = await cropToAspect(props.file, w, h, spec.value.rec_px)
    return _uploadBlob(blob, 'corrigida.jpg')
  }, 'Ajustando...')
}

function doPad() {
  const { w, h } = parseAspect(spec.value.aspect)
  _run(async () => {
    const blob = await padToAspect(props.file, w, h, spec.value.rec_px)
    return _uploadBlob(blob, 'corrigida.jpg')
  }, 'Adicionando borda...')
}

function doAi() {
  if (!confirm('Estender a imagem com IA tem custo por imagem (~US$0,03). Continuar?')) return
  const { w, h } = parseAspect(spec.value.aspect)
  _run(async () => {
    // Envia a imagem já com borda branca no formato alvo; a IA preenche as bordas.
    const padded = await padToAspect(props.file, w, h, spec.value.rec_px, '#ffffff')
    const fd = new FormData()
    fd.append('file', new File([padded], 'outpaint.jpg', { type: 'image/jpeg' }))
    fd.append('marketplace', props.marketplace || '')
    const { data } = await api.post('/media/ai-edit', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
    return data.url
  }, 'Estendendo com IA...')
}

function useAsIs() {
  _run(async () => _uploadBlob(props.file, props.file.name || 'foto.jpg'), 'Enviando...')
}
</script>

<style scoped>
.icm-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.5);
  display: flex; align-items: center; justify-content: center; z-index: 1080;
}
.icm-modal { width: 640px; max-width: 95vw; margin: 0; }
.btn-xs { padding: 1px 6px; font-size: 11px; }
</style>
