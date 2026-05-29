<template>
  <teleport to="body">
    <div
      v-if="show"
      class="modal fade show d-block"
      tabindex="-1"
      role="dialog"
      style="background:rgba(0,0,0,.5)"
      @click.self="close"
    >
      <div class="modal-dialog modal-lg modal-dialog-centered" role="document">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">
              <i class="fas fa-search mr-2"></i> Buscar cliente
            </h5>
            <button type="button" class="close" aria-label="Fechar" @click="close">
              <span aria-hidden="true">&times;</span>
            </button>
          </div>
          <div class="modal-body">
            <div class="input-group mb-3">
              <input
                v-model="searchTerm"
                type="text"
                class="form-control"
                placeholder="Nome ou CPF/CNPJ"
                @keyup.enter="reload"
              />
              <div class="input-group-append">
                <button class="btn btn-primary" type="button" :disabled="loading" @click="reload">
                  <i class="fas" :class="loading ? 'fa-spinner fa-spin' : 'fa-search'"></i>
                </button>
              </div>
            </div>

            <div v-if="loading && !items.length" class="text-center text-muted py-4">
              Carregando…
            </div>
            <div v-else-if="!items.length" class="text-center text-muted py-4">
              Nenhum cliente encontrado.
            </div>
            <table v-else class="table table-hover table-sm mb-0">
              <thead>
                <tr>
                  <th>Documento</th>
                  <th>Nome</th>
                  <th>Cidade/UF</th>
                  <th style="width:80px"></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="p in items" :key="p.id">
                  <td><small class="text-muted">{{ p.document }}</small></td>
                  <td>
                    <strong>{{ p.name }}</strong>
                    <small v-if="p.trade_name" class="d-block text-muted">{{ p.trade_name }}</small>
                  </td>
                  <td>
                    <small>{{ p.city || '-' }}{{ p.state ? '/' + p.state : '' }}</small>
                  </td>
                  <td class="text-right">
                    <button type="button" class="btn btn-sm btn-primary" @click="select(p)">
                      Selecionar
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>

            <div v-if="total > pageSize" class="d-flex justify-content-between align-items-center mt-2">
              <small class="text-muted">{{ items.length }} de {{ total }}</small>
              <div class="btn-group btn-group-sm">
                <button class="btn btn-outline-secondary" :disabled="page === 1" @click="changePage(page - 1)">
                  <i class="fas fa-chevron-left"></i>
                </button>
                <button class="btn btn-outline-secondary" disabled>Página {{ page }}</button>
                <button class="btn btn-outline-secondary" :disabled="page * pageSize >= total" @click="changePage(page + 1)">
                  <i class="fas fa-chevron-right"></i>
                </button>
              </div>
            </div>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" @click="close">Cancelar</button>
          </div>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup>
import { ref, watch } from 'vue'
import { usePeopleStore } from '@/stores/people'

const props = defineProps({
  show: { type: Boolean, default: false },
  cmigId: { type: Number, default: null },
})
const emit = defineEmits(['select', 'close'])

const peopleStore = usePeopleStore()
const items = ref([])
const total = ref(0)
const loading = ref(false)
const searchTerm = ref('')
const page = ref(1)
const pageSize = 10

async function reload() {
  if (!props.cmigId) {
    items.value = []
    total.value = 0
    return
  }
  loading.value = true
  try {
    const data = await peopleStore.fetchPeople({
      cmig_id: props.cmigId,
      is_customer: true,
      is_active: true,
      search: searchTerm.value || undefined,
      page: page.value,
      page_size: pageSize,
    })
    items.value = data.items || []
    total.value = data.total || 0
  } finally {
    loading.value = false
  }
}

function changePage(p) {
  page.value = p
  reload()
}

function select(p) {
  emit('select', p)
}

function close() {
  emit('close')
}

watch(() => props.show, (visible) => {
  if (visible) {
    searchTerm.value = ''
    page.value = 1
    reload()
  }
})
</script>
