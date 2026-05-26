<template>
  <div>
    <hr />
    <h6 class="text-muted text-uppercase mb-3"><small>Informações Fiscais</small></h6>
    <div class="row">
      <div class="col-md-4 form-group">
        <label>NCM</label>
        <input v-model="form.ncm" class="form-control" maxlength="10" placeholder="0000.00.00" />
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
    <div class="row">
      <div class="col-md-6 form-group">
        <label>CSOSN do ICMS <small class="text-muted">(Simples Nacional)</small></label>
        <select v-model="form.csosn" class="form-control">
          <option :value="null">— Default da CMIG (102 se Simples) —</option>
          <option value="101">101 - Tributada com permissão de crédito</option>
          <option value="102">102 - Tributada sem permissão de crédito</option>
          <option value="103">103 - Isenção do ICMS para faixa de receita bruta</option>
          <option value="201">201 - Tributada com permissão e ICMS-ST</option>
          <option value="202">202 - Tributada sem permissão e ICMS-ST</option>
          <option value="203">203 - Isenção para faixa receita bruta e ICMS-ST</option>
          <option value="300">300 - Imune</option>
          <option value="400">400 - Não tributada pelo Simples Nacional</option>
          <option value="500">500 - ICMS cobrado anteriormente por ST ou antecipação</option>
          <option value="900">900 - Outros</option>
        </select>
        <small class="text-muted">Obrigatório no Faturador ML. Em branco usa "102" se a CMIG é Simples Nacional.</small>
      </div>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  form: { type: Object, required: true },
})
</script>
