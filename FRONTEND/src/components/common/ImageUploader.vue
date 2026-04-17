<template>
  <div>
    <!-- Existing images -->
    <div v-if="modelValue.length" class="d-flex flex-wrap gap-2 mb-2">
      <div
        v-for="(img, i) in modelValue"
        :key="img.id ?? i"
        class="position-relative"
        style="width:90px;height:90px"
      >
        <img
          :src="img.url"
          class="img-thumbnail w-100 h-100"
          style="object-fit:cover"
          :alt="`Imagem ${i + 1}`"
        />
        <button
          type="button"
          class="btn btn-xs btn-danger position-absolute top-0 right-0"
          style="line-height:1;padding:2px 5px"
          @click="remove(i)"
        >
          <i class="fas fa-times"></i>
        </button>
        <div class="d-flex justify-content-between mt-1">
          <button type="button" class="btn btn-xs btn-light" :disabled="i === 0" @click="move(i, -1)">
            <i class="fas fa-arrow-left"></i>
          </button>
          <button type="button" class="btn btn-xs btn-light" :disabled="i === modelValue.length - 1" @click="move(i, 1)">
            <i class="fas fa-arrow-right"></i>
          </button>
        </div>
      </div>
    </div>

    <!-- Upload zone -->
    <div
      class="border rounded p-3 text-center text-muted"
      style="cursor:pointer;border-style:dashed!important"
      @click="triggerInput"
      @dragover.prevent
      @drop.prevent="onDrop"
    >
      <i class="fas fa-cloud-upload-alt fa-2x mb-1"></i>
      <div><small>Clique ou arraste imagens aqui (JPG/PNG, máx. 5MB cada)</small></div>
    </div>
    <input ref="inputRef" type="file" accept="image/*" multiple class="d-none" @change="onFiles" />

    <div v-if="uploading" class="mt-1 text-muted small">
      <i class="fas fa-spinner fa-spin mr-1"></i> Enviando...
    </div>
    <div v-if="error" class="mt-1 text-danger small">{{ error }}</div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import api from '@/composables/useApi'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },  // [{ id, url, sort_order }]
  uploadUrl:  { type: String, required: true },     // e.g. /catalog/42/images
})

const emit = defineEmits(['update:modelValue'])

const inputRef  = ref(null)
const uploading = ref(false)
const error     = ref('')

function triggerInput() { inputRef.value.click() }

function onFiles(e) { handleFiles(Array.from(e.target.files)) }
function onDrop(e)  { handleFiles(Array.from(e.dataTransfer.files)) }

async function handleFiles(files) {
  error.value = ''
  const valid = files.filter(f => f.type.startsWith('image/') && f.size <= 5 * 1024 * 1024)
  if (!valid.length) { error.value = 'Nenhum arquivo válido (JPG/PNG, máx. 5MB)'; return }

  uploading.value = true
  try {
    const results = await Promise.all(valid.map(async f => {
      const fd = new FormData()
      fd.append('file', f)
      const { data } = await api.post(props.uploadUrl, fd, { headers: { 'Content-Type': 'multipart/form-data' } })
      return data
    }))
    emit('update:modelValue', [...props.modelValue, ...results])
  } catch (err) {
    error.value = err.response?.data?.detail || 'Erro ao enviar imagem'
  } finally {
    uploading.value = false
    inputRef.value.value = ''
  }
}

function remove(i) {
  const list = [...props.modelValue]
  list.splice(i, 1)
  emit('update:modelValue', list)
}

function move(i, dir) {
  const list = [...props.modelValue]
  const [item] = list.splice(i, 1)
  list.splice(i + dir, 0, item)
  emit('update:modelValue', list)
}
</script>
