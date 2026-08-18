import { describe, expect, it } from 'vitest'
import { calculateWeightedRisk, levelForScore } from './risk'

describe('risk model', () => {
  it('uses the documented 25/25/15/15/10/10 weights and inverts capacity', () => {
    const result = calculateWeightedRisk({ severity: 90, transmission: 80, scale: 70, travel: 60, transit: 50, capacity: 20 })
    expect(result).toEqual({ score: 75, level: 'orange' })
  })

  it.each([[39.9, 'blue'], [40, 'yellow'], [60, 'orange'], [80, 'red']] as const)(
    'maps %s to %s',
    (score, level) => expect(levelForScore(score)).toBe(level),
  )

  it('rejects invalid weights', () => {
    expect(() => calculateWeightedRisk({}, { severity: 0.2 })).toThrow('权重之和必须为 1')
  })
})
