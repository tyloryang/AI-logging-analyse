<template>
  <div class="trp" :class="{ open }">
    <button class="trp-btn" :title="'全局时间窗 · 所有可观测性页面共用'" @click="open = !open" @blur="onBlur">
      <span class="trp-icon">⌚</span>
      <span class="trp-label">{{ store.label }}</span>
      <span class="trp-arrow">▾</span>
    </button>
    <div v-if="open" class="trp-menu">
      <button v-for="p in store.presets" :key="p.hours"
        class="trp-item" :class="{ active: store.hours === p.hours }"
        @mousedown.prevent="choose(p.hours)">
        {{ p.label }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useTimeRangeStore } from '../stores/timeRange.js'

const store = useTimeRangeStore()
const open = ref(false)

function choose(h) {
  store.set(h)
  open.value = false
}
function onBlur() { setTimeout(() => { open.value = false }, 150) }
</script>

<style scoped>
.trp { position: relative; }
.trp-btn {
  display: inline-flex; align-items: center; gap: 7px;
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 10px; padding: 6px 14px;
  font-size: 12.5px; color: var(--text-primary); cursor: pointer;
  transition: border-color .15s;
}
.trp-btn:hover, .trp.open .trp-btn { border-color: var(--accent); }
.trp-icon { color: var(--accent); }
.trp-arrow { color: var(--text-muted); font-size: 10px; }
.trp-menu {
  position: absolute; right: 0; top: calc(100% + 6px);
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 10px; padding: 5px;
  box-shadow: var(--shadow-md);
  min-width: 160px; z-index: 50;
}
.trp-item {
  display: block; width: 100%; text-align: left;
  background: transparent; border: none; cursor: pointer;
  padding: 7px 12px; border-radius: 7px;
  font-size: 12.5px; color: var(--text-primary);
}
.trp-item:hover { background: var(--bg-hover); }
.trp-item.active { background: var(--accent-soft); color: var(--accent); font-weight: 600; }
</style>
