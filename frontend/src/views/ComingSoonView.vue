<template>
  <div class="coming-soon">
    <div class="cs-card">
      <div class="cs-icon" v-html="icon"></div>
      <h2>{{ title }}</h2>
      <p class="cs-desc">{{ desc || '该模块正在建设中，敬请期待' }}</p>
      <div class="cs-badge">Coming Soon</div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, default: '建设中' },
  desc:  { type: String, default: '' },
  icon:  { type: String, default: '<svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>' },
})
</script>

<style scoped>
.coming-soon {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-main, #0d1117);
}
.cs-card {
  text-align: center;
  padding: 48px 60px;
  border-radius: 16px;
  border: 1px solid rgba(255,255,255,0.08);
  background: var(--bg-card, #161b22);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  max-width: 380px;
}
.cs-icon {
  color: var(--accent, #388bfd);
  opacity: 0.6;
  margin-bottom: 4px;
}
h2 {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary, #e6edf3);
  margin: 0;
}
.cs-desc {
  font-size: 13px;
  color: var(--text-muted, #6e7681);
  margin: 0;
  line-height: 1.6;
}
.cs-badge {
  margin-top: 8px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: .08em;
  color: var(--accent, #388bfd);
  background: rgba(56,139,253,0.12);
  border: 1px solid rgba(56,139,253,0.25);
  border-radius: 20px;
  padding: 3px 12px;
}
</style>
