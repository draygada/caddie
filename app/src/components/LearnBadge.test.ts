import { describe, expect, it } from 'vitest'

import { LEARN_HELP, learnBadgeText } from './LearnBadge'

describe('learnBadgeText', () => {
  it('counts the shots learned from', () => {
    expect(learnBadgeText(0)).toBe('No course shots to learn from yet')
    expect(learnBadgeText(1)).toBe('Learned from 1 shot')
    expect(learnBadgeText(14)).toBe('Learned from 14 shots')
  })

  it('the tooltip says the value grid is not re-solved', () => {
    expect(LEARN_HELP).toMatch(/not re-solved/)
  })
})
