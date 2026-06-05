<template>
  <div class="content-header">
    <div class="container-fluid">
      <div class="row mb-2">
        <div class="col-sm-6">
          <h1 class="m-0"><i class="fas fa-shield-alt mr-2 text-primary"></i>Gestão de Perfis de Acesso</h1>
        </div>
      </div>
    </div>
  </div>

  <section class="content">
    <div class="container-fluid">

      <!-- Cabeçalho com botão Novo Perfil -->
      <div class="d-flex justify-content-between align-items-center mb-3">
        <p class="text-muted mb-0 small">
          Configure quais menus cada perfil pode acessar. Perfis de sistema
          <i class="fas fa-lock text-warning mx-1"></i> não podem ser deletados.
        </p>
        <button class="btn btn-primary btn-sm" @click="openCreate">
          <i class="fas fa-plus mr-1"></i> Novo Perfil
        </button>
      </div>

      <!-- Loading -->
      <div v-if="loading" class="text-center py-5">
        <i class="fas fa-spinner fa-spin fa-2x text-muted"></i>
      </div>

      <!-- Grid de perfis -->
      <div v-else class="row">
        <div v-for="profile in profiles" :key="profile.id" class="col-xl-4 col-lg-6 col-md-6 mb-4">
          <div class="card h-100 shadow-sm" :class="profile.is_system ? 'card-outline card-warning' : 'card-outline card-primary'">
            <div class="card-header py-2 d-flex align-items-center">
              <span class="font-weight-bold flex-grow-1">
                <i v-if="profile.is_system" class="fas fa-lock text-warning mr-2" title="Perfil de sistema"></i>
                {{ profile.label }}
                <span class="badge badge-secondary ml-2" style="font-size:10px">{{ profile.name }}</span>
              </span>
              <span :class="roleClass(profile.base_role)" class="badge ml-2" style="font-size:10px">
                {{ roleLabel(profile.base_role) }}
              </span>
              <span v-if="!profile.is_active" class="badge badge-danger ml-1" style="font-size:10px">Inativo</span>
            </div>

            <div class="card-body p-3" style="font-size:12px">
              <!-- Menus agrupados por seção -->
              <div v-if="profile.menu_keys.length === 0" class="text-muted text-center py-2">
                <i class="fas fa-eye-slash mr-1"></i>Nenhum menu configurado
              </div>
              <template v-else>
                <div v-for="(keys, section) in groupedMenus(profile.menu_keys)" :key="section" class="mb-2">
                  <div class="text-muted font-weight-bold mb-1" style="font-size:10px;text-transform:uppercase;letter-spacing:.5px">
                    {{ section }}
                  </div>
                  <div class="d-flex flex-wrap" style="gap:4px">
                    <span v-for="key in keys" :key="key"
                          class="badge badge-light border" style="font-size:10px">
                      {{ menuLabel(key) }}
                    </span>
                  </div>
                </div>
              </template>
            </div>

            <div class="card-footer py-2 d-flex justify-content-end" style="gap:6px">
              <button class="btn btn-sm btn-outline-primary" @click="openEdit(profile)">
                <i class="fas fa-edit mr-1"></i>Editar
              </button>
              <button v-if="!profile.is_system" class="btn btn-sm btn-outline-danger" @click="confirmDelete(profile)">
                <i class="fas fa-trash mr-1"></i>Excluir
              </button>
            </div>
          </div>
        </div>
      </div>

    </div>
  </section>

  <!-- ══ Modal: Criar / Editar Perfil ══════════════════════════════════════ -->
  <div v-if="modal.show" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.55);z-index:1050">
    <div class="modal-dialog modal-lg modal-dialog-scrollable">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title">
            <i class="fas fa-shield-alt mr-2"></i>
            {{ modal.isEdit ? 'Editar Perfil' : 'Novo Perfil de Acesso' }}
          </h5>
          <button type="button" class="close" @click="modal.show = false"><span>&times;</span></button>
        </div>

        <div class="modal-body">
          <!-- Dados básicos -->
          <div class="row">
            <div class="col-md-4">
              <div class="form-group">
                <label class="font-weight-bold">Nome (slug) <span class="text-danger">*</span></label>
                <input v-model="modal.form.name" type="text" class="form-control"
                       placeholder="ex: gc_avancado" maxlength="50"
                       :disabled="modal.isEdit" />
                <small class="text-muted">Identificador único, sem espaços</small>
              </div>
            </div>
            <div class="col-md-4">
              <div class="form-group">
                <label class="font-weight-bold">Label (exibição) <span class="text-danger">*</span></label>
                <input v-model="modal.form.label" type="text" class="form-control"
                       placeholder="ex: Gestor de Conta Avançado" maxlength="100" />
              </div>
            </div>
            <div class="col-md-4">
              <div class="form-group">
                <label class="font-weight-bold">Papel base (API) <span class="text-danger">*</span></label>
                <select v-model="modal.form.base_role" class="form-control"
                        :disabled="modal.isEdit && modal.editProfile?.is_system">
                  <option value="ac">GC — Gestor de Conta (ac)</option>
                  <option value="ugo">GL — Gestor Logístico (ugo)</option>
                  <option value="go">GO — Gestor Operacional (go)</option>
                  <option value="admin">Admin (admin)</option>
                </select>
                <small class="text-muted">Define as permissões de API (require_role)</small>
              </div>
            </div>
          </div>

          <!-- Seleção de menus -->
          <div class="font-weight-bold mb-2">
            <i class="fas fa-list-ul mr-1"></i>Menus permitidos
            <small class="text-muted ml-2">({{ modal.form.menu_keys.length }} selecionado(s))</small>
            <button class="btn btn-xs btn-outline-secondary ml-2" @click="selectAll">Todos</button>
            <button class="btn btn-xs btn-outline-secondary ml-1" @click="selectNone">Nenhum</button>
          </div>

          <div v-for="(items, section) in menuCatalogBySectionFiltered" :key="section" class="mb-3">
            <div class="text-muted font-weight-bold mb-1" style="font-size:11px;text-transform:uppercase;border-bottom:1px solid #dee2e6;padding-bottom:3px">
              {{ section }}
            </div>
            <div class="row">
              <div v-for="item in items" :key="item.key" class="col-md-4 col-sm-6">
                <div class="custom-control custom-checkbox mb-1">
                  <input type="checkbox" class="custom-control-input"
                         :id="`mk_${item.key}`"
                         :value="item.key"
                         v-model="modal.form.menu_keys" />
                  <label class="custom-control-label small" :for="`mk_${item.key}`">
                    {{ item.label }}
                  </label>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="modal-footer">
          <div v-if="modal.error" class="alert alert-danger py-2 w-100 mb-2 small">{{ modal.error }}</div>
          <button class="btn btn-secondary" @click="modal.show = false" :disabled="modal.saving">Cancelar</button>
          <button class="btn btn-primary" @click="saveProfile" :disabled="modal.saving">
            <i :class="['fas', modal.saving ? 'fa-spinner fa-spin' : 'fa-save', 'mr-1']"></i>
            {{ modal.saving ? 'Salvando...' : 'Salvar Perfil' }}
          </button>
        </div>
      </div>
    </div>
  </div>

  <!-- ══ Confirm Delete ═════════════════════════════════════════════════════ -->
  <div v-if="deleteTarget" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.55);z-index:1060">
    <div class="modal-dialog modal-sm">
      <div class="modal-content">
        <div class="modal-header">
          <h6 class="modal-title text-danger"><i class="fas fa-exclamation-triangle mr-2"></i>Confirmar Exclusão</h6>
          <button type="button" class="close" @click="deleteTarget = null"><span>&times;</span></button>
        </div>
        <div class="modal-body small">
          Deseja excluir o perfil <strong>{{ deleteTarget.label }}</strong>?
          <br>Usuários vinculados a ele perderão o perfil.
        </div>
        <div class="modal-footer py-2">
          <button class="btn btn-sm btn-secondary" @click="deleteTarget = null">Cancelar</button>
          <button class="btn btn-sm btn-danger" @click="doDelete" :disabled="deleting">
            <i :class="['fas', deleting ? 'fa-spinner fa-spin' : 'fa-trash', 'mr-1']"></i>
            {{ deleting ? 'Excluindo...' : 'Excluir' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'

const toast = useToast()

const profiles = ref([])
const loading = ref(true)
const menuCatalog = ref([])   // [{key, label, section}]

const deleteTarget = ref(null)
const deleting = ref(false)

const modal = reactive({
  show: false,
  isEdit: false,
  editProfile: null,
  saving: false,
  error: '',
  form: { name: '', label: '', base_role: 'ac', menu_keys: [] },
})

// ── Agrupamento do catálogo por seção ────────────────────────────────────────
const menuCatalogBySectionFiltered = computed(() => {
  const sections = {}
  for (const item of menuCatalog.value) {
    if (!sections[item.section]) sections[item.section] = []
    sections[item.section].push(item)
  }
  return sections
})

function groupedMenus(keys) {
  const bySection = {}
  for (const item of menuCatalog.value) {
    if (keys.includes(item.key)) {
      if (!bySection[item.section]) bySection[item.section] = []
      bySection[item.section].push(item.key)
    }
  }
  return bySection
}

function menuLabel(key) {
  return menuCatalog.value.find(m => m.key === key)?.label || key
}

function roleLabel(role) {
  return { admin: 'Admin', ac: 'GC', ugo: 'GL', go: 'GO' }[role] || role
}

function roleClass(role) {
  return { admin: 'badge-danger', ac: 'badge-success', ugo: 'badge-info', go: 'badge-warning' }[role] || 'badge-secondary'
}

// ── Carregar dados ───────────────────────────────────────────────────────────
async function load() {
  loading.value = true
  try {
    const [p, m] = await Promise.all([
      api.get('/profiles'),
      api.get('/profiles/menu-keys'),
    ])
    profiles.value = p.data
    menuCatalog.value = m.data
  } catch (e) {
    toast.error('Erro ao carregar perfis')
  } finally {
    loading.value = false
  }
}

onMounted(load)

// ── Abrir modal ───────────────────────────────────────────────────────────────
function openCreate() {
  modal.isEdit = false
  modal.editProfile = null
  modal.error = ''
  modal.form = { name: '', label: '', base_role: 'ac', menu_keys: [] }
  modal.show = true
}

function openEdit(profile) {
  modal.isEdit = true
  modal.editProfile = profile
  modal.error = ''
  modal.form = {
    name: profile.name,
    label: profile.label,
    base_role: profile.base_role,
    menu_keys: [...profile.menu_keys],
  }
  modal.show = true
}

// ── Selecionar / deselecionar todos ─────────────────────────────────────────
function selectAll() {
  modal.form.menu_keys = menuCatalog.value.map(m => m.key)
}
function selectNone() {
  modal.form.menu_keys = []
}

// ── Salvar ────────────────────────────────────────────────────────────────────
async function saveProfile() {
  modal.error = ''
  if (!modal.form.name.trim() || !modal.form.label.trim()) {
    modal.error = 'Nome e label são obrigatórios'
    return
  }
  modal.saving = true
  try {
    if (modal.isEdit) {
      await api.put(`/profiles/${modal.editProfile.id}`, {
        label: modal.form.label,
        base_role: modal.form.base_role,
        menu_keys: modal.form.menu_keys,
      })
      toast.success('Perfil atualizado com sucesso')
    } else {
      await api.post('/profiles', modal.form)
      toast.success('Perfil criado com sucesso')
    }
    modal.show = false
    await load()
  } catch (e) {
    modal.error = e.response?.data?.detail || 'Erro ao salvar perfil'
  } finally {
    modal.saving = false
  }
}

// ── Excluir ───────────────────────────────────────────────────────────────────
function confirmDelete(profile) {
  deleteTarget.value = profile
}

async function doDelete() {
  deleting.value = true
  try {
    await api.delete(`/profiles/${deleteTarget.value.id}`)
    toast.success('Perfil excluído')
    deleteTarget.value = null
    await load()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao excluir perfil')
  } finally {
    deleting.value = false
  }
}
</script>
