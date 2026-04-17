/**
 * Validate CPF (Cadastro de Pessoas Físicas)
 */
export function validateCPF(cpf) {
  const digits = cpf.replace(/\D/g, '')
  if (digits.length !== 11) return false
  if (/^(\d)\1+$/.test(digits)) return false

  let sum = 0
  for (let i = 0; i < 9; i++) sum += parseInt(digits[i]) * (10 - i)
  let check = (sum * 10) % 11
  if (check === 10 || check === 11) check = 0
  if (check !== parseInt(digits[9])) return false

  sum = 0
  for (let i = 0; i < 10; i++) sum += parseInt(digits[i]) * (11 - i)
  check = (sum * 10) % 11
  if (check === 10 || check === 11) check = 0
  return check === parseInt(digits[10])
}

/**
 * Validate CNPJ (Cadastro Nacional da Pessoa Jurídica)
 */
export function validateCNPJ(cnpj) {
  const digits = cnpj.replace(/\D/g, '')
  if (digits.length !== 14) return false
  if (/^(\d)\1+$/.test(digits)) return false

  const weights1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
  const weights2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]

  const calcDigit = (arr, weights) => {
    const sum = arr.reduce((acc, d, i) => acc + d * weights[i], 0)
    const rest = sum % 11
    return rest < 2 ? 0 : 11 - rest
  }

  const arr = digits.split('').map(Number)
  if (calcDigit(arr.slice(0, 12), weights1) !== arr[12]) return false
  if (calcDigit(arr.slice(0, 13), weights2) !== arr[13]) return false
  return true
}

/**
 * Validate email format
 */
export function validateEmail(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
}

/**
 * Validate Brazilian phone number
 */
export function validatePhone(phone) {
  return /^\(\d{2}\)\s\d{4,5}-\d{4}$/.test(phone)
}
