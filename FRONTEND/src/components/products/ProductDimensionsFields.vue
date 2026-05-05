<template>
  <div>
    <hr />
    <h6 class="text-muted text-uppercase mb-3"><small>Dimensões e Peso</small></h6>
    <div class="row">
      <div class="col-md-3 form-group">
        <label>Peso (kg)</label>
        <input v-model="form.weight_kg" type="number" step="0.001" class="form-control" />
      </div>
      <div class="col-md-3 form-group">
        <label>Altura (cm)</label>
        <input v-model="form.height_cm" type="number" step="0.01" class="form-control" />
      </div>
      <div class="col-md-3 form-group">
        <label>Largura (cm)</label>
        <input v-model="form.width_cm" type="number" step="0.01" class="form-control" />
      </div>
      <div class="col-md-3 form-group">
        <label>Comprimento (cm)</label>
        <input v-model="form.length_cm" type="number" step="0.01" class="form-control" />
      </div>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  form: { type: Object, required: true },
})
</script>
