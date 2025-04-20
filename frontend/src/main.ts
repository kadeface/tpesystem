import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import axios from 'axios'

// 配置axios
const http = axios.create({
  baseURL: process.env.VUE_APP_API_URL || '/api',
  timeout: 60000
})

const app = createApp(App)
app.use(router)
app.use(ElementPlus)
app.config.globalProperties.$http = http
app.mount('#app') 