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

// ── Data/hora — FONTE ÚNICA (horário local do Brasil) ───────────────────────
// Política: o backend guarda/transporta em UTC (ISO com offset). A conversão para
// o horário local do Brasil acontece SEMPRE aqui, com timeZone fixo, independente
// do fuso do navegador. Use estas funções em TODA exibição/cálculo/filtro de data.
export const BR_TZ = 'America/Sao_Paulo'
const _RE_DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/
const _RE_HAS_TZ = /(Z|[+-]\d{2}:?\d{2})$/

/**
 * Converte qualquer entrada (Date | epoch | string ISO) em um Date (ou null).
 * - "YYYY-MM-DD" (só-data): dia-calendário literal (não converte fuso → sem off-by-one).
 * - datetime COM offset/Z: instante absoluto.
 * - datetime SEM offset (naive): tratado como UTC (o backend guarda UTC).
 */
export function parseDate(input) {
  if (input === null || input === undefined || input === '') return null
  if (input instanceof Date) return isNaN(input.getTime()) ? null : input
  if (typeof input === 'number') { const d = new Date(input); return isNaN(d.getTime()) ? null : d }
  let s = String(input).trim()
  if (!s) return null
  if (_RE_DATE_ONLY.test(s)) {
    const d = new Date(s + 'T12:00:00')        // dia literal (meio-dia local)
    return isNaN(d.getTime()) ? null : d
  }
  s = s.replace(' ', 'T')
  if (s.includes('T') && !_RE_HAS_TZ.test(s)) s += 'Z'  // naive → UTC
  const d = new Date(s)
  return isNaN(d.getTime()) ? null : d
}

/** Formata para dd/MM/aaaa (horário do Brasil). Só-data é exibida literal. */
export function formatDate(input) {
  const s = input == null ? '' : String(input).trim()
  if (_RE_DATE_ONLY.test(s)) { const [y, m, d] = s.split('-'); return `${d}/${m}/${y}` }
  const d = parseDate(input)
  return d ? new Intl.DateTimeFormat('pt-BR', {
    timeZone: BR_TZ, day: '2-digit', month: '2-digit', year: 'numeric',
  }).format(d) : '—'
}

/** Formata para dd/MM/aaaa HH:mm (horário do Brasil). */
export function formatDateTime(input) {
  const s = input == null ? '' : String(input).trim()
  if (_RE_DATE_ONLY.test(s)) return formatDate(s)   // sem hora
  const d = parseDate(input)
  return d ? new Intl.DateTimeFormat('pt-BR', {
    timeZone: BR_TZ, day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  }).format(d) : '—'
}

/** Formata só a hora HH:mm (horário do Brasil). */
export function formatTime(input) {
  const d = parseDate(input)
  return d ? new Intl.DateTimeFormat('pt-BR', {
    timeZone: BR_TZ, hour: '2-digit', minute: '2-digit',
  }).format(d) : '—'
}

/** "Hoje" no fuso do Brasil como "YYYY-MM-DD" (não usa toISOString=UTC). */
export function brToday() { return brDateISO(new Date()) }
/** "YYYY-MM-DD" de N dias atrás no fuso do Brasil. */
export function brDaysAgo(days) {
  const d = new Date(); d.setDate(d.getDate() - Number(days || 0))
  return brDateISO(d)
}
function brDateISO(date) {
  // en-CA formata como YYYY-MM-DD; timeZone garante o dia-calendário do Brasil.
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: BR_TZ, year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(date)
}

/** Converte "YYYY-MM-DDTHH:mm" (entendido como horário do BRASIL) → ISO UTC p/ enviar ao backend. */
export function brInputToUtcIso(localStr) {
  if (!localStr) return null
  const d = new Date(String(localStr).length === 16 ? localStr + ':00-03:00' : localStr + '-03:00')
  return isNaN(d.getTime()) ? null : d.toISOString()
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
