// Nome de arquivo de download — fonte ÚNICA é o backend (header Content-Disposition).
// Como o download vira blob URL (que perde o header), lemos o Content-Disposition da
// resposta axios e usamos como `a.download`. Assim o padrão Tipo_venda_cliente definido
// no backend (services/file_naming.py) vale em toda a aplicação.

export function filenameFromContentDisposition(headers, fallback = 'arquivo') {
  const cd = (headers && (headers['content-disposition'] || headers['Content-Disposition'])) || ''
  // filename="..." ou filename*=UTF-8''...  (o backend emite ASCII puro)
  const m = /filename\*?=(?:UTF-8'')?["']?([^"';\r\n]+)/i.exec(cd)
  if (!m) return fallback
  const raw = m[1].trim()
  try { return decodeURIComponent(raw) || fallback } catch { return raw || fallback }
}

// Baixa uma resposta axios (responseType:'blob') usando o nome do Content-Disposition.
export function saveBlobResponse(resp, fallbackName, type) {
  const name = filenameFromContentDisposition(resp?.headers, fallbackName)
  const url = URL.createObjectURL(type ? new Blob([resp.data], { type }) : new Blob([resp.data]))
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  setTimeout(() => URL.revokeObjectURL(url), 60000)
  return name
}

// Abre o blob em nova aba (para imprimir) E baixa uma cópia já nomeada (Content-Disposition).
export function openAndSaveBlobResponse(resp, fallbackName, type) {
  const name = filenameFromContentDisposition(resp?.headers, fallbackName)
  const url = URL.createObjectURL(type ? new Blob([resp.data], { type }) : new Blob([resp.data]))
  window.open(url, '_blank')            // 1) abre para impressão
  const a = document.createElement('a') // 2) baixa cópia nomeada
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  setTimeout(() => URL.revokeObjectURL(url), 60000)
  return name
}

// Etiqueta em PDF + ZPL "de uma vez": abre o PDF para imprimir (quando open=true) e baixa
// AMBOS os arquivos já nomeados (o nome vem do Content-Disposition de cada resposta).
// Passe as respostas axios (responseType:'blob') dos dois formatos; qualquer uma pode faltar.
export function saveLabelBoth(pdfResp, zplResp, { open = true } = {}) {
  if (pdfResp) {
    if (open) openAndSaveBlobResponse(pdfResp, 'Etiqueta.pdf', 'application/pdf')
    else saveBlobResponse(pdfResp, 'Etiqueta.pdf', 'application/pdf')
  }
  if (zplResp) saveBlobResponse(zplResp, 'Etiqueta.zpl', 'text/plain')
}
