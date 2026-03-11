import { ref } from 'vue'

export const THEMES = [
  { id: 'deep-space', label: 'Deep Space', color: '#00d4ff' },
  { id: 'cyber',      label: 'Cyber',      color: '#bf00ff' },
  { id: 'matrix',     label: 'Matrix',     color: '#00ff41' },
  { id: 'steel',      label: 'Steel',      color: '#2563eb' },
  { id: 'arctic',     label: 'Arctic',     color: '#0ea5e9' },
]

const STORAGE_KEY = 'aiops-theme'

function applyTheme(id) {
  if (id === 'deep-space') {
    document.documentElement.removeAttribute('data-theme')
  } else {
    document.documentElement.setAttribute('data-theme', id)
  }
}

const currentTheme = ref(localStorage.getItem(STORAGE_KEY) || 'deep-space')

// Apply on load
applyTheme(currentTheme.value)

export function useTheme() {
  function setTheme(id) {
    currentTheme.value = id
    localStorage.setItem(STORAGE_KEY, id)
    applyTheme(id)
  }

  return { currentTheme, THEMES, setTheme }
}
