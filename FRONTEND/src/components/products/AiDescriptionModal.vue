<template>
  <div v-if="visible" class="modal fade show d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
    <div class="modal-dialog modal-xl" role="document">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title">
            <i class="fas fa-robot text-success mr-2"></i>Gerar descrição por IA
          </h5>
          <button type="button" class="close" @click="voltar"><span>&times;</span></button>
        </div>

        <div class="modal-body">
          <!-- Componentes do KIT: copiar a descrição de cada um p/ colar no prompt (req. #3) -->
          <div v-if="components && components.length" class="card card-body bg-light py-2 mb-3">
            <div class="d-flex align-items-center flex-wrap">
              <small class="text-muted mr-2">
                <i class="fas fa-cubes mr-1"></i>Componentes do KIT — copiar descrição:
              </small>
              <button
                v-for="c in components"
                :key="c.product_id ?? c.component_id ?? c.sku"
                type="button"
                class="btn btn-sm btn-outline-secondary mr-1 mb-1"
                :title="`Copiar a descrição de ${c.title}`"
                @click="copy(c.description, `Descrição de ${c.sku || c.title} copiada!`)"
              >
                <i class="fas fa-copy mr-1"></i>{{ c.sku || c.title }}
              </button>
            </div>
          </div>

          <!-- Prompt -->
          <div class="form-group">
            <label class="mb-1">
              O que a IA deve escrever?
              <small class="text-muted">(descreva o produto, o tom, o público, o que destacar…)</small>
            </label>
            <textarea
              v-model="prompt"
              class="form-control w-100"
              rows="10"
              placeholder="Ex.: Escreva a descrição de um halter ajustável de 24kg, destacando o material, a regulagem de carga e o uso em treino em casa. Tom direto, com tópicos curtos."
            ></textarea>
          </div>

          <div class="d-flex align-items-center mb-3">
            <button class="btn btn-success" :disabled="loading || !prompt.trim()" @click="gerar">
              <i class="fas mr-1" :class="loading ? 'fa-spinner fa-spin' : 'fa-magic'"></i>
              {{ loading ? 'Gerando…' : (response ? 'Gerar novamente' : 'Gerar descrição') }}
            </button>

            <!-- Checkbox: reenviar a resposta como contexto do próximo prompt (req. #1) -->
            <div v-if="response" class="custom-control custom-checkbox ml-3">
              <input id="aiUseCtx" v-model="useContext" type="checkbox" class="custom-control-input">
              <label class="custom-control-label small" for="aiUseCtx">
                Usar a resposta abaixo como <strong>contexto</strong> do próximo prompt
              </label>
            </div>
          </div>

          <!-- Resposta da IA (EDITÁVEL) -->
          <div class="form-group mb-0">
            <label class="mb-1 d-flex align-items-center">
              <span>Resposta da IA <small class="text-muted">(pode editar antes de aplicar)</small></span>
              <span class="ml-auto small" :class="tooLong ? 'text-danger font-weight-bold' : 'text-muted'">
                {{ response.length }}<span v-if="maxChars"> / {{ maxChars }}</span> caracteres
              </span>
            </label>
            <textarea
              v-model="response"
              class="form-control w-100"
              rows="10"
              placeholder="A descrição gerada aparecerá aqui — e você pode ajustá-la antes de aplicar."
            ></textarea>
            <small v-if="tooLong" class="text-danger">
              <i class="fas fa-exclamation-triangle mr-1"></i>
              A descrição excede o limite de {{ maxChars }} caracteres do produto CMIG e seria
              cortada ao salvar. Reduza o texto.
            </small>
          </div>
        </div>

        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" @click="voltar">
            <i class="fas fa-arrow-left mr-1"></i>Voltar
          </button>
          <button
            type="button"
            class="btn btn-primary"
            :disabled="!response.trim() || tooLong"
            title="Substitui a descrição do produto pelo texto acima"
            @click="pronto"
          >
            <i class="fas fa-check mr-1"></i>Pronto
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { useClipboard } from '@/composables/useClipboard'

const props = defineProps({
  visible: { type: Boolean, default: false },
  productType: { type: String, default: null },   // 'cmig' | 'pg'
  productId: { type: [Number, String], default: null },
  components: { type: Array, default: () => [] }, // só nos KITs
})
const emit = defineEmits(['close', 'apply'])

const toast = useToast()
const { copy } = useClipboard()

const prompt = ref('')
const response = ref('')
const useContext = ref(false)
const loading = ref(false)

// CMIGProduct.description é VARCHAR(4000); o PG é CLOB (sem limite).
const maxChars = computed(() => (props.productType === 'cmig' ? 4000 : 0))
const tooLong = computed(() => !!maxChars.value && response.value.length > maxChars.value)

// Ao reabrir o modal, começa limpo (não carrega resíduo da sessão anterior).
watch(() => props.visible, (v) => {
  if (v) { prompt.value = ''; response.value = ''; useContext.value = false }
})

async function gerar() {
  loading.value = true
  try {
    const { data } = await api.post('/ai/product-description', {
      prompt: prompt.value,
      // Só manda a resposta anterior quando o usuário pediu (o checkbox).
      previous_response: useContext.value ? response.value : null,
      product_type: props.productType,
      product_id: props.productId || null,
    })
    response.value = data.description || ''
    if (!response.value) toast.warning('A IA não retornou texto. Tente reformular o prompt.')
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao gerar a descrição com a IA.')
  } finally {
    loading.value = false
  }
}

// Voltar: NÃO carrega nada — a descrição do produto fica como estava.
function voltar() {
  emit('close')
}

// Pronto: substitui a descrição do produto pela resposta (já editada, se for o caso).
function pronto() {
  emit('apply', response.value.trim())
  emit('close')
}
</script>
