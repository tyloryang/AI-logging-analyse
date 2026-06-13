/**
 * 全局时间窗 store —— 所有可观测性页面共用。
 * - hours: 数值（兼容 LogAnalysis 的字符串）
 * - label: 显示用文字
 * - 持久化到 localStorage，跨页面切换/刷新保留
 */
import { defineStore } from 'pinia'

const PRESETS = [
  { hours: 0.25, label: '最近 15 分钟' },
  { hours: 0.5,  label: '最近 30 分钟' },
  { hours: 1,    label: '最近 1 小时'   },
  { hours: 6,    label: '最近 6 小时'   },
  { hours: 24,   label: '最近 24 小时'  },
  { hours: 72,   label: '最近 3 天'     },
  { hours: 168,  label: '最近 7 天'     },
]

const KEY = 'aiops.timeRange.hours'

export const useTimeRangeStore = defineStore('timeRange', {
  state: () => {
    const saved = Number(localStorage.getItem(KEY) || 1)
    return {
      hours: Number.isFinite(saved) && saved > 0 ? saved : 1,
      presets: PRESETS,
    }
  },
  getters: {
    label: (state) => {
      const p = PRESETS.find(p => p.hours === state.hours)
      return p ? p.label : `最近 ${state.hours} 小时`
    },
    rangeMs: (state) => state.hours * 3600 * 1000,
    sinceIso: (state) => new Date(Date.now() - state.hours * 3600 * 1000).toISOString(),
    untilIso: () => new Date().toISOString(),
  },
  actions: {
    set(hours) {
      this.hours = Number(hours) || 1
      localStorage.setItem(KEY, String(this.hours))
    },
  },
})
