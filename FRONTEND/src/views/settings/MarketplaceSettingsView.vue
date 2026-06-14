<template>
  <div class="marketplace-settings">
    <div class="card card-outline card-primary">
      <div class="card-header">
        <h3 class="card-title">
          <i class="fas fa-store mr-2"></i>Configuração de Marketplaces
          <span class="badge badge-primary ml-1" style="font-size:9px">Super Admin</span>
        </h3>
      </div>

      <div class="card-body">
        <div v-if="loading" class="text-center py-5">
          <i class="fas fa-spinner fa-spin fa-2x text-muted"></i>
        </div>

        <template v-else>
          <!-- Abas por marketplace -->
          <ul class="nav nav-tabs mb-3">
            <li v-for="mp in marketplaces" :key="mp.marketplace" class="nav-item">
              <a
                href="#"
                class="nav-link"
                :class="{ active: activeTab === mp.marketplace }"
                @click.prevent="activeTab = mp.marketplace"
              >{{ mp.label }}</a>
            </li>
          </ul>

          <!-- Conteúdo da aba ativa -->
          <div v-if="current">
            <p class="text-muted">
              Formatos recomendados para <strong>{{ current.label }}</strong>. São sugestões
              (pesquisadas) — você pode editar. São usadas para orientar e validar uploads de
              fotos e clips deste marketplace.
            </p>

            <!-- Imagem -->
            <div class="card card-outline card-secondary">
              <div class="card-header py-2"><strong><i class="fas fa-image mr-1"></i> Imagem</strong></div>
              <div class="card-body">
                <div class="row">
                  <div class="form-group col-md-3">
                    <label class="small">Proporção</label>
                    <input v-model="form.media.image.aspect" class="form-control form-control-sm" placeholder="1:1" />
                  </div>
                  <div class="form-group col-md-3">
                    <label class="small">Px mínimo (lado)</label>
                    <input v-model.number="form.media.image.min_px" type="number" class="form-control form-control-sm" />
                  </div>
                  <div class="form-group col-md-3">
                    <label class="small">Px recomendado</label>
                    <input v-model.number="form.media.image.rec_px" type="number" class="form-control form-control-sm" />
                  </div>
                  <div class="form-group col-md-3">
                    <label class="small">Px máximo (0 = s/ limite)</label>
                    <input v-model.number="form.media.image.max_px" type="number" class="form-control form-control-sm" />
                  </div>
                  <div class="form-group col-md-3">
                    <label class="small">Tamanho máx (MB, 0 = s/ limite)</label>
                    <input v-model.number="form.media.image.max_mb" type="number" class="form-control form-control-sm" />
                  </div>
                  <div class="form-group col-md-3">
                    <label class="small">Formatos (separados por vírgula)</label>
                    <input v-model="imageFormats" class="form-control form-control-sm" placeholder="JPG, PNG" />
                  </div>
                  <div class="form-group col-md-6">
                    <label class="small">Observação / fundo</label>
                    <input v-model="form.media.image.background" class="form-control form-control-sm" />
                  </div>
                </div>
              </div>
            </div>

            <!-- Clip / Vídeo -->
            <div class="card card-outline card-secondary">
              <div class="card-header py-2">
                <strong><i class="fas fa-film mr-1"></i> Clip / Vídeo</strong>
              </div>
              <div class="card-body">
                <div class="form-check mb-2">
                  <input id="clipEnabled" v-model="form.media.clip.enabled" type="checkbox" class="form-check-input" />
                  <label for="clipEnabled" class="form-check-label">Marketplace aceita clip/vídeo</label>
                </div>
                <div class="row" :class="{ 'text-muted': !form.media.clip.enabled }">
                  <div class="form-group col-md-3">
                    <label class="small">Entrega</label>
                    <select v-model="form.media.clip.delivery" class="form-control form-control-sm" :disabled="!form.media.clip.enabled">
                      <option value="upload">Upload (arquivo)</option>
                      <option value="youtube">YouTube (link)</option>
                    </select>
                  </div>
                  <div class="form-group col-md-3">
                    <label class="small">Proporção</label>
                    <input v-model="form.media.clip.aspect" class="form-control form-control-sm" :disabled="!form.media.clip.enabled" placeholder="9:16" />
                  </div>
                  <div class="form-group col-md-3">
                    <label class="small">Seg. mínimo</label>
                    <input v-model.number="form.media.clip.min_sec" type="number" class="form-control form-control-sm" :disabled="!form.media.clip.enabled" />
                  </div>
                  <div class="form-group col-md-3">
                    <label class="small">Seg. máximo</label>
                    <input v-model.number="form.media.clip.max_sec" type="number" class="form-control form-control-sm" :disabled="!form.media.clip.enabled" />
                  </div>
                  <div class="form-group col-md-3">
                    <label class="small">Tamanho máx (MB)</label>
                    <input v-model.number="form.media.clip.max_mb" type="number" class="form-control form-control-sm" :disabled="!form.media.clip.enabled" />
                  </div>
                  <div class="form-group col-md-3">
                    <label class="small">Formatos</label>
                    <input v-model="clipFormats" class="form-control form-control-sm" :disabled="!form.media.clip.enabled" placeholder="MP4, MOV" />
                  </div>
                  <div class="form-group col-md-6">
                    <label class="small">Observação</label>
                    <input v-model="form.media.clip.note" class="form-control form-control-sm" :disabled="!form.media.clip.enabled" />
                  </div>
                  <div class="form-group col-12">
                    <label class="small">Prompt padrão para criação de clip por IA</label>
                    <textarea v-model="form.media.clip.ai_prompt" class="form-control form-control-sm" rows="2"
                      placeholder="Sugestão de prompt que aparece ao criar um clip por IA neste marketplace..."></textarea>
                  </div>
                </div>
              </div>
            </div>

            <div class="text-right">
              <button class="btn btn-primary" :disabled="saving" @click="save">
                <i class="fas" :class="saving ? 'fa-spinner fa-spin' : 'fa-save'"></i>
                Salvar {{ current.label }}
              </button>
            </div>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useToast } from '@/composables/useToast'
import api from '@/composables/useApi'

const toast = useToast()
const loading = ref(true)
const saving = ref(false)
const marketplaces = ref([])
const activeTab = ref('mercadolivre')

// Estrutura editável da aba ativa
const form = reactive({ media: { image: {}, clip: {} } })

const current = computed(() => marketplaces.value.find(m => m.marketplace === activeTab.value) || null)

// formatos como texto separado por vírgula <-> array
const imageFormats = computed({
  get: () => (form.media.image.formats || []).join(', '),
  set: (v) => { form.media.image.formats = v.split(',').map(s => s.trim()).filter(Boolean) },
})
const clipFormats = computed({
  get: () => (form.media.clip.formats || []).join(', '),
  set: (v) => { form.media.clip.formats = v.split(',').map(s => s.trim()).filter(Boolean) },
})

function loadFormFromCurrent() {
  const s = current.value?.settings?.media || {}
  form.media.image = { ...(s.image || {}) }
  form.media.clip = { ...(s.clip || {}) }
}

// Quando troca de aba, recarrega o form com os dados daquele marketplace
import { watch } from 'vue'
watch(activeTab, loadFormFromCurrent)

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/marketplace-settings')
    marketplaces.value = data.marketplaces || []
    loadFormFromCurrent()
  } catch (e) {
    toast.error('Erro ao carregar configurações de marketplaces')
    console.error('[mkt-settings]', e?.response?.status ?? e?.message)
  } finally {
    loading.value = false
  }
}

async function save() {
  if (!current.value) return
  saving.value = true
  try {
    const { data } = await api.put(`/marketplace-settings/${activeTab.value}`, { media: form.media })
    // Atualiza o cache local com o que o backend devolveu (defaults mesclados)
    const idx = marketplaces.value.findIndex(m => m.marketplace === activeTab.value)
    if (idx >= 0) marketplaces.value[idx].settings = data.settings
    toast.success(`Configuração de ${current.value.label} salva`)
  } catch (e) {
    toast.error(e?.response?.data?.detail || 'Erro ao salvar')
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>
