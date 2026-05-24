// Utilitários de EAN-13.
//
// Prefixo 789 = código de país atribuído pela GS1 ao Brasil. Gera EANs no
// formato "público" usado em produtos comerciais reais (ex.: 7896585254999).
// Atenção: prefixos 789/790 oficialmente pertencem à GS1 Brasil e só devem
// ser usados por empresas associadas — manter ciente do risco regulatório.

const INTERNAL_PREFIX = '789'

/** Calcula o dígito verificador do EAN-13 (mod 10 ponderado 1/3). */
export function ean13Checksum(first12) {
  if (first12.length !== 12 || !/^\d{12}$/.test(first12)) {
    throw new Error('EAN-13: primeiros 12 dígitos devem ser numéricos')
  }
  let sum = 0
  for (let i = 0; i < 12; i++) {
    const d = Number(first12[i])
    sum += i % 2 === 0 ? d : d * 3
  }
  return (10 - (sum % 10)) % 10
}

/** Gera um EAN-13 com prefixo interno 200 + 9 dígitos aleatórios + checksum. */
export function generateEan13() {
  let body = INTERNAL_PREFIX
  for (let i = 0; i < 9; i++) {
    body += Math.floor(Math.random() * 10).toString()
  }
  return body + ean13Checksum(body).toString()
}

/** True se a string é um EAN-13 válido (13 dígitos + checksum correto). */
export function isValidEan13(s) {
  if (!s || typeof s !== 'string') return false
  if (!/^\d{13}$/.test(s)) return false
  return ean13Checksum(s.substring(0, 12)) === Number(s[12])
}
