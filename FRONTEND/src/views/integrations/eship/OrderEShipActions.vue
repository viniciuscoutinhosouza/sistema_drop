<template>
  <span class="d-inline-flex align-items-center" style="gap:.25rem">
    <template v-if="enviada">
      <!-- O número da ordem no WMS fica À VISTA no pedido — é por ele que o usuário confere o
           envio no painel do eShip, sem precisar abrir nada. -->
      <span class="badge badge-info" :title="order.eship_order_id
              ? `Ordem ${order.eship_order_id} no eShip — clique para ver/atualizar/excluir`
              : 'Pedido já enviado ao eShip — clique para ver a ordem'">
        <i class="fas fa-dolly-flatbed mr-1"></i>eShip
        <template v-if="order.eship_order_id"> #{{ order.eship_order_id }}</template>
      </span>
      <span class="badge" :class="order.eship_nfe_attached ? 'badge-success' : 'badge-light'"
            :title="order.eship_nfe_attached ? 'NF-e anexada à Ordem' : 'NF-e ainda não anexada'">NF-e</span>
      <span class="badge" :class="order.eship_label_attached ? 'badge-success' : 'badge-light'"
            :title="order.eship_label_attached ? 'Etiqueta anexada à Ordem' : 'Etiqueta ainda não anexada'">Etiq</span>
      <!-- Já enviado: o clique NUNCA reenvia direto — abre a ordem gravada e pergunta o que fazer. -->
      <button class="btn btn-xs" :class="pendente ? 'btn-outline-warning' : 'btn-outline-info'"
              :disabled="busy" title="Ver a ordem gravada no eShip (atualizar ou excluir)"
              @click="openOrdem">
        <i class="fas" :class="busy ? 'fa-spinner fa-spin' : 'fa-file-invoice'"></i>
      </button>
      <button class="btn btn-xs btn-outline-info" :disabled="busy"
              title="Sincronizar status com o eShip" @click="sync">
        <i class="fas" :class="busy ? 'fa-spinner fa-spin' : 'fa-sync'"></i>
      </button>
    </template>
    <template v-else>
      <span v-if="order.eship_dispatch_status === 'failed'" class="badge badge-danger"
            :title="order.eship_dispatch_error || 'Falha no último envio ao eShip'">
        <i class="fas fa-exclamation-triangle mr-1"></i>eShip
      </span>
      <button class="btn btn-xs btn-outline-secondary" :disabled="busy"
              title="Enviar ao eShip (Ordem + NF-e + Etiqueta)" @click="openPreview">
        <i class="fas mr-1" :class="busy ? 'fa-spinner fa-spin' : 'fa-dolly-flatbed'"></i>Enviar ao eShip
      </button>
    </template>

    <!-- Modal da ORDEM GRAVADA — evita o reenvio em duplicidade -->
    <Teleport to="body">
      <div v-if="showOrdem" class="eship-preview-backdrop" @click.self="closeOrdem">
        <div class="eship-preview-card card">
          <div class="card-header py-2 d-flex align-items-center">
            <strong><i class="fas fa-file-invoice mr-1"></i>Ordem no eShip — Pedido #{{ order.platform_order_id || order.id }}</strong>
            <button class="btn btn-sm btn-outline-secondary ml-auto" @click="closeOrdem" title="Fechar">
              <i class="fas fa-times"></i>
            </button>
          </div>
          <div class="card-body">
            <div v-if="!ordem" class="text-center text-muted py-4">
              <i class="fas fa-spinner fa-spin fa-2x"></i>
            </div>
            <template v-else>
              <p class="small text-muted mb-2">
                Este pedido <strong>já foi enviado</strong> ao eShip. Confira a ordem abaixo no painel do WMS.
                <strong>Atualizar</strong> reprocessa só o que ficou pendente (não recria a ordem).
                <strong>Excluir</strong> cancela a ordem no eShip e libera o pedido para um novo envio.
              </p>

              <table class="table table-sm mb-2">
                <tbody>
                  <tr>
                    <th style="width:180px" class="small">Código da ordem</th>
                    <td>
                      <template v-if="ordem.eship_order_id">
                        <span class="text-monospace">{{ ordem.eship_order_id }}</span>
                        <button class="btn btn-xs btn-outline-secondary ml-2"
                                @click="copy(ordem.eship_order_id, 'Código da ordem')">
                          <i class="fas fa-copy"></i>
                        </button>
                      </template>
                      <span v-else class="text-muted small">
                        <i class="fas fa-info-circle mr-1"></i>o eShip aceitou a ordem mas não devolveu um código —
                        confira pela resposta bruta / pelo <em>numeroOrigem</em>
                      </span>
                    </td>
                  </tr>
                  <tr>
                    <th class="small">numeroOrigem</th>
                    <td>
                      <span class="text-monospace">{{ ordem.numero_origem }}</span>
                      <button class="btn btn-xs btn-outline-secondary ml-2"
                              @click="copy(ordem.numero_origem, 'numeroOrigem')">
                        <i class="fas fa-copy"></i>
                      </button>
                      <small class="text-muted d-block">É por este número que o eShip endereça a ordem.</small>
                    </td>
                  </tr>
                  <tr>
                    <th class="small">Situação do envio</th>
                    <td>
                      <span class="badge" :class="statusClass">{{ statusLabel }}</span>
                      <span class="badge badge-light ml-1">{{ ordem.dispatch_attempts }} tentativa(s)</span>
                      <span class="badge ml-1" :class="ordem.nfe_attached ? 'badge-success' : 'badge-light'">NF-e</span>
                      <span class="badge ml-1" :class="ordem.label_attached ? 'badge-success' : 'badge-light'">Etiqueta</span>
                    </td>
                  </tr>
                  <tr v-if="ordem.dispatch_error">
                    <th class="small">Pendência</th>
                    <td class="small text-danger">{{ ordem.dispatch_error }}</td>
                  </tr>
                </tbody>
              </table>

              <!-- Arquivos que o WMS realmente tem — conferência de verdade, consultada no eShip,
                   e não o nosso selo local. -->
              <div class="mb-2">
                <strong class="small d-block mb-1">
                  <i class="fas fa-paperclip mr-1"></i>Arquivos anexados na ordem (consultados no eShip)
                </strong>
                <div v-if="anexosLoading" class="text-muted small">
                  <i class="fas fa-spinner fa-spin mr-1"></i>consultando o eShip...
                </div>
                <div v-else-if="anexosErro" class="small text-danger">{{ anexosErro }}</div>
                <table v-else-if="anexos.length" class="table table-sm table-bordered mb-0">
                  <thead>
                    <tr><th class="small">Categoria</th><th class="small">Arquivos</th><th class="small">Tamanho</th></tr>
                  </thead>
                  <tbody>
                    <tr v-for="a in anexos" :key="a.categoria">
                      <td class="small text-monospace">{{ a.categoria }}</td>
                      <td class="small">{{ a.quantidade }}</td>
                      <td class="small">{{ a.tamanho_kb }} KB</td>
                    </tr>
                  </tbody>
                </table>
                <div v-else class="small text-muted">Nenhum arquivo anexado nesta ordem.</div>
              </div>

              <div v-if="ordem.last_response">
                <button class="btn btn-xs btn-outline-secondary" @click="showRaw = !showRaw">
                  <i class="fas mr-1" :class="showRaw ? 'fa-chevron-down' : 'fa-chevron-right'"></i>
                  Resposta do eShip
                </button>
                <pre v-if="showRaw" class="eship-preview-pre mt-1">{{ rawPretty }}</pre>
              </div>
            </template>
          </div>
          <div class="card-footer d-flex" style="gap:.5rem">
            <button class="btn btn-sm btn-outline-secondary" @click="closeOrdem">Fechar</button>
            <button class="btn btn-sm btn-outline-danger" :disabled="busy || !ordem" @click="excluir">
              <i class="fas mr-1" :class="busy ? 'fa-spinner fa-spin' : 'fa-trash'"></i>Excluir ordem
            </button>
            <button class="btn btn-sm btn-warning ml-auto" :disabled="busy || !ordem" @click="atualizar">
              <i class="fas mr-1" :class="busy ? 'fa-spinner fa-spin' : 'fa-redo'"></i>
              Atualizar ordem
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Modal de prévia do curl (debug) — só no primeiro envio -->
    <Teleport to="body">
      <div v-if="showPreview" class="eship-preview-backdrop" @click.self="closePreview">
        <div class="eship-preview-card card">
          <div class="card-header py-2 d-flex align-items-center">
            <strong><i class="fas fa-dolly-flatbed mr-1"></i>Prévia do envio ao eShip — Pedido #{{ order.platform_order_id || order.id }}</strong>
            <button class="btn btn-sm btn-outline-secondary ml-auto" @click="closePreview" title="Fechar">
              <i class="fas fa-times"></i>
            </button>
          </div>
          <div class="card-body">
            <p class="small text-muted mb-2">
              Este é o <strong>webServicePostOrdem</strong> que o envio executaria. Copie o <em>Body</em> e cole no
              <strong>Console de API do eShip</strong> (a apikey é injetada lá), ou use o curl abaixo trocando o
              placeholder <code>SUA_APIKEY_ESHIP</code> pela apikey real.
            </p>

            <!-- Bloqueios: o corpo esta incompleto e o eShip vai recusar. Antes o campo faltante
                 era simplesmente omitido em silencio e o erro so aparecia no WMS. -->
            <div v-if="bloqueios.length" class="alert alert-danger py-2">
              <strong><i class="fas fa-exclamation-triangle mr-1"></i>Este envio será recusado pelo eShip:</strong>
              <ul class="mb-0 mt-1 pl-4 small">
                <li v-for="(b, i) in bloqueios" :key="i">{{ b }}</li>
              </ul>
            </div>

            <!-- Avisos: o envio é possível, mas a ordem iria incompleta ao WMS. Exige confirmação. -->
            <div v-if="avisos.length" class="alert alert-warning py-2">
              <strong><i class="fas fa-exclamation-circle mr-1"></i>Atenção — falta documento para este envio:</strong>
              <ul class="mb-0 mt-1 pl-4 small">
                <li v-for="(a, i) in avisos" :key="i">{{ a }}</li>
              </ul>
              <small class="d-block mt-1">
                Você pode enviar assim mesmo e completar depois (o botão <strong>Atualizar</strong> anexa o
                que faltou, sem recriar a ordem) — ou aguardar a NF-e/etiqueta e enviar tudo de uma vez.
              </small>
            </div>

            <div v-if="preview" class="small mb-2">
              <span class="badge badge-light mr-2">Função: <span class="text-monospace">{{ preview.funcao }}</span></span>
              <span class="badge badge-light mr-2">CMIG: {{ preview.cmig_id }}</span>
              <span class="badge badge-light">Armazém: {{ preview.warehouse_code || '—' }}</span>
            </div>

            <template v-if="preview">
              <div class="d-flex align-items-center mb-1">
                <strong class="small">Body (JSON)</strong>
                <button class="btn btn-xs btn-outline-secondary ml-auto" @click="copy(bodyPretty, 'Body')">
                  <i class="fas fa-copy mr-1"></i>Copiar body
                </button>
              </div>
              <pre class="eship-preview-pre">{{ bodyPretty }}</pre>

              <div class="d-flex align-items-center mb-1 mt-2">
                <strong class="small">curl</strong>
                <button class="btn btn-xs btn-outline-secondary ml-auto" @click="copy(preview.curl, 'curl')">
                  <i class="fas fa-copy mr-1"></i>Copiar curl
                </button>
              </div>
              <pre class="eship-preview-pre">{{ preview.curl }}</pre>
            </template>
            <div v-else class="text-center text-muted py-3">
              <i class="fas fa-spinner fa-spin fa-2x"></i>
            </div>
          </div>
          <div class="card-footer d-flex" style="gap:.5rem">
            <button class="btn btn-sm btn-outline-secondary" @click="closePreview">Fechar</button>
            <button class="btn btn-sm ml-auto" :class="avisos.length ? 'btn-danger' : 'btn-warning'"
                    :disabled="busy || !preview || bloqueios.length"
                    :title="bloqueios.length ? 'Corrija as pendências acima antes de enviar' : ''"
                    @click="confirmSend">
              <i class="fas mr-1" :class="busy ? 'fa-spinner fa-spin' : 'fa-paper-plane'"></i>
              {{ avisos.length ? 'Enviar mesmo assim (incompleto)' : 'Confirmar envio ao eShip' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </span>
</template>

<script setup>
import { ref, computed } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'

const props = defineProps({ order: { type: Object, required: true } })
const emit = defineEmits(['updated'])
const toast = useToast()
const busy = ref(false)

// "Já enviado" não é só ter o código: o eShip pode aceitar a ordem sem devolver um id extraível.
// O backend manda `eship_enviada`; o fallback cobre payloads antigos em cache.
const enviada = computed(() => (
  props.order.eship_enviada
  ?? (!!props.order.eship_order_id || ['sent', 'partial'].includes(props.order.eship_dispatch_status))
))
const pendente = computed(() => !props.order.eship_nfe_attached || !props.order.eship_label_attached)

const showOrdem = ref(false)
const ordem = ref(null)
const showRaw = ref(false)

const STATUS = {
  sent: ['Enviado', 'badge-success'],
  partial: ['Parcial', 'badge-warning'],
  failed: ['Falhou', 'badge-danger'],
  sending: ['Em andamento', 'badge-secondary'],
  cancelled: ['Cancelado', 'badge-dark'],
}
const statusLabel = computed(() => STATUS[ordem.value?.dispatch_status]?.[0] || '—')
const statusClass = computed(() => STATUS[ordem.value?.dispatch_status]?.[1] || 'badge-light')
const rawPretty = computed(() => {
  const raw = ordem.value?.last_response
  if (!raw) return ''
  try { return JSON.stringify(JSON.parse(raw), null, 2) } catch { return String(raw) }
})

const anexos = ref([])
const anexosLoading = ref(false)
const anexosErro = ref('')

async function openOrdem() {
  if (busy.value) return
  ordem.value = null
  showRaw.value = false
  showOrdem.value = true
  try {
    const { data } = await api.get(`/integrations/eship/orders/${props.order.id}/eship-ordem`)
    ordem.value = data
  } catch (e) {
    showOrdem.value = false
    toast.error(e.response?.data?.detail || 'Erro ao carregar a ordem do eShip')
    return
  }
  loadAnexos()
}

// Consulta separada: bate no eShip (webServiceGetAnexosOrdem) e pode demorar — não segura o modal.
async function loadAnexos() {
  anexos.value = []
  anexosErro.value = ''
  anexosLoading.value = true
  try {
    const { data } = await api.get(`/integrations/eship/orders/${props.order.id}/eship-anexos`)
    anexos.value = data.anexos || []
  } catch (e) {
    anexosErro.value = e.response?.data?.detail || 'Não foi possível consultar os anexos no eShip'
  } finally {
    anexosLoading.value = false
  }
}

function closeOrdem() {
  showOrdem.value = false
}

// "Atualizar" reprocessa só o que faltou (o envio é idempotente: não recria a ordem no WMS)
// e depois puxa o status. Nada aqui pode duplicar a ordem.
async function atualizar() {
  closeOrdem()
  await doSend()
  await sync({ silentNoChange: true })
}

async function excluir() {
  if (!window.confirm(
    'Excluir esta ordem no eShip?\n\nA ordem é REMOVIDA do WMS (não apenas cancelada) — só assim o eShip '
    + 'libera o número do pedido e permite reenviá-lo com o mesmo número da venda.'
  )) return
  busy.value = true
  try {
    await api.post(`/integrations/eship/orders/${props.order.id}/cancel`)
    closeOrdem()
    toast.success('Ordem excluída do eShip — o pedido está liberado para novo envio')
    emit('updated')
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao cancelar a ordem no eShip')
  } finally {
    busy.value = false
  }
}

const showPreview = ref(false)
const preview = ref(null)
const bloqueios = computed(() => preview.value?.bloqueios || [])
const avisos = computed(() => preview.value?.avisos || [])
const bodyPretty = computed(() => {
  if (!preview.value?.body) return ''
  try { return JSON.stringify(preview.value.body, null, 2) } catch { return String(preview.value.body) }
})

async function openPreview() {
  if (busy.value) return
  preview.value = null
  showPreview.value = true
  try {
    const { data } = await api.get(`/integrations/eship/orders/${props.order.id}/preview-ordem`)
    preview.value = data
  } catch (e) {
    showPreview.value = false
    toast.error(e.response?.data?.detail || 'Erro ao montar a prévia do envio')
  }
}

function closePreview() {
  showPreview.value = false
}

async function copy(text, label) {
  try {
    await navigator.clipboard.writeText(String(text ?? ''))
    toast.success(`${label} copiado`)
  } catch {
    toast.warning('Não foi possível copiar automaticamente — selecione e copie manualmente')
  }
}

async function confirmSend() {
  // Enviar sem NF-e/etiqueta cria a ordem incompleta no WMS. É permitido (dá para completar depois
  // com "Atualizar"), mas nunca em silêncio — o usuário confirma sabendo o que falta.
  if (avisos.value.length) {
    const faltando = avisos.value.map((a) => `• ${a}`).join('\n')
    const ok = window.confirm(
      `Este pedido será enviado ao eShip INCOMPLETO:\n\n${faltando}\n\n`
      + 'A ordem será criada no WMS assim mesmo. Depois de emitir a NF-e / liberar a etiqueta, '
      + 'clique no pedido e use "Atualizar" para anexar o que faltou (a ordem não é recriada).\n\n'
      + 'Deseja enviar mesmo assim?'
    )
    if (!ok) return
  }
  closePreview()
  await doSend()
}

async function doSend() {
  busy.value = true
  try {
    const { data } = await api.post(`/integrations/eship/orders/${props.order.id}/send`)
    const erros = data.erros || []
    if (!erros.length) {
      toast.success('Enviado ao eShip: Ordem + NF-e + Etiqueta')
    } else {
      const feito = []
      if (data.eship_order_id) feito.push('Ordem')
      if (data.nfe_attached) feito.push('NF-e')
      if (data.label_attached) feito.push('Etiqueta')
      const pend = erros.map((e) => e.erro).join(' · ')
      toast.warning((feito.length ? `Enviado: ${feito.join(' + ')}. ` : '') + `Pendente: ${pend}`)
    }
    emit('updated')
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao enviar ao eShip')
  } finally {
    busy.value = false
  }
}

async function sync({ silentNoChange = false } = {}) {
  busy.value = true
  try {
    const { data } = await api.post(`/integrations/eship/orders/${props.order.id}/sync`)
    if (data.changed) {
      toast.success('Status atualizado pelo eShip')
      emit('updated')
    } else if (!silentNoChange) {
      toast.success('Sem mudança de status')
    }
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao sincronizar com eShip')
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.eship-preview-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, .5);
  z-index: 1080;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 4vh 12px;
  overflow: auto;
}
.eship-preview-card {
  width: 100%;
  max-width: 820px;
  margin: 0;
}
.eship-preview-pre {
  background: #1e1e1e;
  color: #d4d4d4;
  font-size: 12px;
  padding: 10px;
  border-radius: 4px;
  max-height: 320px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}
</style>
