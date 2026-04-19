<template>
  <router-view v-slot="{ Component, route }">
    <!-- 公开页面（登录/注册）：全屏无侧边栏 -->
    <component v-if="route.meta.public" :is="Component" />

    <!-- 应用页面：侧边栏 + 内容区 -->
    <div v-else class="layout">
      <Sidebar />
      <main class="main-content">
        <keep-alive include="Dashboard">
          <component :is="Component" />
        </keep-alive>
      </main>
      <AIOpsAssistantFloat v-if="route.name !== 'aiops-assistant'" />
    </div>
  </router-view>
</template>

<script setup>
import Sidebar from './components/Sidebar.vue'
import AIOpsAssistantFloat from './components/AIOpsAssistantFloat.vue'
</script>

<style scoped>
.layout {
  display: flex;
  width: 100%;
  height: 100vh;
  overflow: hidden;
}
.main-content {
  flex: 1;
  min-width: 0;
  height: 100vh;
  overflow: hidden;
  background: var(--bg-base);
  position: relative;
  display: flex;
  flex-direction: column;
}
</style>
