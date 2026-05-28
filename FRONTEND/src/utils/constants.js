export const ORDER_STATUSES = [
  { key: 'downloaded',      label: 'Baixou Pedido',     color: 'secondary' },
  { key: 'paid',            label: 'Pedido Pago',       color: 'info' },
  { key: 'label_generated', label: 'Etiqueta Gerada',   color: 'primary' },
  { key: 'label_printed',   label: 'Etiqueta Impressa', color: 'warning' },
  { key: 'separated',       label: 'Pedido Separado',   color: 'dark' },
  { key: 'shipped',         label: 'Pedido Enviado',    color: 'success' },
  { key: 'cancelled',       label: 'Cancelado',         color: 'danger' },
  { key: 'returned',        label: 'Devolvido',         color: 'danger' },
]

// =============================================================================
// SHIPPING MODE — paleta canonica (NAO duplicar cores em outros arquivos).
// Use SHIPPING_MODE_STYLE.<key> em qualquer badge que mostre forma de entrega.
// Padronizado em 2026-05-27 para garantir consistencia visual entre Pedidos,
// Anuncios, Modais e qualquer view futura.
// =============================================================================
export const SHIPPING_MODE_STYLE = {
  full: {
    label: 'Full',
    icon: 'fas fa-warehouse',
    bg: '#00a650',     // verde ML oficial
    fg: '#ffffff',
    title: 'Full — ML armazena e despacha (Fulfillment)',
  },
  flex: {
    label: 'Flex',
    icon: 'fas fa-bolt',
    bg: '#f97316',     // laranja Flex (motorcycle do ML)
    fg: '#ffffff',
    title: 'Flex — vendedor entrega no mesmo dia (Mercado Envios Flex)',
  },
  agencia: {
    label: 'Agência',
    icon: 'fas fa-store',
    bg: '#7c3aed',     // roxo (Mercado Envios Places/Agil)
    fg: '#ffffff',
    title: 'Agência — vendedor leva a ponto parceiro Mercado Envios Places/Agil',
  },
  correios: {
    label: 'Correios',
    icon: 'fas fa-truck',
    bg: '#facc15',     // amarelo Correios
    fg: '#1f2937',     // texto escuro pra contraste
    title: 'Correios — vendedor leva a uma agencia dos Correios',
  },
  coletado: {
    label: 'Coletado',
    icon: 'fas fa-people-carry',
    bg: '#0891b2',     // ciano/teal (ML Coleta)
    fg: '#ffffff',
    title: 'Coletado — Mercado Livre coleta o pacote no vendedor',
  },
  combinado: {
    label: 'Combinado',
    icon: 'fas fa-handshake',
    bg: '#6b7280',     // cinza neutro
    fg: '#ffffff',
    title: 'Combinado — acordo direto vendedor x comprador (sem ME)',
  },
  desconhecido: {
    label: 'Mercado Envios',
    icon: 'fas fa-truck',
    bg: '#e5e7eb',     // cinza claro
    fg: '#4b5563',
    title: 'Modo de envio nao identificado ainda',
  },
}

export function shippingModeStyle(mode) {
  return SHIPPING_MODE_STYLE[mode] || SHIPPING_MODE_STYLE.desconhecido
}

export const PLATFORMS = [
  { key: 'mercadolivre', label: 'Mercado Livre', icon: 'fas fa-store',        color: '#FFE600', logo: '/marketplaces/Mercado_livre_logo.png' },
  { key: 'shopee',       label: 'Shopee',        icon: 'fas fa-shopping-bag', color: '#EE4D2D', logo: '/marketplaces/shopee-logo.png' },
  { key: 'manual',       label: 'Manual',        icon: 'fas fa-hand-paper',   color: '#6c757d', logo: null },
]

// Helper: devolve {src, label} ou null se nao houver arte pro marketplace
export function platformLogo(key) {
  const p = PLATFORMS.find(p => p.key === key)
  return (p && p.logo) ? { src: p.logo, label: p.label } : null
}

export const RETURN_STATUSES = [
  { key: 'analyzing', label: 'Analisando', color: 'warning' },
  { key: 'returned',  label: 'Devolvido',  color: 'success' },
  { key: 'rejected',  label: 'Rejeitado',  color: 'danger' },
]

export const PERSON_TYPES = [
  { key: 'fisica',    label: 'Pessoa Física (CPF)' },
  { key: 'juridica',  label: 'Pessoa Jurídica (CNPJ)' },
]

export const BRAZIL_STATES = [
  'AC','AL','AP','AM','BA','CE','DF','ES','GO','MA',
  'MT','MS','MG','PA','PB','PR','PE','PI','RJ','RN',
  'RS','RO','RR','SC','SP','SE','TO',
]

export const FISCAL_ORIGINS = [
  { value: 0, label: '0 – Nacional' },
  { value: 1, label: '1 – Estrangeira (Importação Direta)' },
  { value: 2, label: '2 – Estrangeira (Mercado Interno)' },
  { value: 3, label: '3 – Nacional (>40% conteúdo estrangeiro)' },
  { value: 4, label: '4 – Nacional (processo produtivo básico)' },
  { value: 5, label: '5 – Nacional (≤40% conteúdo estrangeiro)' },
  { value: 6, label: '6 – Estrangeira (importação direta, sem similar)' },
  { value: 7, label: '7 – Estrangeira (mercado interno, sem similar)' },
  { value: 8, label: '8 – Nacional (conteúdo de importação >70%)' },
]
