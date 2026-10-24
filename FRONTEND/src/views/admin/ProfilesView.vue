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

              <!-- Permissões de ação -->
              <div class="mt-2 pt-2 border-top">
                <div class="text-muted font-weight-bold mb-1" style="font-size:10px;text-transform:uppercase;letter-spacing:.5px">
                  <i class="fas fa-key mr-1"></i>Ações ({{ profile.action_keys?.length || 0 }})
                </div>
                <div v-if="!profile.action_keys || profile.action_keys.length === 0" class="text-muted" style="font-size:11px">
                  Nenhuma permissão de ação
                </div>
                <div v-else class="d-flex flex-wrap" style="gap:4px">
                  <span v-for="key in profile.action_keys" :key="key"
                        class="badge badge-info" style="font-size:10px">
                    {{ actionLabel(key) }}
                  </span>
                </div>
              </div>
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
                <label class="font-weight-bold">Escopo de dados <span class="text-danger">*</span></label>
                <select v-model="modal.form.base_role" class="form-control">
                  <option value="admin">Global (vê tudo)</option>
                  <option value="go">Por Galpão</option>
                  <option value="ac">Por Conta-CMIG</option>
                </select>
                <small class="text-muted">Qual fatia de dados este perfil enxerga (isolamento). São só 3 estratégias possíveis. O que o perfil <em>pode fazer</em> vem das permissões de ação abaixo.</small>
              </div>
            </div>
            <div class="col-md-4" v-if="modal.form.base_role === 'ac'">
              <div class="form-group">
                <label class="font-weight-bold">Visibilidade de PG (Conta)</label>
                <select v-model="modal.form.conta_pg_scope" class="form-control">
                  <option value="posse">Por posse (CMIGs que é dono)</option>
                  <option value="administracao">Por administração (CMIGs que administra)</option>
                  <option value="nenhum">Não vê PG</option>
                </select>
                <small class="text-muted">Base dos galpões cujo PG o AC enxerga. CMIG é sempre por administração.</small>
              </div>
            </div>
          </div>

          <!-- Acesso por menu (árvore igual ao menu lateral) + ações (CRUD) de cada menu -->
          <div class="d-flex align-items-center mb-2">
            <span class="font-weight-bold"><i class="fas fa-sitemap mr-1"></i>Acesso por menu</span>
            <small class="text-muted ml-2">
              {{ modal.form.menu_keys.length }} menu(s) · {{ modal.form.action_keys.length }} ação(ões)
            </small>
            <div class="ml-auto">
              <button class="btn btn-xs btn-outline-secondary" @click="selectAll">Marcar tudo</button>
              <button class="btn btn-xs btn-outline-secondary ml-1" @click="selectNone">Limpar tudo</button>
            </div>
          </div>
          <p class="text-muted small mb-3">
            Marque os menus que este perfil enxerga — na mesma ordem do menu lateral. Dentro de cada
            menu, marque as <strong>ações</strong> <i class="fas fa-bolt text-warning"></i> (o que ele
            pode fazer). As ações são <em>independentes</em> do menu: dá para liberar a ação sem exibir
            o menu. O escopo de dados (galpão/CMIG) vem do campo acima; admin sempre pode tudo.
          </p>

          <div v-for="sec in menuTree" :key="sec.section" class="mb-3">
            <div class="menu-section-header">{{ sec.section }}</div>
            <div v-for="menu in sec.menus" :key="menu.key" class="menu-row">
              <div class="custom-control custom-checkbox">
                <input type="checkbox" class="custom-control-input"
                       :id="`mk_${menu.key}`" :value="menu.key" v-model="modal.form.menu_keys" />
                <label class="custom-control-label menu-name" :for="`mk_${menu.key}`">{{ menu.label }}</label>
              </div>
              <div v-if="menu.actions.length" class="menu-actions">
                <div v-for="act in menu.actions" :key="act.key"
                     class="custom-control custom-checkbox mb-1">
                  <input type="checkbox" class="custom-control-input"
                         :id="`ak_${act.key}`" :value="act.key" v-model="modal.form.action_keys" />
                  <label class="custom-control-label small" :for="`ak_${act.key}`">
                    <i class="fas fa-bolt text-warning mr-1" style="font-size:9px"></i>{{ act.label }}
                  </label>
                </div>
              </div>
            </div>
          </div>

          <!-- Ações sem menu próprio -->
          <div v-if="orphanActions.length" class="mb-3">
            <div class="menu-section-header">Outras ações</div>
            <div class="menu-row">
              <div class="menu-actions" style="margin-left:0">
                <div v-for="act in orphanActions" :key="act.key" class="custom-control custom-checkbox mb-1">
                  <input type="checkbox" class="custom-control-input"
                         :id="`ak_${act.key}`" :value="act.key" v-model="modal.form.action_keys" />
                  <label class="custom-control-label small" :for="`ak_${act.key}`">
                    <i class="fas fa-bolt text-warning mr-1" style="font-size:9px"></i>{{ act.label }}
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
const actionCatalog = ref([]) // [{key, label, menu, default_base_roles}]

const deleteTarget = ref(null)
const deleting = ref(false)

const modal = reactive({
  show: false,
  isEdit: false,
  editProfile: null,
  saving: false,
  error: '',
  form: { name: '', label: '', base_role: 'ac', conta_pg_scope: 'posse', menu_keys: [], action_keys: [] },
})

// ── Árvore (seção → menu → ações do menu), na ordem do catálogo = ordem do menu lateral ──
const menuTree = computed(() => {
  const sections = []
  const bySection = {}
  for (const m of menuCatalog.value) {
    if (!bySection[m.section]) {
      bySection[m.section] = { section: m.section, menus: [] }
      sections.push(bySection[m.section])
    }
    bySection[m.section].menus.push({
      ...m,
      actions: actionCatalog.value.filter(a => a.menu === m.key),
    })
  }
  return sections
})

// Ações sem menu (menu=null) ou cujo menu não existe no catálogo → "Outras ações".
const orphanActions = computed(() => {
  const valid = new Set(menuCatalog.value.map(m => m.key))
  return actionCatalog.value.filter(a => !a.menu || !valid.has(a.menu))
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

function actionLabel(key) {
  return actionCatalog.value.find(a => a.key === key)?.label || key
}

function roleLabel(role) {
  // base_role = modo de escopo de dados (ADR-0035). `ugo` aposentado → 'Por Galpão' (legado).
  return { admin: 'Global', ac: 'Por Conta-CMIG', ugo: 'Por Galpão', go: 'Por Galpão' }[role] || role
}

function roleClass(role) {
  return { admin: 'badge-danger', ac: 'badge-success', ugo: 'badge-warning', go: 'badge-warning' }[role] || 'badge-secondary'
}

// ── Carregar dados ───────────────────────────────────────────────────────────
async function load() {
  loading.value = true
  try {
    const [p, m, a] = await Promise.all([
      api.get('/profiles'),
      api.get('/profiles/menu-keys'),
      api.get('/profiles/action-keys'),
    ])
    profiles.value = p.data
    menuCatalog.value = m.data
    actionCatalog.value = a.data
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
  modal.form = { name: '', label: '', base_role: 'ac', conta_pg_scope: 'posse', menu_keys: [], action_keys: [] }
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
    conta_pg_scope: profile.conta_pg_scope || 'posse',
    menu_keys: [...profile.menu_keys],
    action_keys: [...(profile.action_keys || [])],
  }
  modal.show = true
}

// ── Marcar / limpar tudo (menus + ações) ─────────────────────────────────────
function selectAll() {
  modal.form.menu_keys = menuCatalog.value.map(m => m.key)
  modal.form.action_keys = actionCatalog.value.map(a => a.key)
}
function selectNone() {
  modal.form.menu_keys = []
  modal.form.action_keys = []
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
        conta_pg_scope: modal.form.conta_pg_scope,
        menu_keys: modal.form.menu_keys,
        action_keys: modal.form.action_keys,
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

<style scoped>
.menu-section-header {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: .5px;
  color: #6c757d;
  background: #f4f6f9;
  border-left: 3px solid #007bff;
  padding: 4px 8px;
  margin-bottom: 6px;
  border-radius: 2px;
}
.menu-row {
  padding: 4px 0 4px 6px;
  border-bottom: 1px solid #f0f0f0;
}
.menu-row:last-child {
  border-bottom: none;
}
.menu-name {
  font-weight: 600;
}
/* Ações aninhadas sob o menu (apenas visual — a ação é independente do menu) */
.menu-actions {
  margin-left: 26px;
  margin-top: 2px;
  padding-left: 10px;
  border-left: 2px dashed #e0e0e0;
}
</style>
