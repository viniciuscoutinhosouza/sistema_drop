<template>
  <div class="mt-3 border-top pt-3">
    <h6 class="font-weight-bold mb-2"><i class="fas fa-download mr-1"></i>Importar catálogo do Bling</h6>

    <div v-if="job && (job.status === 'running')" class="alert alert-info py-2 mb-2">
      <i class="fas fa-spinner fa-spin mr-1"></i>
      <strong>Importando…</strong> {{ job.progresso || 'iniciando' }}
      <span class="d-block small">
        {{ job.criados }} criados · {{ job.atualizados }} atualizados · {{ job.pulados }} pulados ·
        {{ job.falhas }} falhas <span v-if="job.total"> (de {{ job.total }})</span>
      </span>
    </div>
    <div v-else-if="job && job.status === 'done'" class="alert alert-success py-2 mb-2">
      <i class="fas fa-check-circle mr-1"></i>
      <strong>Importação concluída.</strong>
      <span class="d-block small">
        {{ job.criados }} criados · {{ job.atualizados }} atualizados · {{ job.pulados }} pulados ·
        {{ job.falhas }} falhas.
      </span>
    </div>
    <div v-else-if="job && job.status === 'error'" class="alert alert-danger py-2 mb-2">
      <i class="fas fa-times-circle mr-1"></i> Falhou: {{ job.erro }}
    </div>

    <div class="row">
      <div class="col-md-6 form-group mb-2">
        <label class="small font-weight-bold mb-1 d-block">Importar para</label>
        <div class="btn-group btn-group-sm btn-block" role="group">
          <button type="button" class="btn" :class="target === 'cmig' ? 'btn-primary' : 'btn-outline-primary'"
                  @click="target = 'cmig'">CMIG (produtos da empresa)</button>
          <button type="button" class="btn" :class="target === 'pg' ? 'btn-primary' : 'btn-outline-primary'"
                  @click="target = 'pg'">PG (Produto Geral)</button>
        </div>
      </div>
      <div class="col-md-6 form-group mb-2">
        <label class="small font-weight-bold mb-1 d-block">Se o SKU já existe</label>
        <div class="btn-group btn-group-sm btn-block" role="group">
          <button type="button" class="btn" :class="onConflict === 'skip' ? 'btn-secondary' : 'btn-outline-secondary'"
                  @click="onConflict = 'skip'">Pular</button>
          <button type="button" class="btn" :class="onConflict === 'update' ? 'btn-secondary' : 'btn-outline-secondary'"
                  @click="onConflict = 'update'">Atualizar</button>
        </div>
      </div>
    </div>

    <div class="d-flex align-items-center mb-2" style="gap:1rem">
      <div class="custom-control custom-switch">
        <input type="checkbox" class="custom-control-input" id="blImgs" v-model="opts.images">
        <label class="custom-control-label small" for="blImgs">Baixar imagens</label>
      </div>
      <div class="custom-control custom-switch">
        <input type="checkbox" class="custom-control-input" id="blKits" v-model="opts.kits">
        <label class="custom-control-label small" for="blKits">Importar kits (componentes)</label>
      </div>
      <span v-if="preview" class="small text-muted ml-auto">
        {{ preview.itens.length }} produtos nesta página{{ preview.tem_mais ? '+' : '' }}
      </span>
    </div>

    <p class="small text-muted mb-2">
      Importa o catálogo inteiro do Bling (categorias + produtos + kits). O estoque NÃO é importado
      (continua controlado aqui). As variações entram como produtos próprios por SKU.
    </p>

    <button class="btn btn-sm btn-success" :disabled="running" @click="start">
      <i class="fas" :class="running ? 'fa-spinner fa-spin' : 'fa-play'"></i>
      {{ running ? 'Importando…' : 'Importar tudo do Bling' }}
    </button>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onBeforeUnmount } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'

const props = defineProps({ cmigId: { type: Number, required: true } })
const toast = useToast()

const target = ref('cmig')
const onConflict = ref('skip')
const opts = reactive({ images: true, kits: true })
const preview = ref(null)
const job = ref(null)
const running = ref(false)
let poll = null

async function loadPreview() {
  try {
    const { data } = await api.get(`/cmigs/${props.cmigId}/bling/products`, { params: { pagina: 1, limite: 100 } })
    preview.value = data
  } catch { /* o modal já mostra erro de conexão */ }
}

async function start() {
  running.value = true
  job.value = null
  try {
    const { data } = await api.post(`/cmigs/${props.cmigId}/bling/import`, {
      target: target.value,
      on_conflict: onConflict.value,
      options: { images: opts.images, kits: opts.kits },
    })
    toast.success('Importação iniciada')
    watchJob(data.job_id)
  } catch (e) {
    running.value = false
    toast.error(e.response?.data?.detail || 'Erro ao iniciar a importação')
  }
}

function watchJob(jobId) {
  const tick = async () => {
    try {
      const { data } = await api.get(`/cmigs/${props.cmigId}/bling/import/${jobId}`)
      job.value = data
      if (data.status !== 'running') {
        clearInterval(poll); poll = null; running.value = false
        if (data.status === 'done') toast.success('Importação concluída')
        else if (data.status === 'error') toast.error('A importação falhou')
      }
    } catch { /* mantém o poll */ }
  }
  tick()
  poll = setInterval(tick, 2000)
}

onMounted(loadPreview)
onBeforeUnmount(() => { if (poll) clearInterval(poll) })
</script>
