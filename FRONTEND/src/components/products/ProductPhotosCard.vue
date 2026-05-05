<template>
  <div class="mb-3">
    <label class="d-block font-weight-bold small text-muted text-uppercase mb-1">
      <i class="fas fa-images mr-1"></i>Fotos ({{ modelValue.length }})
    </label>
    <div class="d-flex flex-wrap mb-2">
      <div v-for="(pic, i) in modelValue" :key="i" class="position-relative mr-1 mb-1">
        <img :src="pic.url" class="rounded border"
             style="width:72px;height:72px;object-fit:cover;cursor:pointer;"
             :title="pic.url" />
        <button type="button" @click="removePhoto(i)"
                class="btn btn-danger position-absolute"
                style="top:-6px;right:-6px;width:20px;height:20px;padding:0;line-height:1;border-radius:50%;font-size:10px;"
                title="Remover foto">
          <i class="fas fa-times"></i>
        </button>
      </div>
      <div v-if="modelValue.length === 0" class="text-muted small d-flex align-items-center">
        Nenhuma foto cadastrada.
      </div>
    </div>

    <div class="input-group input-group-sm mb-2" style="max-width:500px">
      <input v-model="newPhotoUrl" class="form-control"
             placeholder="URL da foto (https://...)" @keyup.enter="addPhotoByUrl" />
      <div class="input-group-append">
        <button type="button" class="btn btn-outline-secondary"
                @click="addPhotoByUrl" :disabled="!newPhotoUrl.trim()">
          <i class="fas fa-link mr-1"></i>Adicionar URL
        </button>
      </div>
    </div>

    <div v-if="uploadUrl">
      <input ref="fileInput" type="file" accept="image/jpeg,image/png,image/webp,image/gif"
             class="d-none" @change="uploadPhoto" />
      <button type="button" class="btn btn-sm btn-outline-primary"
              @click="fileInput.click()" :disabled="uploading">
        <i :class="uploading ? 'fas fa-spinner fa-spin' : 'fas fa-upload'" class="mr-1"></i>
        {{ uploading ? 'Enviando...' : 'Upload de foto' }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  uploadUrl:  { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue'])
const toast = useToast()

const newPhotoUrl = ref('')
const uploading   = ref(false)
const fileInput   = ref(null)

function emitList(list) {
  emit('update:modelValue', list)
}

function removePhoto(index) {
  const next = [...props.modelValue]
  next.splice(index, 1)
  emitList(next)
}

function addPhotoByUrl() {
  const url = newPhotoUrl.value.trim()
  if (!url) return
  emitList([...props.modelValue, { url }])
  newPhotoUrl.value = ''
}

async function uploadPhoto(event) {
  const file = event.target.files?.[0]
  if (!file) return
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', file)
    const { data } = await api.post(props.uploadUrl, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    emitList([...props.modelValue, { url: data.url }])
    toast.success('Foto adicionada!')
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao enviar foto.')
  } finally {
    uploading.value = false
    event.target.value = ''
  }
}
</script>
