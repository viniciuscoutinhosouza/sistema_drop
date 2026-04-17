<template>
  <div class="wrapper">
    <AppTopbar />
    <AppSidebar />

    <!-- Content Wrapper -->
    <div class="content-wrapper">
      <div class="content-header">
        <div class="container-fluid">
          <div class="row mb-2">
            <div class="col-sm-6">
              <h1 class="m-0">{{ route.meta.title || 'MIG ECOMMERCE' }}</h1>
            </div>
          </div>
        </div>
      </div>

      <section class="content">
        <div class="container-fluid">
          <RouterView />
        </div>
      </section>
    </div>

    <!-- Footer -->
    <footer class="main-footer">
      <strong>MIG ECOMMERCE</strong> &copy; {{ new Date().getFullYear() }}
      <div class="float-right d-none d-sm-inline-block">
        <b>Versão</b> 1.0.0
      </div>
    </footer>

    <!-- Toast notifications -->
    <div
      class="position-fixed"
      style="bottom: 1rem; right: 1rem; z-index: 9999; min-width: 280px"
    >
      <div
        v-for="toast in toasts"
        :key="toast.id"
        :class="`alert alert-${toast.type} alert-dismissible mb-2 shadow`"
        role="alert"
      >
        {{ toast.message }}
        <button type="button" class="close" @click="removeToast(toast.id)">
          <span>&times;</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useRoute } from 'vue-router'
import AppTopbar from '@/components/common/AppTopbar.vue'
import AppSidebar from '@/components/common/AppSidebar.vue'
import { useFinancialStore } from '@/stores/financial'
import { useNotificationsStore } from '@/stores/notifications'
import { useSocket } from '@/composables/useSocket'
import { useToast } from '@/composables/useToast'

const route = useRoute()
const financialStore = useFinancialStore()
const notificationsStore = useNotificationsStore()
const { connect } = useSocket()
const { toasts, remove: removeToast } = useToast()

onMounted(async () => {
  connect()
  await Promise.all([
    financialStore.fetchBalance(),
    notificationsStore.fetchNotifications(),
  ])
})
</script>
