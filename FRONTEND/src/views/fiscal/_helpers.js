export const fmt = {
  date(iso) {
    if (!iso) return '—'
    const d = new Date(iso)
    return d.toLocaleDateString('pt-BR')
  },

  datetime(iso) {
    if (!iso) return '—'
    const d = new Date(iso)
    return d.toLocaleString('pt-BR')
  },

  currency(v) {
    if (v === null || v === undefined) return '—'
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(Number(v))
  },

  purpose(p) {
    const map = {
      venda: 'Venda',
      devolucao: 'Devolução',
      remessa: 'Simples Remessa',
      retorno: 'Retorno',
      transferencia: 'Transferência',
      complementar: 'Complementar',
      ajuste: 'Ajuste',
      outros: 'Outros',
    }
    return map[p] || p || '—'
  },

  statusLabel(s) {
    const map = {
      draft: 'Rascunho',
      queued: 'Em fila',
      pending: 'Pendente',
      processing: 'Processando',
      authorized: 'Autorizada',
      finalized: 'Finalizada (sem SEFAZ)',
      rejected: 'Rejeitada',
      cancelled: 'Cancelada',
      denied: 'Denegada',
    }
    return map[s] || s || '—'
  },

  statusClass(s) {
    const map = {
      draft: 'badge-secondary',
      queued: 'badge-info',
      pending: 'badge-warning',
      processing: 'badge-info',
      authorized: 'badge-success',
      finalized: 'badge-primary',
      rejected: 'badge-danger',
      cancelled: 'badge-warning',
      denied: 'badge-dark',
    }
    return map[s] || 'badge-light'
  },

  manifestation(m) {
    const map = {
      pending: 'Pendente',
      ciencia: 'Ciência',
      confirmacao: 'Confirmação',
      desconhecimento: 'Desconhecimento',
      nao_realizada: 'Não Realizada',
      not_required: '—',
    }
    return map[m] || '—'
  },

  manifestationClass(m) {
    const map = {
      pending: 'badge-danger',
      ciencia: 'badge-info',
      confirmacao: 'badge-success',
      desconhecimento: 'badge-dark',
      nao_realizada: 'badge-warning',
      not_required: 'badge-light',
    }
    return map[m] || 'badge-light'
  },

  inboundSource(s) {
    const map = {
      xml_upload: 'Upload XML',
      manual: 'Manual',
      dfe_focus: 'DFe Focus',
    }
    return map[s] || '—'
  },

  formatDoc(doc, type) {
    if (!doc) return ''
    const d = String(doc).replace(/\D/g, '')
    if ((type === 'PJ' || d.length === 14) && d.length === 14) {
      return `${d.slice(0,2)}.${d.slice(2,5)}.${d.slice(5,8)}/${d.slice(8,12)}-${d.slice(12)}`
    }
    if ((type === 'PF' || d.length === 11) && d.length === 11) {
      return `${d.slice(0,3)}.${d.slice(3,6)}.${d.slice(6,9)}-${d.slice(9)}`
    }
    return d
  },
}
