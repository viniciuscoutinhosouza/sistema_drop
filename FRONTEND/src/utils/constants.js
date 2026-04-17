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

export const PLATFORMS = [
  { key: 'mercadolivre', label: 'Mercado Livre', icon: 'fas fa-store',    color: '#FFE600' },
  { key: 'shopee',       label: 'Shopee',        icon: 'fas fa-shopping-bag', color: '#EE4D2D' },
  { key: 'manual',       label: 'Manual',        icon: 'fas fa-hand-paper',  color: '#6c757d' },
]

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
