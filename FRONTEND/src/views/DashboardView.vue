<template>
  <div>
    <!-- KPI Cards row -->
    <div class="row">
      <div class="col-lg-3 col-6">
        <KpiCard
          title="Vendas no Mês"
          :value="kpis.monthly_sales_count"
          icon="fas fa-shopping-bag"
          color="info"
          :change="kpis.monthly_sales_change_pct"
          :subtitle="`R$ ${formatCurrency(kpis.monthly_sales_value)}`"
        />
      </div>
      <div class="col-lg-3 col-6">
        <KpiCard
          title="Pedidos para Pagar"
          :value="kpis.unpaid_orders_count"
          icon="fas fa-dollar-sign"
          color="warning"
          subtitle="Ver pedidos não pagos"
          link-to="/orders?payment_status=pending"
        />
      </div>
      <div class="col-lg-3 col-6">
        <KpiCard
          title="Sem Vínculo de Produto"
          :value="kpis.unlinked_orders_count"
          icon="fas fa-unlink"
          color="danger"
          subtitle="Ver pedidos"
          link-to="/orders?unlinked=true"
        />
      </div>
      <div class="col-lg-3 col-6">
        <KpiCard
          title="Pedidos Cancelados"
          :value="kpis.cancelled_orders_count"
          icon="fas fa-times-circle"
          color="secondary"
          subtitle="Ver cancelados"
          link-to="/orders?status=cancelled"
        />
      </div>
    </div>

    <!-- Secondary metrics -->
    <div class="row">
      <div class="col-md-4">
        <div class="info-box">
          <span class="info-box-icon bg-info elevation-1">
            <i class="fas fa-box"></i>
          </span>
          <div class="info-box-content">
            <span class="info-box-text">Total de Produtos</span>
            <span class="info-box-number">{{ kpis.total_products }}</span>
          </div>
        </div>
      </div>
      <div class="col-md-4">
        <div class="info-box">
          <span class="info-box-icon bg-success elevation-1">
            <i class="fas fa-chart-line"></i>
          </span>
          <div class="info-box-content">
            <span class="info-box-text">Vendas (30 dias)</span>
            <span class="info-box-number">{{ formatCurrency(kpis.sales_last_30_days) }}</span>
          </div>
        </div>
      </div>
      <div class="col-md-4">
        <div class="info-box">
          <span class="info-box-icon bg-warning elevation-1">
            <i class="fas fa-calendar-day"></i>
          </span>
          <div class="info-box-content">
            <span class="info-box-text">Vendas de Hoje</span>
            <span class="info-box-number">{{ formatCurrency(kpis.sales_today) }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Top 8 catalog products -->
    <div class="row">
      <div class="col-12">
        <div class="card">
          <div class="card-header">
            <h3 class="card-title">
              <i class="fas fa-star mr-2 text-warning"></i>
              Últimos 8 produtos do catálogo
            </h3>
            <div class="card-tools">
              <RouterLink to="/catalog" class="btn btn-sm btn-outline-primary">
                Ver catálogo completo
              </RouterLink>
            </div>
          </div>
          <div class="card-body">
            <div v-if="loadingProducts" class="text-center py-4">
              <i class="fas fa-spinner fa-spin fa-2x text-muted"></i>
            </div>
            <div v-else class="row">
              <div
                v-for="product in topProducts"
                :key="product.id"
                class="col-xl-3 col-lg-4 col-md-6 col-12 mb-3"
              >
                <div class="card card-outline card-primary h-100">
                  <div class="card-body p-2">
                    <img
                      :src="product.image_url || 'https://via.placeholder.com/200x150?text=Sem+Foto'"
                      class="img-fluid mb-2 rounded"
                      style="height: 140px; width: 100%; object-fit: cover"
                      :alt="product.title"
                    />
                    <p class="text-xs text-muted mb-1">{{ product.sku }}</p>
                    <p class="font-weight-bold mb-1 text-sm" style="line-height:1.2">
                      {{ product.title.slice(0, 55) }}{{ product.title.length > 55 ? '...' : '' }}
                    </p>
                    <p class="text-success font-weight-bold mb-1">{{ formatCurrency(product.cost_price) }}</p>
                    <small class="text-muted">Estoque: {{ product.stock_quantity }}</small>
                  </div>
                  <div class="card-footer p-1">
                    <RouterLink
                      :to="`/catalog/${product.id}`"
                      class="btn btn-sm btn-primary btn-block"
                    >
                      <i class="fas fa-plus mr-1"></i> Cadastrar Produto
                    </RouterLink>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import KpiCard from '@/components/dashboard/KpiCard.vue'
import { formatCurrency } from '@/utils/formatters'
import api from '@/composables/useApi'

const kpis = reactive({
  monthly_sales_count: 0,
  monthly_sales_value: 0,
  monthly_sales_change_pct: 0,
  unpaid_orders_count: 0,
  unlinked_orders_count: 0,
  cancelled_orders_count: 0,
  total_products: 0,
  sales_last_30_days: 0,
  sales_today: 0,
})

const topProducts = ref([])
const loadingProducts = ref(true)

onMounted(async () => {
  const [kpisRes, productsRes] = await Promise.all([
    api.get('/dashboard/kpis'),
    api.get('/dashboard/top-products'),
  ])
  Object.assign(kpis, kpisRes.data)
  topProducts.value = productsRes.data
  loadingProducts.value = false
})
</script>
