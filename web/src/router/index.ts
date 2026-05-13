import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/Login.vue'),
    },
    {
      path: '/',
      component: () => import('../layouts/MainLayout.vue'),
      meta: { requiresAuth: true },
      children: [
        { path: '', name: 'dashboard', component: () => import('../views/Dashboard.vue') },
        { path: 'conversations', name: 'conversations', component: () => import('../views/Conversations.vue') },
        { path: 'items', name: 'items', component: () => import('../views/Items.vue') },
        { path: 'orders', name: 'orders', component: () => import('../views/Orders.vue') },
        { path: 'analytics', name: 'analytics', component: () => import('../views/Analytics.vue') },
        { path: 'config', name: 'config', component: () => import('../views/Config.vue') },
        { path: 'logs', name: 'logs', component: () => import('../views/Logs.vue') },
      ],
    },
  ],
})

router.beforeEach((to, _from, next) => {
  const auth = useAuthStore()
  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    next({ name: 'login' })
  } else if (to.name === 'login' && auth.isAuthenticated) {
    next({ name: 'dashboard' })
  } else {
    next()
  }
})

export default router
