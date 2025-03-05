import { createRouter, createWebHistory, RouteRecordRaw } from 'vue-router';
import RegionList from '../components/RegionList.vue';
import SchoolList from '../components/SchoolList.vue';

const routes: Array<RouteRecordRaw> = [
  {
    path: '/',
    name: 'Home',
    component: RegionList,
  },
  {
    path: '/schools',
    name: 'Schools',
    component: SchoolList,
  },
];

const router = createRouter({
  history: createWebHistory(process.env.BASE_URL),
  routes,
});

export default router; 