<template>
  <div class="mb-3">
    <label class="d-block font-weight-bold small text-muted text-uppercase mb-1">
      <i class="fas fa-images mr-1"></i>Fotos ({{ modelValue.length }})
    </label>

    <!-- Galeria (arraste para reordenar) -->
    <p v-if="modelValue.length" class="text-muted mb-1" style="font-size:11px">
      <i class="fas fa-arrows-alt mr-1"></i>Arraste para reordenar. A primeira (★) é a capa.
    </p>
    <draggable
      :model-value="modelValue"
      @update:model-value="emitList"
      item-key="url"
      class="d-flex flex-wrap mb-2"
      style="gap:6px"
      :animation="150"
    >
      <template #item="{ element: pic, index: i }">
        <div class="position-relative" style="width:72px;cursor:move"
          @mouseenter="startPreview($event, pic.url)" @mouseleave="stopPreview">
          <img
            :src="pic.url"
            class="rounded"
            style="width:72px;height:72px;object-fit:cover;display:block"
            :style="pic.lowQuality ? 'border:2px solid #dc3545' : 'border:2px solid #dee2e6'"
            :title="pic.lowQuality ? `Baixa qualidade: ${pic.w}×${pic.h}px` : (pic.w ? `${pic.w}×${pic.h}px` : pic.url)"
          />
          <span class="position-absolute d-flex align-items-center justify-content-center text-white rounded"
            style="top:2px;left:2px;min-width:18px;height:18px;font-size:9px;padding:0 3px;line-height:1"
            :style="i === 0 ? 'background:#007bff' : 'background:rgba(0,0,0,0.55)'"
            :title="i === 0 ? 'Foto de capa' : `Posição ${i+1}`"
          >{{ i === 0 ? '★' : i + 1 }}</span>
          <span v-if="pic.lowQuality"
            class="position-absolute d-flex align-items-center justify-content-center bg-danger text-white rounded"
            style="bottom:2px;left:2px;width:18px;height:18px;font-size:9px" title="Abaixo de 1200×1200px">
            <i class="fas fa-exclamation"></i>
          </span>
          <button type="button" class="btn btn-danger position-absolute"
            style="top:-6px;right:-6px;width:20px;height:20px;padding:0;line-height:1;border-radius:50%;font-size:10px"
            title="Remover foto" @click="removePhotoByUrl(pic.url)">
            <i class="fas fa-times"></i>
          </button>
        </div>
      </template>
    </draggable>
    <div v-if="modelValue.length === 0" class="text-muted small mb-2">Nenhuma foto cadastrada.</div>

    <!-- Adicionar por URL -->
    <div class="input-group input-group-sm mb-2" style="max-width:520px">
      <input v-model="newPhotoUrl" class="form-control" placeholder="URL da foto (https://...)" @keyup.enter="addPhotoByUrl" />
      <div class="input-group-append">
        <button type="button" class="btn btn-outline-secondary" :disabled="!newPhotoUrl.trim() || checkingUrl" @click="addPhotoByUrl">
          <i :class="checkingUrl ? 'fas fa-spinner fa-spin' : 'fas fa-link'" class="mr-1"></i>Adicionar URL
        </button>
      </div>
    </div>

    <!-- Upload de arquivo (com checagem de padrão) -->
    <input ref="fileInput" type="file" accept="image/jpeg,image/png,image/webp,image/gif" class="d-none" @change="onFileSelected" />
    <button type="button" class="btn btn-sm btn-outline-primary" :disabled="uploading" @click="fileInput.click()">
      <i :class="['fas', uploading ? 'fa-spinner fa-spin' : 'fa-upload', 'mr-1']"></i>
      {{ uploading ? 'Enviando...' : 'Upload de foto' }}
    </button>
    <button type="button" class="btn btn-sm btn-outline-info ml-1" @click="aiPhoto.open = !aiPhoto.open">
      <i class="fas fa-magic mr-1"></i>Criar foto (IA)
    </button>
    <button type="button" class="btn btn-sm btn-outline-info ml-1" @click="openAiClip">
      <i class="fas fa-film mr-1"></i>Criar clip (IA)
    </button>
    <small class="text-muted d-block mt-1" style="font-size:11px">
      <i class="fas fa-info-circle mr-1"></i>Padrão: <strong>1:1, 1200×1200px</strong>. Fora do padrão, oferecemos ajuste (cortar/borda/IA).
    </small>

    <!-- Painel criar foto IA -->
    <div v-if="aiPhoto.open" class="border rounded p-2 bg-light mt-2" style="max-width:520px">
      <label class="small font-weight-bold mb-1">Prompt para gerar uma foto</label>
      <textarea v-model="aiPhoto.prompt" class="form-control form-control-sm" rows="3" placeholder="Ex.: produto em fundo branco, vista frontal, estúdio."></textarea>
      <div class="custom-control custom-checkbox mt-1">
        <input type="checkbox" class="custom-control-input" id="ppcBrief" v-model="aiPhoto.includeBrief" />
        <label class="custom-control-label small" for="ppcBrief">Incluir ficha técnica/descrição do produto</label>
      </div>
      <p class="text-warning small mb-1 mt-1"><i class="fas fa-exclamation-triangle mr-1"></i>Custo por imagem (~US$0,03).</p>
      <button class="btn btn-sm btn-info" :disabled="aiPhoto.loading || !aiPhoto.prompt.trim()" @click="generateAiPhoto">
        <i :class="['fas', aiPhoto.loading ? 'fa-spinner fa-spin' : 'fa-magic', 'mr-1']"></i>{{ aiPhoto.loading ? 'Gerando...' : 'Gerar imagem' }}
      </button>
      <button class="btn btn-sm btn-outline-secondary ml-1" :disabled="aiPhoto.loading" @click="aiPhoto.open = false">Cancelar</button>
    </div>

    <!-- Painel criar clip IA -->
    <div v-if="aiClip.open" class="border rounded p-2 bg-light mt-2" style="max-width:520px">
      <label class="small font-weight-bold mb-1">Prompt para gerar um clip de vídeo</label>
      <textarea v-model="aiClip.prompt" class="form-control form-control-sm" rows="3" placeholder="Descreva o clip (movimento de câmera, cenário)."></textarea>
      <div class="custom-control custom-checkbox mt-1">
        <input type="checkbox" class="custom-control-input" id="ppcClipBrief" v-model="aiClip.includeBrief" />
        <label class="custom-control-label small" for="ppcClipBrief">Incluir ficha técnica/descrição do produto</label>
      </div>
      <small class="text-muted d-block">Usa a 1ª foto como referência (se houver).</small>
      <p class="text-warning small mb-1 mt-1"><i class="fas fa-exclamation-triangle mr-1"></i>Vídeo por IA custa por segundo (~US$0,15–0,30/clip) e leva ~30–60s.</p>
      <button class="btn btn-sm btn-info" :disabled="aiClip.loading || !aiClip.prompt.trim()" @click="generateAiClip">
        <i :class="['fas', aiClip.loading ? 'fa-spinner fa-spin' : 'fa-film', 'mr-1']"></i>{{ aiClip.loading ? 'Iniciando...' : 'Gerar clip' }}
      </button>
      <button class="btn btn-sm btn-outline-secondary ml-1" :disabled="aiClip.loading" @click="aiClip.open = false">Cancelar</button>
    </div>

    <!-- Clips gerados -->
    <div v-if="clips.length" class="mt-2">
      <h6 class="text-muted small text-uppercase mb-1">Clips gerados</h6>
      <div class="d-flex flex-wrap" style="gap:8px">
        <div v-for="c in clips" :key="c.job_id" class="text-center position-relative" style="width:150px">
          <div v-if="c.status === 'done' && c.url" style="position:relative;cursor:pointer" @click="clipPreview = c">
            <video :src="c.url" muted style="width:150px;height:95px;background:#000;border-radius:4px;object-fit:cover;display:block"></video>
            <span class="position-absolute" style="top:50%;left:50%;transform:translate(-50%,-50%);color:#fff;font-size:22px;text-shadow:0 0 6px #000"><i class="fas fa-play-circle"></i></span>
          </div>
          <div v-else class="d-flex align-items-center justify-content-center" style="width:150px;height:95px;background:#f1f1f1;border-radius:4px;font-size:11px;padding:4px">
            <span v-if="c.status === 'running'"><i class="fas fa-spinner fa-spin mr-1"></i>gerando...</span>
            <span v-else class="text-danger">{{ c.error || 'falhou' }}</span>
          </div>
          <button type="button" class="btn btn-danger position-absolute"
            style="top:-6px;right:-6px;width:20px;height:20px;padding:0;line-height:1;border-radius:50%;font-size:10px"
            title="Excluir clip" @click="removeClip(c.job_id)">
            <i class="fas fa-times"></i>
          </button>
          <a v-if="c.status === 'done' && c.url" :href="c.url" download class="btn btn-sm btn-outline-primary mt-1" style="font-size:10px;padding:1px 6px">
            <i class="fas fa-download mr-1"></i>Baixar
          </a>
        </div>
      </div>
    </div>

    <ClipPreviewModal v-if="clipPreview" :url="clipPreview.url" :prompt="clipPreview.prompt" @close="clipPreview = null" />

    <!-- Modal de correção -->
    <ImageCorrectionModal
      v-if="correction.open"
      :file="correction.file"
      :image-spec="GENERIC_SPEC"
      marketplace=""
      marketplace-label="produto"
      :upload-url="uploadUrl || '/anuncios/upload-image'"
      @done="onCorrectionDone"
      @cancel="correction.open = false"
    />
  </div>

  <!-- Preview hover -->
  <Teleport to="body">
    <div v-if="preview.show"
      style="position:fixed;z-index:9999;pointer-events:none;border-radius:8px;overflow:hidden;box-shadow:0 8px 32px rgba(0,0,0,.5);background:#111"
      :style="{ left: preview.left + 'px', top: preview.top + 'px' }">
      <img :src="preview.src" style="width:300px;height:300px;object-fit:contain;display:block" />
    </div>
  </Teleport>
</template>

<script setup>
import { ref, onBeforeMount } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import draggable from 'vuedraggable'
import ImageCorrectionModal from '@/components/common/ImageCorrectionModal.vue'
import ClipPreviewModal from '@/components/common/ClipPreviewModal.vue'
import { validateImage } from '@/composables/useImageStandard'
import { useMediaAi } from '@/composables/useMediaAi'

const MAX_PX = 1200
const GENERIC_SPEC = { aspect: '1:1', rec_px: 1200, min_px: 500, max_mb: 8, formats: ['JPG', 'PNG', 'WEBP', 'GIF'] }

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  uploadUrl:  { type: String, default: '' },
  productType: { type: String, default: '' },   // 'pg' | 'cmig' | ''
  productId:   { type: [Number, String], default: null },
})
const emit = defineEmits(['update:modelValue'])
const toast = useToast()
const mediaAi = useMediaAi()
const clips = mediaAi.clips  // alias top-level p/ auto-unwrap no template

const newPhotoUrl = ref('')
const uploading   = ref(false)
const checkingUrl = ref(false)
const fileInput   = ref(null)
const correction  = ref({ open: false, file: null })
const aiPhoto = ref({ open: false, prompt: '', includeBrief: true, loading: false })
const aiClip  = ref({ open: false, prompt: '', includeBrief: true, loading: false })
const clipPreview = ref(null)

onBeforeMount(() => {
  if (props.productId) mediaAi.loadClips({ productType: props.productType, productId: props.productId })
})

async function removeClip(jobId) {
  if (!confirm('Excluir este clip? Esta ação não pode ser desfeita.')) return
  try {
    await mediaAi.deleteClip(jobId)
    if (clipPreview.value?.job_id === jobId) clipPreview.value = null
  } catch (e) {
    toast.error(e?.response?.data?.detail || 'Erro ao excluir o clip')
  }
}

function emitList(list) { emit('update:modelValue', list) }

function removePhotoByUrl(url) {
  emitList(props.modelValue.filter(p => p.url !== url))
}

// --- Preview hover ---
const preview = ref({ show: false, src: '', left: 0, top: 0 })
let previewTimer = null
function startPreview(event, src) {
  clearTimeout(previewTimer)
  const rect = event.currentTarget.getBoundingClientRect()
  previewTimer = setTimeout(() => {
    const PW = 300, PH = 300, M = 10, vw = window.innerWidth, vh = window.innerHeight
    const cx = rect.left + rect.width / 2, cy = rect.top + rect.height / 2
    let left, top
    if (rect.bottom + PH + M <= vh) { top = rect.bottom + M; left = Math.min(Math.max(cx - PW / 2, M), vw - PW - M) }
    else if (rect.top - PH - M >= 0) { top = rect.top - PH - M; left = Math.min(Math.max(cx - PW / 2, M), vw - PW - M) }
    else if (rect.right + PW + M <= vw) { left = rect.right + M; top = Math.min(Math.max(cy - PH / 2, M), vh - PH - M) }
    else { left = Math.max(rect.left - PW - M, M); top = Math.min(Math.max(cy - PH / 2, M), vh - PH - M) }
    preview.value = { show: true, src, left, top }
  }, 1000)
}
function stopPreview() { clearTimeout(previewTimer); preview.value.show = false }

function checkDimensions(src) {
  return new Promise((resolve) => {
    const img = new Image()
    img.onload = () => resolve({ w: img.naturalWidth, h: img.naturalHeight })
    img.onerror = () => resolve(null)
    img.src = src
  })
}

async function addPhotoByUrl() {
  const url = newPhotoUrl.value.trim()
  if (!url) return
  checkingUrl.value = true
  try {
    const dims = await checkDimensions(url)
    const lowQuality = dims ? (dims.w < MAX_PX || dims.h < MAX_PX) : false
    emitList([...props.modelValue, dims ? { url, lowQuality, w: dims.w, h: dims.h } : { url }])
    newPhotoUrl.value = ''
  } finally {
    checkingUrl.value = false
  }
}

async function onFileSelected(e) {
  const file = e.target.files?.[0]
  if (!file) return
  try {
    const res = await validateImage(file, GENERIC_SPEC)
    if (!res.ok) {
      correction.value = { open: true, file }   // fora do padrão → modal de correção
    } else {
      await uploadFile(file)
    }
  } catch {
    toast.error('Erro ao ler a imagem')
  } finally {
    if (fileInput.value) fileInput.value.value = ''
  }
}

async function uploadFile(file) {
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', file)
    const { data } = await api.post(props.uploadUrl || '/anuncios/upload-image', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    if (data?.url) { pushPhoto(data.url); toast.success('Foto adicionada!') }
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao enviar a foto.')
  } finally {
    uploading.value = false
  }
}

async function pushPhoto(url) {
  const dims = await checkDimensions(url)
  const lowQuality = dims ? (dims.w < MAX_PX || dims.h < MAX_PX) : false
  emitList([...props.modelValue, dims ? { url, lowQuality, w: dims.w, h: dims.h } : { url }])
}

function onCorrectionDone(url) {
  correction.value.open = false
  if (url) pushPhoto(url)
}

async function generateAiPhoto() {
  const prompt = aiPhoto.value.prompt.trim()
  if (!prompt) return
  aiPhoto.value.loading = true
  try {
    const data = await mediaAi.generatePhoto({
      prompt,
      productType: props.productType || null,
      productId: props.productId || null,
      includeBrief: aiPhoto.value.includeBrief,
      sourceUrls: props.modelValue.map(p => p.url),
    })
    if (data?.url) {
      pushPhoto(data.url)
      toast.success('Imagem gerada e adicionada.')
      aiPhoto.value.open = false
      aiPhoto.value.prompt = ''
    }
  } catch (e) {
    toast.error(e?.response?.data?.detail || 'Erro ao gerar imagem por IA')
  } finally {
    aiPhoto.value.loading = false
  }
}

function openAiClip() { aiClip.value.open = !aiClip.value.open }

async function generateAiClip() {
  const prompt = aiClip.value.prompt.trim()
  if (!prompt) return
  aiClip.value.loading = true
  try {
    await mediaAi.startClip({
      prompt,
      productType: props.productType || null,
      productId: props.productId || null,
      includeBrief: aiClip.value.includeBrief,
      sourceUrl: props.modelValue[0]?.url || null,
    })
    aiClip.value.open = false
    aiClip.value.prompt = ''
  } catch (e) {
    toast.error(e?.response?.data?.detail || 'Erro ao iniciar o clip')
  } finally {
    aiClip.value.loading = false
  }
}
</script>
