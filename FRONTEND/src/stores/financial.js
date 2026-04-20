import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/composables/useApi'

export const useFinancialStore = defineStore('financial', () => {
  const balance = ref(0)
  const balanceReserved = ref(0)

  async function fetchBalance() {
    try {
      const { data } = await api.get('/financial/balance')
      balance.value = data.balance
      balanceReserved.value = data.balance_reserved
    } catch {
      // Silencia erros (ex: usuário sem perfil ainda cadastrado)
    }
  }

  return { balance, balanceReserved, fetchBalance }
})
