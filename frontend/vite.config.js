import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        // 保留浏览器原始 Host 头: 后端 CSRF 校验要求 Origin 与 Host 同源,
        // changeOrigin 会把 Host 改写成 127.0.0.1:8000 导致所有 POST 被 403 拒绝
        changeOrigin: false,
        ws: true,
      },
    },
  },
  build: {
    chunkSizeWarningLimit: 1000,
    rollupOptions: {
      output: {
        manualChunks: {
          'vue-vendor':  ['vue', 'vue-router', 'pinia'],
          'xterm':       ['xterm', 'xterm-addon-fit'],
          'axios':       ['axios'],
        },
      },
    },
  },
})