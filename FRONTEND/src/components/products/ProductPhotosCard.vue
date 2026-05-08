<template>
  <div class="mb-3">
    <label class="d-block font-weight-bold small text-muted text-uppercase mb-1">
      <i class="fas fa-images mr-1"></i>Fotos ({{ modelValue.length }})
    </label>

    <!-- Galeria -->
    <div class="d-flex flex-wrap mb-2" style="gap:6px">
      <div v-for="(pic, i) in modelValue" :key="i" class="position-relative">
        <img
          :src="pic.url"
          class="rounded"
          style="width:72px;height:72px;object-fit:cover;cursor:default"
          :style="pic.lowQuality ? 'border:2px solid #dc3545' : 'border:2px solid #dee2e6'"
          :title="pic.lowQuality
            ? `Baixa qualidade: ${pic.w}×${pic.h}px — recomendado 1200×1200px`
            : (pic.w ? `${pic.w}×${pic.h}px` : pic.url)"
        />
        <!-- Badge baixa qualidade -->
        <span
          v-if="pic.lowQuality"
          class="position-absolute d-flex align-items-center justify-content-center bg-danger text-white rounded"
          style="bottom:2px;left:2px;width:18px;height:18px;font-size:9px"
          title="Foto abaixo de 1200×1200px"
        >
          <i class="fas fa-exclamation"></i>
        </span>
        <!-- Botão remover -->
        <button
          type="button"
          class="btn btn-danger position-absolute"
          style="top:-6px;right:-6px;width:20px;height:20px;padding:0;line-height:1;border-radius:50%;font-size:10px"
          title="Remover foto"
          @click="removePhoto(i)"
        >
          <i class="fas fa-times"></i>
        </button>
      </div>
      <div v-if="modelValue.length === 0" class="text-muted small d-flex align-items-center py-1">
        Nenhuma foto cadastrada.
      </div>
    </div>

    <!-- Aviso baixa qualidade -->
    <div v-if="hasLowQuality" class="alert alert-warning py-1 px-2 mb-2" style="font-size:12px">
      <i class="fas fa-exclamation-triangle mr-1"></i>
      Foto(s) marcada(s) em vermelho estão abaixo de 1200×1200px e podem prejudicar o anúncio.
      Substitua por versões de maior resolução.
    </div>

    <!-- Adicionar por URL -->
    <div class="input-group input-group-sm mb-2" style="max-width:520px">
      <input
        v-model="newPhotoUrl"
        class="form-control"
        placeholder="URL da foto (https://...)"
        @keyup.enter="addPhotoByUrl"
      />
      <div class="input-group-append">
        <button
          type="button"
          class="btn btn-outline-secondary"
          :disabled="!newPhotoUrl.trim() || checkingUrl"
          @click="addPhotoByUrl"
        >
          <i :class="checkingUrl ? 'fas fa-spinner fa-spin' : 'fas fa-link'" class="mr-1"></i>
          Adicionar URL
        </button>
      </div>
    </div>

    <!-- Upload de arquivo -->
    <input
      ref="fileInput"
      type="file"
      accept="image/jpeg,image/png,image/webp,image/gif"
      multiple
      class="d-none"
      @change="uploadFiles"
    />
    <button
      type="button"
      class="btn btn-sm btn-outline-primary"
      :disabled="uploading"
      @click="fileInput.click()"
    >
      <i :class="['fas', uploading ? 'fa-spinner fa-spin' : 'fa-upload', 'mr-1']"></i>
      {{ uploading ? 'Enviando...' : 'Upload de foto' }}
    </button>
    <small class="text-muted d-block mt-1" style="font-size:11px">
      <i class="fas fa-info-circle mr-1"></i>
      Resolução ideal: <strong>1200×1200px</strong>. Fotos maiores serão recusadas; menores aceitas com aviso.
    </small>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'

const MAX_PX = 1200

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  uploadUrl:  { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue'])
const toast = useToast()

const newPhotoUrl  = ref('')
const uploading    = ref(false)
const checkingUrl  = ref(false)
const fileInput    = ref(null)

const hasLowQuality = computed(() => props.modelValue.some(p => p.lowQuality))

function emitList(list) {
  emit('update:modelValue', list)
}

function removePhoto(index) {
  const next = [...props.modelValue]
  next.splice(index, 1)
  emitList(next)
}

/**
 * Carrega uma imagem e retorna suas dimensões naturais.
 * Retorna null se falhar (CORS, URL inválida, etc).
 */
function checkDimensions(src) {
  return new Promise((resolve) => {
    const img = new Image()
    img.onload  = () => resolve({ w: img.naturalWidth, h: img.naturalHeight })
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
    if (dims) {
      if (dims.w > MAX_PX || dims.h > MAX_PX) {
        toast.error(`Foto excede ${MAX_PX}×${MAX_PX}px (${dims.w}×${dims.h}px). Redimensione antes de adicionar.`)
        return
      }
      const lowQuality = dims.w < MAX_PX || dims.h < MAX_PX
      emitList([...props.modelValue, { url, lowQuality, w: dims.w, h: dims.h }])
    } else {
      // Não foi possível verificar (CORS) — adiciona sem validação
      emitList([...props.modelValue, { url }])
    }
    newPhotoUrl.value = ''
  } finally {
    checkingUrl.value = false
  }
}

async function uploadFiles(event) {
  const files = [...(event.target.files || [])]
  if (!files.length) return

  const endpoint = props.uploadUrl || '/anuncios/upload-image'

  for (const file of files) {
    const objectUrl = URL.createObjectURL(file)
    const dims = await checkDimensions(objectUrl)
    URL.revokeObjectURL(objectUrl)

    if (dims && (dims.w > MAX_PX || dims.h > MAX_PX)) {
      toast.error(
        `"${file.name}" excede ${MAX_PX}×${MAX_PX}px (${dims.w}×${dims.h}px). Redimensione antes de enviar.`
      )
      continue
    }

    uploading.value = true
    try {
      const fd = new FormData()
      fd.append('file', file)
      const { data } = await api.post(endpoint, fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      const lowQuality = !!(dims && (dims.w < MAX_PX || dims.h < MAX_PX))
      emitList([...props.modelValue, { url: data.url, lowQuality, w: dims?.w, h: dims?.h }])
      if (!lowQuality) toast.success('Foto adicionada!')
      else toast.warning(
        `Foto adicionada com aviso: ${dims.w}×${dims.h}px está abaixo de ${MAX_PX}×${MAX_PX}px.`
      )
    } catch (e) {
      toast.error(e.response?.data?.detail || `Erro ao enviar "${file.name}".`)
    } finally {
      uploading.value = false
    }
  }

  event.target.value = ''
}
</script>
