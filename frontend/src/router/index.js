import { createRouter, createWebHistory } from 'vue-router'
import Home from '../views/Home.vue'
import TestView from '../views/TestView.vue'

// 定义内联404组件
const NotFound = {
  template: `
    <div style="text-align: center; padding: 50px;">
      <h1>404 - 页面未找到</h1>
      <p>抱歉，您请求的页面不存在。</p>
      <router-link to="/">返回首页</router-link>
    </div>
  `
}

const routes = [
  {
    path: '/',
    name: 'Home',
    component: Home
  },
  {
    path: '/school-value-added',
    name: 'SchoolValueAdded',
    component: () => import('../views/SchoolValueAdded.vue')
  },
  {
    path: '/teacher-value-added',
    name: 'TeacherValueAdded',
    component: () => import('../views/TeacherValueAdded.vue') 
  },
  {
    path: '/student-portrait',
    name: 'StudentPortrait',
    component: () => import('../views/StudentPortrait.vue')
  },
  {
    path: '/results',
    name: 'Results',
    component: () => import('../views/Results.vue')
  },
  {
    path: '/data-management',
    name: 'DataManagement',
    component: () => import('../views/DataManagement.vue')
  },
  {
    path: '/404',
    name: 'NotFound',
    component: NotFound
  },
  {
    path: '/:pathMatch(.*)*',  // Vue 3语法的通配符路由
    redirect: '/'
  },
  {
    path: '/test',
    name: 'test',
    component: TestView
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router 