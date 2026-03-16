import { ref } from 'vue'

export const THEMES = [
  { id: 'light', label: '日间', icon: '☀' },
  { id: 'dark',  label: '夜间', icon: '🌙' },
]

const STORAGE_KEY = 'aiops-theme'

function applyTheme(id) {
  if (id === 'light') {
    document.documentElement.setAttribute('data-theme', 'light')
  } else {
    document.documentElement.removeAttribute('data-theme')
  }
}

const currentTheme = ref(localStorage.getItem(STORAGE_KEY) || 'dark')
applyTheme(currentTheme.value)

export function useTheme() {
  function setTheme(id) {
    currentTheme.value = id
    localStorage.setItem(STORAGE_KEY, id)
    applyTheme(id)
  }
  return { currentTheme, THEMES, setTheme }
}
