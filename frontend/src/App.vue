<template>
  <router-view v-slot="{ Component, route }">
    <!-- 公开页面（登录/注册）/ 全屏页面（监控大屏）：无侧边栏。
         public 免鉴权；fullscreen 仍走登录守卫，只是布局全屏。 -->
    <component v-if="route.meta.public || route.meta.fullscreen" :is="Component" />

    <!-- 应用页面：侧边栏 + 内容区 -->
    <div v-else class="layout">
      <Sidebar />
      <main class="main-content">
        <keep-alive :include="['Dashboard', 'Containers']">
          <component :is="Component" />
        </keep-alive>
      </main>
      <AIOpsAssistantFloat v-if="route.name !== 'aiops-assistant' && route.name !== 'aiops-workbench' && canUseAgent" />
      <CommandPalette />
    </div>
  </router-view>
</template>

<script setup>
import { computed, defineAsyncComponent } from 'vue'
import Sidebar from './components/Sidebar.vue'
import { useAuthStore } from './stores/auth.js'

const AIOpsAssistantFloat = defineAsyncComponent(() => import('./components/AIOpsAssistantFloat.vue'))
const CommandPalette = defineAsyncComponent(() => import('./components/CommandPalette.vue'))

const authStore = useAuthStore()
const canUseAgent = computed(() => authStore.can('agent', 'view'))
</script>

<style scoped>
.layout {
  display: flex;
  width: 100%;
  height: 100vh;
  overflow: hidden;
  background: var(--bg-base);
}
.main-content {
  flex: 1;
  min-width: 0;
  height: 100vh;
  overflow: hidden;
  background:
    radial-gradient(1200px circle at 100% 0%, rgba(var(--accent-rgb), 0.05), transparent 32%),
    radial-gradient(900px circle at 0% 0%, rgba(99, 130, 91, 0.04), transparent 30%),
    var(--bg-base);
  position: relative;
  display: flex;
  flex-direction: column;
}
</style>
