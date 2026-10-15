import { createApp } from 'vue'
import { createRouter, createWebHashHistory } from 'vue-router'
import App from './App.vue'
import Dashboard from './pages/Dashboard.vue'
import Detail from './pages/Detail.vue'
import Information from './pages/Information.vue'
import './style.css'

const router = createRouter({ history: createWebHashHistory(), routes: [
  { path: '/', component: Dashboard },
  { path: '/shikigami', component: Dashboard, props: { catalog: true } },
  { path: '/shikigami/:id', component: Detail },
  { path: '/observations', component: Information, props: { mode: 'observations' } },
  { path: '/method', component: Information, props: { mode: 'method' } },
  { path: '/:pathMatch(.*)*', redirect: '/' },
], scrollBehavior: () => ({ top: 0 }) })
createApp(App).use(router).mount('#app')
