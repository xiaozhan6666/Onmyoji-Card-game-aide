<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { refresh, loading, error, loaded, fetchedAt } from './data'
import Icon from './components/Icon.vue'
const route = useRoute()
const menu = ref(false)
const links = [{ path: '/', text: '数据总览', icon: 'grid' }, { path: '/shikigami', text: '式神图鉴', icon: 'cards' }, { path: '/observations', text: '采集概览', icon: 'activity' }, { path: '/method', text: '统计说明', icon: 'book' }]
onMounted(refresh)
</script>
<template>
  <div class="app-shell">
    <button v-if="menu" class="nav-backdrop" aria-label="关闭导航" @click="menu = false"></button>
    <aside class="sidebar" :class="{ open: menu }">
      <RouterLink to="/" class="brand" @click="menu = false"><img src="/mark.svg" alt=""/><div><strong>百闻录</strong><span>百闻牌 · 数据助手</span></div></RouterLink>
      <div class="nav-label">百炼观测</div>
      <nav aria-label="主导航"><RouterLink v-for="link in links" :key="link.path" :to="link.path" :class="{ active: link.path === '/' ? route.path === '/' : route.path.startsWith(link.path) }" @click="menu = false"><Icon :name="link.icon"/><span>{{ link.text }}</span><span class="nav-dot"></span></RouterLink></nav>
      <div class="sidebar-note"><div class="seal">闻</div><p>以观察为始<br/>让每一场，都有迹可循。</p><span>ONMYOJI CARD OBSERVATORY</span></div>
      <div class="sidebar-bottom"><span class="status-dot" :class="{ offline: !!error }"></span>{{ error ? '数据服务未连接' : loaded ? '数据服务已连接' : '正在连接数据服务' }}<span class="version">v0.1</span></div>
    </aside>
    <main class="main-shell">
      <header class="topbar"><div class="breadcrumb"><button class="mobile-menu icon-button" aria-label="打开导航" @click="menu = true"><Icon name="menu"/></button><span>百闻牌助手</span><Icon name="chevron" :size="13"/><strong>{{ route.path.startsWith('/shikigami/') ? '式神详情' : links.find(l => l.path === route.path)?.text }}</strong></div><div class="top-actions"><span class="season"><i></i>S56 赛季</span><span class="single-server">单服 · 百炼榜</span><button class="icon-button" aria-label="刷新数据" title="刷新网站数据" :disabled="loading" @click="refresh"><Icon name="refresh" :class="{ spinning: loading }"/></button></div></header>
      <div class="page-content">
        <div v-if="error" class="error-banner" role="alert"><Icon name="info"/><div><strong>暂时无法读取最新数据</strong><p>{{ error }}。{{ loaded ? '下方保留上次结果，尚未更新。' : '请确认本机数据服务已经启动。' }}</p></div><button @click="refresh" :disabled="loading">重试</button></div>
        <div v-if="loading && !loaded" class="loading-page" role="status"><span class="loading-orbit"></span><h2>正在翻开百闻录</h2><p>读取式神与百炼观察数据…</p></div>
        <RouterView v-else-if="loaded"/>
        <div v-else class="empty-service"><Icon name="activity" :size="40"/><h2>等待数据服务</h2><p>连接后，这里会呈现真实的式神观察与样本统计。</p></div>
      </div>
      <footer class="page-footer"><span>百闻录 <b>·</b> 从观察开始，谨慎理解胜率。</span><span>{{ fetchedAt ? `页面读取于 ${fetchedAt.toLocaleTimeString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })}` : '尚未读取数据' }} <b>·</b> 北京时间</span></footer>
    </main>
  </div>
</template>
