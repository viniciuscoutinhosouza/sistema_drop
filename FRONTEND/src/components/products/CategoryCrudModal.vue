<template>
  <div v-if="visible" class="modal fade show d-block" style="background:rgba(0,0,0,.5)">
    <div class="modal-dialog modal-lg">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title"><i class="fas fa-folder-open mr-2"></i>Gerenciar Categorias</h5>
          <button type="button" class="close" @click="$emit('close')"><span>&times;</span></button>
        </div>
        <div class="modal-body">
          <div v-if="error" class="alert alert-danger py-1">{{ error }}</div>

          <!-- Formulário inline (criar / editar) -->
          <form class="form-inline mb-3" @submit.prevent="save">
            <input v-model="form.name" class="form-control form-control-sm mr-2"
                   placeholder="Nome da categoria" style="min-width:220px" />
            <select v-model="form.parent_id" class="form-control form-control-sm mr-2">
              <option :value="null">— Sem categoria pai —</option>
              <option v-for="c in parentOptions" :key="c.id" :value="c.id">{{ c.name }}</option>
            </select>
            <button type="submit" class="btn btn-sm btn-primary mr-1" :disabled="saving || !form.name.trim()">
              <i v-if="saving" class="fas fa-spinner fa-spin mr-1"></i>
              {{ form.id ? 'Salvar' : 'Criar' }}
            </button>
            <button v-if="form.id" type="button" class="btn btn-sm btn-secondary" @click="resetForm">
              Cancelar
            </button>
          </form>

          <!-- Tabela hierárquica -->
          <div v-if="loading" class="text-center py-3">
            <i class="fas fa-spinner fa-spin"></i> Carregando...
          </div>
          <div v-else-if="categories.length === 0" class="text-center text-muted py-3">
            Nenhuma categoria cadastrada.
          </div>
          <table v-else class="table table-sm table-hover mb-0">
            <thead>
              <tr>
                <th>Nome</th>
                <th>Categoria Pai</th>
                <th class="text-right">Ações</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="c in sorted" :key="c.id">
                <td>
                  <span v-if="c.parent_id" class="text-muted mr-1">└</span>
                  {{ c.name }}
                </td>
                <td class="text-muted small">{{ parentName(c.parent_id) || '—' }}</td>
                <td class="text-right">
                  <button class="btn btn-xs btn-outline-primary mr-1" @click="edit(c)">
                    <i class="fas fa-edit"></i>
                  </button>
                  <button class="btn btn-xs btn-outline-success mr-1" @click="select(c)">
                    Selecionar
                  </button>
                  <button class="btn btn-xs btn-outline-danger" @click="remove(c)">
                    <i class="fas fa-trash"></i>
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" @click="$emit('close')">Fechar</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'

const props = defineProps({
  visible: { type: Boolean, default: false },
})
const emit = defineEmits(['close', 'select', 'changed'])

const toast = useToast()

const categories = ref([])
const loading    = ref(false)
const saving     = ref(false)
const error      = ref('')
const form       = ref({ id: null, name: '', parent_id: null })

const parentOptions = computed(() =>
  categories.value.filter(c => !c.parent_id && c.id !== form.value.id)
)

const sorted = computed(() => {
  const byName = (a, b) => a.name.localeCompare(b.name, 'pt-BR')
  const parents = categories.value.filter(c => !c.parent_id).slice().sort(byName)
  const orphans = categories.value.filter(c => c.parent_id && !parents.some(p => p.id === c.parent_id))
  const result  = []
  for (const p of parents) {
    result.push(p)
    const children = categories.value.filter(c => c.parent_id === p.id).slice().sort(byName)
    result.push(...children)
  }
  result.push(...orphans.slice().sort(byName))
  return result
})

function parentName(id) {
  return categories.value.find(c => c.id === id)?.name
}

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/catalog/categories')
    categories.value = data
  } catch (e) {
    error.value = e.response?.data?.detail || 'Erro ao carregar categorias.'
  } finally {
    loading.value = false
  }
}

function resetForm() {
  form.value = { id: null, name: '', parent_id: null }
  error.value = ''
}

function edit(c) {
  form.value = { id: c.id, name: c.name, parent_id: c.parent_id }
  error.value = ''
}

async function save() {
  error.value = ''
  saving.value = true
  try {
    if (form.value.id) {
      await api.put(`/catalog/categories/${form.value.id}`, {
        name: form.value.name.trim(),
        parent_id: form.value.parent_id,
      })
      toast.success('Categoria atualizada!')
    } else {
      await api.post('/catalog/categories', {
        name: form.value.name.trim(),
        parent_id: form.value.parent_id,
      })
      toast.success('Categoria criada!')
    }
    resetForm()
    await load()
    emit('changed')
  } catch (e) {
    error.value = e.response?.data?.detail || 'Erro ao salvar categoria.'
  } finally {
    saving.value = false
  }
}

async function remove(c) {
  if (!confirm(`Excluir a categoria "${c.name}"?`)) return
  try {
    await api.delete(`/catalog/categories/${c.id}`)
    toast.success('Categoria excluída!')
    await load()
    emit('changed')
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao excluir categoria.')
  }
}

function select(c) {
  emit('select', c)
}

watch(() => props.visible, (v) => { if (v) { resetForm(); load() } })
</script>
