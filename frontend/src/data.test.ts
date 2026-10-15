import { describe, it, expect } from 'vitest'
import { count, percent, date, state, type Shikigami } from './data'
describe('public statistics formatting', () => {
  it('keeps bigint counts exact beyond Number safe range', () => { expect(count('9223372036854775807')).toBe('9,223,372,036,854,775,807') })
  it('distinguishes unknown rates from real zero and formats decimals exactly', () => {
    expect(percent(null)).toBe('—'); expect(percent('0.000000')).toBe('0.0%')
    expect(percent('0.666667')).toBe('66.7%'); expect(percent('1.000000')).toBe('100.0%')
    expect(percent('0.123500')).toBe('12.4%'); expect(percent('2.0')).toBe('—')
  })
  it('uses Shanghai time instead of host timezone', () => { expect(date('2026-10-13T06:30:00Z')).toContain('14:30:00') })
  it('shows baseline without inventing games and preserves zero-win samples', () => {
    expect(state({ observation_count: '10', win_rate: null } as Shikigami).text).toBe('基线已建立')
    expect(state({ observation_count: '0', win_rate: null } as Shikigami).text).toBe('等待采集')
    expect(state({ observation_count: '10', win_rate: '0.000000' } as Shikigami).text).toBe('有统计样本')
  })
})
