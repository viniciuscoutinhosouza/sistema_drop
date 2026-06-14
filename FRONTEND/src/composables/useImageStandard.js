/**
 * Validação e correção (canvas) de imagens contra o padrão de um marketplace.
 * Crop e borda são feitos no browser (sem custo); o outpaint por IA é feito no
 * backend (/media/ai-edit). Usado pelo ImageCorrectionModal.
 */

const IMG_FORMATS = { 'image/jpeg': 'JPG', 'image/png': 'PNG', 'image/webp': 'WEBP', 'image/gif': 'GIF' }

export function parseAspect(aspect) {
  // "1:1" / "9:16" -> {w, h}. Se vier intervalo ("1:1 a 16:9"), usa o primeiro.
  const m = String(aspect || '1:1').match(/(\d+)\s*:\s*(\d+)/)
  if (!m) return { w: 1, h: 1 }
  return { w: Number(m[1]) || 1, h: Number(m[2]) || 1 }
}

function loadImage(file) {
  return new Promise((resolve, reject) => {
    const img = new Image()
    const url = URL.createObjectURL(file)
    img.onload = () => resolve(img)
    img.onerror = (e) => { URL.revokeObjectURL(url); reject(e) }  // evita leak no erro
    img.src = url
  })
}

/** Lê dimensões/formato/tamanho e compara com o spec. Retorna issues[]. */
export async function validateImage(file, spec) {
  const img = await loadImage(file)
  const width = img.naturalWidth
  const height = img.naturalHeight
  const sizeMB = file.size / (1024 * 1024)
  const format = IMG_FORMATS[file.type] || (file.type || '').toUpperCase()
  const issues = []

  const { w: aw, h: ah } = parseAspect(spec?.aspect)
  const targetRatio = aw / ah
  const ratio = width / height
  if (Math.abs(ratio - targetRatio) > 0.02) {
    issues.push(`Proporção ${ratio.toFixed(2)} difere do padrão ${spec?.aspect || '1:1'}`)
  }
  if (spec?.min_px && Math.min(width, height) < spec.min_px) {
    issues.push(`Menor lado ${Math.min(width, height)}px < mínimo ${spec.min_px}px`)
  }
  if (spec?.max_mb && sizeMB > spec.max_mb) {
    issues.push(`Tamanho ${sizeMB.toFixed(1)}MB > máximo ${spec.max_mb}MB`)
  }
  if (spec?.formats?.length && format && !spec.formats.map(f => f.toUpperCase()).includes(format)) {
    issues.push(`Formato ${format} fora do padrão (${spec.formats.join(', ')})`)
  }

  URL.revokeObjectURL(img.src)
  return { ok: issues.length === 0, width, height, sizeMB, format, ratio, issues }
}

function _targetSize(aw, ah, recPx) {
  const long = recPx && recPx > 0 ? recPx : 1200
  return aw >= ah ? { tw: long, th: Math.round(long * ah / aw) } : { tw: Math.round(long * aw / ah), th: long }
}

/** Center-crop para a proporção alvo + resize. Retorna Blob (JPEG). */
export async function cropToAspect(file, aw, ah, recPx) {
  const img = await loadImage(file)
  const { tw, th } = _targetSize(aw, ah, recPx)
  const targetRatio = tw / th
  const srcRatio = img.naturalWidth / img.naturalHeight
  let sx, sy, sw, sh
  if (srcRatio > targetRatio) {
    sh = img.naturalHeight; sw = sh * targetRatio; sx = (img.naturalWidth - sw) / 2; sy = 0
  } else {
    sw = img.naturalWidth; sh = sw / targetRatio; sx = 0; sy = (img.naturalHeight - sh) / 2
  }
  const canvas = document.createElement('canvas')
  canvas.width = tw; canvas.height = th
  canvas.getContext('2d').drawImage(img, sx, sy, sw, sh, 0, 0, tw, th)
  URL.revokeObjectURL(img.src)
  return _toBlob(canvas, 'image/jpeg', 0.92)
}

/** Letterbox: encaixa a imagem inteira no alvo com borda (sem cortar). Retorna Blob. */
export async function padToAspect(file, aw, ah, recPx, bg = '#ffffff') {
  const img = await loadImage(file)
  const { tw, th } = _targetSize(aw, ah, recPx)
  const canvas = document.createElement('canvas')
  canvas.width = tw; canvas.height = th
  const ctx = canvas.getContext('2d')
  ctx.fillStyle = bg
  ctx.fillRect(0, 0, tw, th)
  const scale = Math.min(tw / img.naturalWidth, th / img.naturalHeight)
  const dw = img.naturalWidth * scale, dh = img.naturalHeight * scale
  ctx.drawImage(img, (tw - dw) / 2, (th - dh) / 2, dw, dh)
  URL.revokeObjectURL(img.src)
  return _toBlob(canvas, 'image/jpeg', 0.92)
}

function _toBlob(canvas, type, quality) {
  return new Promise((resolve) => canvas.toBlob(b => resolve(b), type, quality))
}
