import type { RiskLevel } from './types'

export const defaultRiskWeights: Record<string, number> = {
  severity: 0.25,
  transmission: 0.25,
  scale: 0.15,
  travel: 0.15,
  transit: 0.10,
  capacity: 0.10,
}

export function levelForScore(score: number): RiskLevel {
  if (score >= 80) return 'red'
  if (score >= 60) return 'orange'
  if (score >= 40) return 'yellow'
  return 'blue'
}

export function calculateWeightedRisk(
  factors: Record<string, number>,
  weights: Record<string, number> = defaultRiskWeights,
): { score: number; level: RiskLevel } {
  const total = Object.values(weights).reduce((sum, weight) => sum + weight, 0)
  if (Math.abs(total - 1) > 1e-6) throw new Error('风险因子权重之和必须为 1')

  const raw = Object.entries(weights).reduce((sum, [key, weight]) => {
    const value = factors[key] ?? 0
    if (value < 0 || value > 100) throw new Error(`风险因子 ${key} 必须在 0—100 之间`)
    return sum + (key === 'capacity' ? 100 - value : value) * weight
  }, 0)
  const score = Math.round(Math.max(0, Math.min(100, raw)) * 10) / 10
  return { score, level: levelForScore(score) }
}
