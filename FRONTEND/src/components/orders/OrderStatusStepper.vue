<template>
  <div class="order-stepper d-flex align-items-center overflow-auto py-2">
    <div
      v-for="(step, i) in steps"
      :key="step.key"
      class="d-flex align-items-center"
    >
      <div class="text-center" style="min-width:80px">
        <div
          class="step-circle mx-auto mb-1"
          :class="{
            'bg-success text-white': isPast(step.key) || isCurrent(step.key),
            'bg-secondary text-white': !isPast(step.key) && !isCurrent(step.key),
            'step-current': isCurrent(step.key),
          }"
        >
          <i :class="step.icon"></i>
        </div>
        <small :class="isCurrent(step.key) ? 'font-weight-bold text-success' : 'text-muted'">
          {{ step.label }}
        </small>
      </div>
      <div
        v-if="i < steps.length - 1"
        class="step-line flex-grow-1 mx-1"
        :class="isPast(steps[i + 1].key) || isCurrent(steps[i + 1].key) ? 'bg-success' : 'bg-secondary'"
        style="height:2px;min-width:20px"
      ></div>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  status: { type: String, required: true },
})

const steps = [
  { key: 'downloaded',      label: 'Baixado',     icon: 'fas fa-download' },
  { key: 'paid',            label: 'Pago',        icon: 'fas fa-dollar-sign' },
  { key: 'label_generated', label: 'Etiqueta',    icon: 'fas fa-tag' },
  { key: 'label_printed',   label: 'Impresso',    icon: 'fas fa-print' },
  { key: 'separated',       label: 'Separado',    icon: 'fas fa-box-open' },
  { key: 'shipped',         label: 'Enviado',     icon: 'fas fa-truck' },
]

const order = steps.map(s => s.key)

function isPast(key) {
  const cur = order.indexOf(props.status)
  const idx = order.indexOf(key)
  return idx !== -1 && cur !== -1 && idx < cur
}

function isCurrent(key) {
  return props.status === key
}
</script>

<style scoped>
.step-circle {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
}
.step-current {
  box-shadow: 0 0 0 3px rgba(40,167,69,.35);
}
</style>
