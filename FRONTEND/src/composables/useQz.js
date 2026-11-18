// Integração com o QZ Tray (agente local de impressão) — envia ZPL cru e PDF direto p/ a impressora
// escolhida, sem caixa de diálogo. O QZ roda no PC de despacho (wss://localhost). Fase 1: conexão
// NÃO assinada (o QZ mostra "permitir" uma vez; marque "lembrar" → silencioso). Assinatura via
// certificado (silêncio desde o 1º print) = Fase 2.
//
// LGPD: NUNCA logar o payload (ZPL/base64 da etiqueta/DANFE levam dados do comprador).
import { ref } from 'vue'

import qz from 'qz-tray'

const connected = ref(false)
const printers = ref([])
let connecting = null

async function connect() {
  try {
    if (qz.websocket.isActive()) { connected.value = true; return true }
  } catch { /* ignore */ }
  if (connecting) return connecting
  connecting = qz.websocket.connect({ retries: 1, delay: 1 })
    .then(() => { connected.value = true; return true })
    .catch(() => { connected.value = false; return false })
    .finally(() => { connecting = null })
  return connecting
}

async function listPrinters() {
  if (!await connect()) return []
  try { printers.value = await qz.printers.find(); return printers.value }
  catch { return [] }
}

async function printRaw(printer, data) {
  if (!printer) throw new Error('Impressora não definida')
  if (!await connect()) throw new Error('QZ Tray não conectado — abra o QZ Tray no PC de despacho')
  const cfg = qz.configs.create(printer)
  await qz.print(cfg, [{ type: 'raw', format: 'command', flavor: 'plain', data }])
}

async function printPdfBase64(printer, base64, size = 'a4') {
  if (!printer) throw new Error('Impressora não definida')
  if (!await connect()) throw new Error('QZ Tray não conectado — abra o QZ Tray no PC de despacho')
  const opts = size === '10x15'
    ? { size: { width: 10, height: 15 }, units: 'cm', scaleContent: true, rasterize: false }
    : { size: { width: 21, height: 29.7 }, units: 'cm', scaleContent: true, rasterize: false }
  const cfg = qz.configs.create(printer, opts)
  await qz.print(cfg, [{ type: 'pixel', format: 'pdf', flavor: 'base64', data: base64 }])
}

async function printHtml(printer, html, size = 'a4') {
  if (!printer) throw new Error('Impressora não definida')
  if (!await connect()) throw new Error('QZ Tray não conectado — abra o QZ Tray no PC de despacho')
  const opts = size === '10x15'
    ? { size: { width: 10, height: 15 }, units: 'cm', scaleContent: true }
    : { size: { width: 21, height: 29.7 }, units: 'cm', scaleContent: true }
  const cfg = qz.configs.create(printer, opts)
  await qz.print(cfg, [{ type: 'pixel', format: 'html', flavor: 'plain', data: html }])
}

function disconnect() {
  try { if (qz.websocket.isActive()) qz.websocket.disconnect() } catch { /* ignore */ }
  connected.value = false
}

function isActive() {
  try { return qz.websocket.isActive() } catch { return false }
}

export function useQz() {
  return { connected, printers, connect, listPrinters, printRaw, printPdfBase64, printHtml, disconnect, isActive }
}
