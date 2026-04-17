<template>
  <div class="card" style="max-width:600px">
    <div class="card-header"><h3 class="card-title">Editar Kit #{{ route.params.id }}</h3></div>
    <div class="card-body">
      <div v-if="!kit" class="text-center py-4"><i class="fas fa-spinner fa-spin"></i></div>
      <form v-else @submit.prevent="submit">
        <div class="form-group">
          <label>Título</label>
          <input v-model="form.title" type="text" class="form-control" required />
        </div>
        <div v-if="error" class="alert alert-danger py-2">{{ error }}</div>
        <button type="submit" class="btn btn-primary" :disabled="loading">Salvar</button>
        <RouterLink to="/kits" class="btn btn-secondary ml-2">Cancelar</RouterLink>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '@/composables/useApi'

const route = useRoute()
const router = useRouter()
const kit = ref(null)
const loading = ref(false)
const error = ref('')
const form = reactive({ title: '' })

onMounted(async () => {
  // Kits endpoint returns list – find by id
  const { data } = await api.get('/kits')
  kit.value = data.items.find(k => k.id === parseInt(route.params.id))
  if (kit.value) form.title = kit.value.title
})

async function submit() {
  loading.value = true
  error.value = ''
  try {
    await api.put(`/kits/${route.params.id}`, form)
    router.push('/kits')
  } catch (err) {
    error.value = err.response?.data?.detail || 'Erro ao salvar'
  } finally {
    loading.value = false
  }
}
</script>
