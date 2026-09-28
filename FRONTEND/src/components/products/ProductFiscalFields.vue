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

    <!-- Rastreabilidade (ADR-0027): lote / validade / serial / medicamento -->
    <hr />
    <h6 class="text-muted text-uppercase mb-2"><small>Rastreabilidade</small></h6>
    <div class="alert alert-warning py-2 px-3 small" v-if="isTraceable">
      <i class="fas fa-exclamation-triangle"></i>
      Produto rastreável: a NF-e será emitida <strong>pelo próprio sistema</strong> (nunca pelo Faturador ML/Shopee)
      e o produto <strong>não vai ao FULL</strong>.
    </div>
    <div class="row">
      <div class="col-md-4 form-group">
        <div class="custom-control custom-switch">
          <input type="checkbox" class="custom-control-input" id="trk_lot" v-model="form.track_lot" />
          <label class="custom-control-label" for="trk_lot">Rastrear por <strong>Lote</strong></label>
        </div>
      </div>
      <div class="col-md-4 form-group">
        <div class="custom-control custom-switch">
          <input type="checkbox" class="custom-control-input" id="trk_exp" v-model="form.track_expiry" />
          <label class="custom-control-label" for="trk_exp">Rastrear por <strong>Validade</strong></label>
        </div>
      </div>
      <div class="col-md-4 form-group">
        <div class="custom-control custom-switch">
          <input type="checkbox" class="custom-control-input" id="trk_ser" v-model="form.track_serial" />
          <label class="custom-control-label" for="trk_ser">Rastrear por <strong>Nº Serial</strong></label>
        </div>
      </div>
    </div>
    <div class="row" v-if="isTraceable">
      <div class="col-12"><small class="text-muted d-block mb-2">Medicamento (grupo &lt;med&gt; da NF-e — preencha só se for medicamento):</small></div>
      <div class="col-md-4 form-group">
        <label>Código ANVISA</label>
        <input v-model="form.med_anvisa_code" class="form-control" maxlength="13" placeholder="13 dígitos ou ISENTO" />
      </div>
      <div class="col-md-4 form-group">
        <label>PMC (Preço Máx. Consumidor)</label>
        <input v-model="form.med_pmc" type="number" step="0.01" min="0" class="form-control" placeholder="0,00" />
      </div>
      <div class="col-md-4 form-group" v-if="(form.med_anvisa_code || '').toUpperCase() === 'ISENTO'">
        <label>Motivo da Isenção</label>
        <input v-model="form.med_exempt_reason" class="form-control" maxlength="255" />
      </div>
    </div>
    <small class="text-muted" v-if="form.med_anvisa_code && !form.track_lot">
      <i class="fas fa-info-circle"></i> Medicamento exige rastreio por Lote — ligue "Rastrear por Lote".
    </small>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  form: { type: Object, required: true },
})

const isTraceable = computed(() =>
  !!(props.form.track_lot || props.form.track_expiry || props.form.track_serial || props.form.med_anvisa_code)
)
</script>
