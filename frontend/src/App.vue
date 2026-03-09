<template>
  <div class="layout">
    <Sidebar />
    <main class="main-content">
      <router-view v-slot="{ Component }">
        <transition name="fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>
  </div>
</template>

<script setup>
import Sidebar from './components/Sidebar.vue'
</script>

<style scoped>
.layout { display: flex; height: 100vh; overflow: hidden; }
.main-content { flex: 1; overflow-y: auto; background: var(--bg-base); }
</style>
