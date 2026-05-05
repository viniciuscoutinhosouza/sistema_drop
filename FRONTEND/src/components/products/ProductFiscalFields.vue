<template>
  <div>
    <hr />
    <h6 class="text-muted text-uppercase mb-3"><small>Informações Fiscais</small></h6>
    <div class="row">
      <div class="col-md-4 form-group">
        <label>NCM</label>
        <input v-model="form.ncm" class="form-control" maxlength="8" placeholder="00000000" />
      </div>
      <div class="col-md-4 form-group">
        <label>CEST</label>
        <input v-model="form.cest" class="form-control" maxlength="7" placeholder="0000000" />
      </div>
      <div class="col-md-4 form-group">
        <label>Origem</label>
        <select v-model="form.origin" class="form-control">
          <option :value="0">0 - Nacional</option>
          <option :value="1">1 - Estrangeira (Importação Direta)</option>
          <option :value="2">2 - Estrangeira (Mercado Interno)</option>
        </select>
      </div>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  form: { type: Object, required: true },
})
</script>
