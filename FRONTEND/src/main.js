import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'

// Bootstrap CSS + AdminLTE CSS
import 'bootstrap/dist/css/bootstrap.min.css'
import 'admin-lte/dist/css/adminlte.min.css'
import '@fortawesome/fontawesome-free/css/all.min.css'

// jQuery + Bootstrap JS + AdminLTE JS (required by AdminLTE)
import $ from 'jquery'
window.$ = $
window.jQuery = $
import 'bootstrap/dist/js/bootstrap.bundle.min.js'
import 'admin-lte/dist/js/adminlte.min.js'

import { useAuthStore } from '@/stores/auth'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)

// Load persisted auth before mounting
const authStore = useAuthStore()
authStore.loadFromStorage()

app.mount('#app')
