import type { RiskLevel } from './types'

export const levelMeta: Record<RiskLevel, { label: string; color: string; soft: string }> = {
  red: { label: '红色', color: '#ff4d67', soft: 'rgba(255,77,103,.14)' },
  orange: { label: '橙色', color: '#ff9f43', soft: 'rgba(255,159,67,.14)' },
  yellow: { label: '黄色', color: '#f5ce48', soft: 'rgba(245,206,72,.14)' },
  blue: { label: '蓝色', color: '#4ea1ff', soft: 'rgba(78,161,255,.14)' },
}

export const formatNumber = (value: number) => new Intl.NumberFormat('zh-CN').format(value)
export const compactNumber = (value: number) => value >= 10_000 ? `${(value / 10_000).toFixed(value >= 100_000 ? 0 : 1)}万` : formatNumber(value)
export const formatTime = (value: string) => new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(value))
export const formatBytes = (value: number) => value >= 1024 ** 3 ? `${(value / 1024 ** 3).toFixed(1)} GB` : value >= 1024 ** 2 ? `${(value / 1024 ** 2).toFixed(1)} MB` : `${(value / 1024).toFixed(0)} KB`
