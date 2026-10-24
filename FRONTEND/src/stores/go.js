import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/composables/useApi'

// Store do autoatendimento "Minha Empresa" (o dono edita a própria empresa/galpão).
// O cadastro de dono (createGo) e a listagem (fetchGoes) foram aposentados junto com a tela
// "Gestores Operacionais" — o cadastro vive agora na tela Galpões (POST /warehouse com bloco owner).
export const useGoStore = defineStore('go', () => {
  const goes = ref([])

  async function updateGo(id, payload) {
    const { data } = await api.put(`/goes/${id}`, payload)
    const idx = goes.value.findIndex(g => g.id === id)
    if (idx !== -1) goes.value[idx] = data
    return data
  }

  return { goes, updateGo }
})
