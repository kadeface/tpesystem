import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import axios from 'axios'
import educationDataApi from './api/education-data'

// 导入WebSocket配置
import './config/socket'

// 配置axios
const http = axios.create({
  baseURL: process.env.VUE_APP_API_URL || '/',
  timeout: 60000
})

const app = createApp(App)
app.use(router)
app.use(ElementPlus)
app.config.globalProperties.$http = http
app.config.globalProperties.$api = educationDataApi

// 添加全局错误处理
app.config.errorHandler = (err) => {
  if (err.message && err.message.includes('ResizeObserver')) {
    // 忽略 ResizeObserver 错误
    return;
  }
  console.error(err);
};

app.mount('#app')
