<template>
  <div>
    <button type="button" class="btn btn-sm btn-outline-secondary" @click="show = true">
      <i class="fas fa-images mr-1"></i>
      Fotos
      <span v-if="modelValue.length" class="badge badge-primary ml-1">{{ modelValue.length }}</span>
    </button>

    <div v-if="show" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,0.55);z-index:1080">
      <div class="modal-dialog modal-md modal-dialog-scrollable">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">
              <i class="fas fa-images mr-2"></i>Fotos da variação
              <span v-if="title" class="text-muted small ml-2">— {{ title }}</span>
            </h5>
            <button type="button" class="close" @click="show = false"><span>&times;</span></button>
          </div>

          <div class="modal-body">

            <!-- Selecionadas -->
            <div class="mb-3">
              <div class="text-muted small font-weight-bold mb-1">
                Selecionadas (a 1ª é a capa da variação):
              </div>
              <div v-if="modelValue.length" class="d-flex flex-wrap" style="gap:6px">
                <div v-for="(url, i) in modelValue" :key="`sel-${i}-${url}`" class="position-relative">
                  <img :src="url" style="width:64px;height:64px;object-fit:cover;border-radius:4px;border:2px solid #007bff" />
                  <span v-if="i === 0" class="position-absolute badge badge-primary"
                        style="top:2px;left:2px;font-size:8px;padding:1px 3px">Capa</span>
                  <button type="button" @click="removeAt(i)"
                          class="btn btn-danger position-absolute"
                          style="top:-6px;right:-6px;width:18px;height:18px;padding:0;line-height:1;border-radius:50%;font-size:9px">
                    <i class="fas fa-times"></i>
                  </button>
                </div>
              </div>
              <div v-else class="text-muted small">Nenhuma foto selecionada.</div>
              <div v-if="maxPictures && modelValue.length >= maxPictures" class="text-warning small mt-1">
                <i class="fas fa-exclamation-circle mr-1"></i>Limite de {{ maxPictures }} fotos atingido
              </div>
            </div>

            <!-- Galeria do produto -->
            <div v-if="productImages.length" class="mb-3">
              <div class="text-muted small font-weight-bold mb-1">
                Imagens do produto — clique para adicionar/remover:
              </div>
              <div class="d-flex flex-wrap" style="gap:6px">
                <div v-for="img in productImages" :key="`gal-${img.url}`"
                     class="position-relative" style="cursor:pointer" @click="toggle(img.url)">
                  <img :src="img.url"
                       style="width:56px;height:56px;object-fit:cover;border-radius:4px;transition:opacity .15s"
                       :style="isSelected(img.url) ? 'outline:3px solid #28a745;opacity:1' : 'outline:3px solid #dee2e6;opacity:.7'" />
                  <span v-if="isSelected(img.url)"
                        class="position-absolute d-flex align-items-center justify-content-center bg-success text-white"
                        style="top:2px;right:2px;width:14px;height:14px;border-radius:50%;font-size:8px">
                    <i class="fas fa-check"></i>
                  </span>
                </div>
              </div>
            </div>

            <!-- Adicionar por URL -->
            <div class="mb-2">
              <div class="text-muted small font-weight-bold mb-1">Adicionar por URL:</div>
              <div class="input-group input-group-sm">
                <input v-model="newUrl" class="form-control" placeholder="https://..." @keyup.enter="addByUrl" />
                <div class="input-group-append">
                  <button type="button" class="btn btn-outline-secondary" @click="addByUrl"
                          :disabled="!newUrl.trim() || isLimitReached">
                    <i class="fas fa-link mr-1"></i>Adicionar
                  </button>
                </div>
              </div>
            </div>

            <!-- Upload -->
            <div>
              <input ref="fileInput" type="file" accept="image/jpeg,image/png,image/webp,image/gif"
                     class="d-none" @change="uploadPhoto" />
              <button type="button" class="btn btn-sm btn-outline-primary"
                      @click="fileInput.click()" :disabled="uploading || isLimitReached">
                <i :class="['fas', uploading ? 'fa-spinner fa-spin' : 'fa-upload', 'mr-1']"></i>
                {{ uploading ? 'Enviando...' : 'Upload de foto' }}
              </button>
            </div>

            <div v-if="error" class="alert alert-danger py-2 mt-2 small mb-0">{{ error }}</div>
          </div>

          <div class="modal-footer">
            <button type="button" class="btn btn-secondary btn-sm" @click="show = false">Fechar</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import api from '@/composables/useApi'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },         // URLs selecionadas
  productImages: { type: Array, default: () => [] },      // [{url}, ...] do produto vinculado
  maxPictures: { type: Number, default: 10 },
  title: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue'])

const show = ref(false)
const newUrl = ref('')
const uploading = ref(false)
const fileInput = ref(null)
const error = ref('')

const isLimitReached = computed(() => props.maxPictures && props.modelValue.length >= props.maxPictures)

function isSelected(url) {
  return props.modelValue.includes(url)
}

function emitUpdate(next) {
  emit('update:modelValue', next)
}

function toggle(url) {
  const idx = props.modelValue.indexOf(url)
  if (idx === -1) {
    if (isLimitReached.value) { error.value = `Limite de ${props.maxPictures} fotos atingido`; return }
    emitUpdate([...props.modelValue, url])
  } else {
    const next = [...props.modelValue]
    next.splice(idx, 1)
    emitUpdate(next)
  }
  error.value = ''
}

function removeAt(i) {
  const next = [...props.modelValue]
  next.splice(i, 1)
  emitUpdate(next)
}

function addByUrl() {
  const url = newUrl.value.trim()
  if (!url || props.modelValue.includes(url)) return
  if (isLimitReached.value) { error.value = `Limite de ${props.maxPictures} fotos atingido`; return }
  emitUpdate([...props.modelValue, url])
  newUrl.value = ''
  error.value = ''
}

async function uploadPhoto(event) {
  const file = event.target.files?.[0]
  if (!file) return
  if (isLimitReached.value) { error.value = `Limite de ${props.maxPictures} fotos atingido`; return }
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', file)
    const { data } = await api.post('/anuncios/upload-image', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    if (data.url && !props.modelValue.includes(data.url)) {
      emitUpdate([...props.modelValue, data.url])
    }
    error.value = ''
  } catch (e) {
    error.value = e.response?.data?.detail || 'Erro ao enviar foto.'
  } finally {
    uploading.value = false
    event.target.value = ''
  }
}
</script>
