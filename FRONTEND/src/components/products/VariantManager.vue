<template>
  <div>
    <div class="d-flex justify-content-between align-items-center mb-2">
      <strong>Variantes</strong>
      <button type="button" class="btn btn-xs btn-outline-primary" @click="addVariant">
        <i class="fas fa-plus mr-1"></i> Adicionar
      </button>
    </div>

    <div v-if="!modelValue.length" class="text-muted small py-2">
      Nenhuma variante cadastrada. O produto será vendido sem variação.
    </div>

    <table v-else class="table table-sm table-bordered">
      <thead>
        <tr>
          <th>Cor</th>
          <th>Tamanho</th>
          <th>SKU</th>
          <th>Estoque</th>
          <th>Preço Extra (R$)</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(v, i) in modelValue" :key="i">
          <td>
            <input v-model="v.color" type="text" class="form-control form-control-sm" placeholder="Azul" />
          </td>
          <td>
            <input v-model="v.size" type="text" class="form-control form-control-sm" placeholder="M" />
          </td>
          <td>
            <input v-model="v.sku_suffix" type="text" class="form-control form-control-sm" placeholder="-AZM" />
          </td>
          <td>
            <input v-model.number="v.stock_quantity" type="number" min="0" class="form-control form-control-sm" style="width:70px" />
          </td>
          <td>
            <input v-model.number="v.price_delta" type="number" step="0.01" class="form-control form-control-sm" style="width:90px" />
          </td>
          <td>
            <button type="button" class="btn btn-xs btn-outline-danger" @click="remove(i)">
              <i class="fas fa-trash"></i>
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
const props = defineProps({
  modelValue: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:modelValue'])

function addVariant() {
  emit('update:modelValue', [
    ...props.modelValue,
    { color: '', size: '', sku_suffix: '', stock_quantity: 0, price_delta: 0 },
  ])
}

function remove(i) {
  const list = [...props.modelValue]
  list.splice(i, 1)
  emit('update:modelValue', list)
}
</script>
