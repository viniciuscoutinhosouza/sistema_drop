<script setup>
import { ref, onMounted } from 'vue'
import { useToast } from '@/composables/useToast'
import { useMessageTemplates } from '@/composables/useMessageTemplates'

const emit = defineEmits(['close', 'use'])
const toast = useToast()
const { list, create, update, remove } = useMessageTemplates()

const items = ref([])
const loading = ref(true)
const editing = ref(null) // {id?, title, body}

async function load() {
  loading.value = true
  try {
    items.value = await list()
  } catch (e) {
    toast.error('Falha ao carregar mensagens prontas.')
  } finally {
    loading.value = false
  }
}

function newTemplate() {
  editing.value = { title: '', body: '' }
}
function edit(t) {
  editing.value = { id: t.id, title: t.title, body: t.body }
}
async function save() {
  const e = editing.value
  if (!e.title.trim() || !e.body.trim()) {
    toast.warning('Preencha título e conteúdo.')
    return
  }
  try {
    if (e.id) await update(e.id, { title: e.title, body: e.body })
    else await create({ title: e.title, body: e.body })
    editing.value = null
    await load()
    toast.success('Mensagem pronta salva.')
  } catch (err) {
    toast.error(err.response?.data?.detail || 'Falha ao salvar.')
  }
}
async function del(t) {
  if (!confirm(`Excluir a mensagem pronta "${t.title}"?`)) return
  try {
    await remove(t.id)
    await load()
  } catch (err) {
    toast.error(err.response?.data?.detail || 'Falha ao excluir.')
  }
}

onMounted(load)
</script>

<template>
  <div class="cad-overlay" @click.self="$emit('close')">
    <div class="cad-modal card">
      <div class="card-header py-2 d-flex align-items-center">
        <strong><i class="fas fa-comment-dots mr-2"></i>Mensagens Prontas</strong>
        <button class="btn btn-sm btn-light ml-auto" @click="$emit('close')"><i class="fas fa-times"></i></button>
      </div>
      <div class="card-body">
        <!-- Edição -->
        <div v-if="editing" class="border rounded p-2 mb-2 bg-light">
          <input v-model="editing.title" class="form-control form-control-sm mb-2" placeholder="Título" maxlength="200" />
          <textarea v-model="editing.body" class="form-control form-control-sm mb-2" rows="3" placeholder="Conteúdo da mensagem"></textarea>
          <button class="btn btn-sm btn-primary" @click="save"><i class="fas fa-save mr-1"></i>Salvar</button>
          <button class="btn btn-sm btn-outline-secondary ml-1" @click="editing = null">Cancelar</button>
        </div>
        <button v-else class="btn btn-sm btn-outline-primary mb-2" @click="newTemplate">
          <i class="fas fa-plus mr-1"></i>Nova mensagem pronta
        </button>

        <!-- Lista -->
        <div v-if="loading" class="text-center text-muted py-3"><i class="fas fa-spinner fa-spin"></i></div>
        <div v-else-if="!items.length" class="text-muted small">Nenhuma mensagem pronta cadastrada.</div>
        <div v-for="t in items" :key="t.id" class="border-bottom py-2 d-flex align-items-start">
          <div class="flex-grow-1">
            <div class="font-weight-bold small">{{ t.title }}
              <span class="badge badge-light border ml-1">{{ t.scope === 'cmig' ? 'CMIG' : 'Pessoal' }}</span>
            </div>
            <div class="small text-muted" style="white-space:pre-wrap">{{ t.body }}</div>
          </div>
          <div class="ml-2 text-nowrap">
            <button class="btn btn-xs btn-success" title="Usar" @click="$emit('use', t.body)"><i class="fas fa-check"></i></button>
            <button class="btn btn-xs btn-outline-secondary" title="Editar" @click="edit(t)"><i class="fas fa-edit"></i></button>
            <button class="btn btn-xs btn-outline-danger" title="Excluir" @click="del(t)"><i class="fas fa-trash"></i></button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cad-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 1085; }
.cad-modal { width: 560px; max-width: 95vw; margin: 0; max-height: 90vh; overflow-y: auto; }
</style>
