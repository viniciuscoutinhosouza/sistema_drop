/**
 * Format a number as Brazilian Real currency
 */
export function formatCurrency(value) {
  if (value === null || value === undefined) return 'R$ 0,00'
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
  }).format(Number(value))
}

/**
 * Format an ISO date string to dd/MM/yyyy HH:mm
 */
export function formatDateTime(isoString) {
  if (!isoString) return ''
  const d = new Date(isoString)
  return d.toLocaleDateString('pt-BR') + ' ' + d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
}

/**
 * Format an ISO date string to dd/MM/yyyy
 */
export function formatDate(isoString) {
  if (!isoString) return ''
  const d = new Date(isoString)
  return d.toLocaleDateString('pt-BR')
}

/**
 * Apply CPF mask: 000.000.000-00
 */
export function maskCPF(value) {
  const v = value.replace(/\D/g, '').slice(0, 11)
  return v.replace(/(\d{3})(\d)/, '$1.$2')
          .replace(/(\d{3})(\d)/, '$1.$2')
          .replace(/(\d{3})(\d{1,2})$/, '$1-$2')
}

/**
 * Apply CNPJ mask: 00.000.000/0000-00
 */
export function maskCNPJ(value) {
  const v = value.replace(/\D/g, '').slice(0, 14)
  return v.replace(/(\d{2})(\d)/, '$1.$2')
          .replace(/(\d{3})(\d)/, '$1.$2')
          .replace(/(\d{3})(\d)/, '$1/$2')
          .replace(/(\d{4})(\d{1,2})$/, '$1-$2')
}

/**
 * Apply phone mask: (00) 00000-0000
 */
export function maskPhone(value) {
  const v = value.replace(/\D/g, '').slice(0, 11)
  return v.replace(/(\d{2})(\d)/, '($1) $2')
          .replace(/(\d{5})(\d{1,4})$/, '$1-$2')
}

/**
 * Apply CEP mask: 00000-000
 */
export function maskCEP(value) {
  const v = value.replace(/\D/g, '').slice(0, 8)
  return v.replace(/(\d{5})(\d{1,3})$/, '$1-$2')
}

/**
 * Format CPF or CNPJ based on length
 */
export function formatDocument(value) {
  if (!value) return ''
  const digits = value.replace(/\D/g, '')
  return digits.length <= 11 ? maskCPF(digits) : maskCNPJ(digits)
}
