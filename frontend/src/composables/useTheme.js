import { ref } from 'vue'

export const THEMES = [
  { id: 'light', label: '日间', icon: '☀' },
  { id: 'dark',  label: '夜间', icon: '🌙' },
]

const STORAGE_KEY = 'aiops-theme'

function applyTheme(id) {
  if (id === 'dark') {
    document.documentElement.setAttribute('data-theme', 'dark')
  } else {
    document.documentElement.removeAttribute('data-theme')
  }
}

// 旧版存的是 'dark' 表示无 attribute，新版反过来——迁移一次
const _stored = localStorage.getItem(STORAGE_KEY)
const currentTheme = ref(_stored || 'light')
applyTheme(currentTheme.value)

export function useTheme() {
  function setTheme(id) {
    currentTheme.value = id
    localStorage.setItem(STORAGE_KEY, id)
    applyTheme(id)
  }
  return { currentTheme, THEMES, setTheme }
}
