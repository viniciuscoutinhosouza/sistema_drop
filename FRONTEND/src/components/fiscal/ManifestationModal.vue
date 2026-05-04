<template>
  <div class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
    <div class="modal-dialog modal-lg">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title"><i class="fas fa-flag mr-2"></i>Manifestação do Destinatário</h5>
          <button type="button" class="close" @click="$emit('close')"><span>&times;</span></button>
        </div>

        <div class="modal-body">
          <p class="text-muted small">
            Selecione o tipo de manifestação para esta NFe recebida.
            <strong>Os prazos legais são contados a partir da autorização da NFe.</strong>
          </p>

          <div class="row">
            <div class="col-md-6 mb-2" v-for="opt in options" :key="opt.value">
              <div class="card h-100" :class="{'border-primary': selected === opt.value}"
                   style="cursor:pointer" @click="selected = opt.value">
                <div class="card-body p-3">
                  <h6 class="mb-1">
                    <i :class="opt.icon" class="mr-1"></i>{{ opt.label }}
                    <small v-if="opt.deadline" class="text-muted">({{ opt.deadline }})</small>
                  </h6>
                  <p class="small text-muted mb-0">{{ opt.description }}</p>
                </div>
              </div>
            </div>
          </div>

          <!-- Justificativa (obrigatória para Desconhecimento e Não Realizada) -->
          <div v-if="needsJustification" class="form-group mt-3">
            <label class="small">
              Justificativa <span class="text-danger">*</span>
              <small class="text-muted">(15 a 255 caracteres)</small>
            </label>
            <textarea v-model="justificativa" class="form-control" rows="3"
                      maxlength="255" placeholder="Descreva o motivo..."></textarea>
            <small class="text-muted">{{ justificativa.length }} / 255</small>
          </div>

          <!-- Atualizar estoque (apenas em Confirmação) -->
          <div v-if="selected === 'confirmacao' && !invoice.stock_updated" class="form-check mt-3">
            <input id="chk-update-stock-manifest" type="checkbox" class="form-check-input"
                   v-model="updateStock">
            <label for="chk-update-stock-manifest" class="form-check-label">
              Atualizar estoque dos produtos CMIG (match por EAN)
            </label>
          </div>

          <div v-if="error" class="alert alert-danger mt-3 small">{{ error }}</div>
          <div v-if="result" class="alert alert-success mt-3 small">
            <i class="fas fa-check-circle mr-1"></i>
            <strong>Manifestação registrada!</strong>
            <span v-if="result.protocol" class="d-block">Protocolo: {{ result.protocol }}</span>
            <span v-if="result.stock_update" class="d-block">
              Estoque: {{ result.stock_update.matched }} produtos atualizados,
              {{ result.stock_update.unmatched }} sem match
            </span>
          </div>
        </div>

        <div class="modal-footer">
          <button class="btn btn-secondary" @click="$emit('close')">{{ result ? 'Fechar' : 'Cancelar' }}</button>
          <button v-if="!result" class="btn btn-primary" :disabled="!canSubmit" @click="submit">
            <i class="fas" :class="submitting ? 'fa-spinner fa-spin' : 'fa-paper-plane'"></i>
            {{ submitting ? 'Enviando...' : 'Confirmar Manifestação' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useFiscalStore } from '@/stores/fiscal'

const props = defineProps({
  invoice: { type: Object, required: true },
})
const emit = defineEmits(['close', 'manifested'])
const fiscalStore = useFiscalStore()

const options = [
  {
    value: 'ciencia',
    label: 'Ciência da Operação',
    icon: 'fas fa-eye text-info',
    deadline: '10 dias',
    description: 'Acabei de saber, ainda vou avaliar a operação.',
  },
  {
    value: 'confirmacao',
    label: 'Confirmação da Operação',
    icon: 'fas fa-check-circle text-success',
    deadline: '180 dias',
    description: 'Mercadoria recebida e operação aceita.',
  },
  {
    value: 'desconhecimento',
    label: 'Desconhecimento',
    icon: 'fas fa-question-circle text-dark',
    deadline: '10 dias',
    description: 'Não reconheço esta NFe (CNPJ usado indevidamente).',
  },
  {
    value: 'nao_realizada',
    label: 'Operação Não Realizada',
    icon: 'fas fa-times-circle text-warning',
    deadline: '10 dias',
    description: 'NFe legítima mas a mercadoria não chegou ou foi devolvida.',
  },
]

const selected = ref('')
const justificativa = ref('')
const updateStock = ref(false)
const submitting = ref(false)
const error = ref('')
const result = ref(null)

const needsJustification = computed(() =>
  selected.value === 'desconhecimento' || selected.value === 'nao_realizada'
)

const canSubmit = computed(() => {
  if (!selected.value || submitting.value) return false
  if (needsJustification.value) {
    return justificativa.value.length >= 15 && justificativa.value.length <= 255
  }
  return true
})

async function submit() {
  submitting.value = true
  error.value = ''
  try {
    const payload = { type: selected.value }
    if (needsJustification.value) payload.justificativa = justificativa.value
    if (selected.value === 'confirmacao' && updateStock.value) payload.update_stock = true

    result.value = await fiscalStore.manifest(props.invoice.id, payload)
    emit('manifested', result.value)
  } catch (e) {
    error.value = e.response?.data?.detail || 'Erro ao manifestar'
  } finally {
    submitting.value = false
  }
}
</script>
