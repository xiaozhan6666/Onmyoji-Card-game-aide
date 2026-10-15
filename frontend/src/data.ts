import { ref } from 'vue'
import portraitAssets from './portrait-assets.json'

export interface GradeStats {
  grade: number | null; grade_name: string; status: string; win_rate: string | null;
  sample_wins: string; sample_losses: string; sample_games: string; contributing_players: string;
}
export interface Shikigami extends GradeStats {
  id: string; name: string; season_key: string; observation_count: string; observed_players: string;
  latest_capture_at: string | null; stats_updated_at: string; window_start: string; window_end: string;
  grade_statistics: GradeStats[]; latest_observed_grades: { grade: number; player_count: string }[];
  unassigned_grade: GradeStats; excluded_intervals: Record<string, string>; method: string;
  rule_version: string; calculation_mode: string; conditions_confirmed: boolean;
}
export const records = ref<Shikigami[]>([])
export const loading = ref(false)
export const error = ref('')
export const loaded = ref(false)
export const fetchedAt = ref<Date | null>(null)
let active: AbortController | undefined
export async function refresh() {
  active?.abort()
  const controller = new AbortController(); active = controller
  loading.value = true; error.value = ''
  const timeout = setTimeout(() => controller.abort(), 15000)
  try {
    const response = await fetch('/api/rankings', { signal: controller.signal })
    if (!response.ok) throw new Error(`服务返回 ${response.status}`)
    const data: unknown = await response.json()
    if (!Array.isArray(data) || data.some(r => typeof r.id !== 'string' || !Array.isArray(r.grade_statistics) || typeof r.observation_count !== 'string')) throw new Error('接口数据版本不匹配，请更新后端')
    if (active !== controller) return
    records.value = data; loaded.value = true; fetchedAt.value = new Date()
  } catch (e) {
    if (active !== controller) return
    error.value = e instanceof Error && e.name !== 'AbortError' ? e.message : '连接超时，请稍后重试'
  } finally {
    clearTimeout(timeout)
    if (active === controller) loading.value = false
  }
}

export const gradeNames: Record<number, string> = { 5: '五段', 6: '六段', 7: '七段', 8: '八段', 9: '名士', 10: '大名士' }
export function count(value: string | undefined) { return value == null ? '—' : BigInt(value).toLocaleString('zh-CN') }
// Format the server's decimal with integer arithmetic; never recalculate a win rate.
export function percent(value: string | null | undefined) {
  if (value == null) return '—'
  if (!/^(0(\.\d+)?|1(\.0+)?)$/.test(value)) return '—'
  const [whole = '0', fraction = ''] = value.split('.')
  const scale = 10n ** BigInt(fraction.length)
  const units = BigInt(whole) * scale + BigInt(fraction || '0')
  const tenths = (units * 1000n + scale / 2n) / scale
  return `${tenths / 10n}.${tenths % 10n}%`
}
export function date(value: string | null | undefined, short = false) {
  if (!value) return '尚未采集'
  return new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', ...(short ? {} : { second: '2-digit' }), hour12: false }).format(new Date(value))
}
export function state(row: Shikigami) {
  if (row.win_rate != null) return { text: '有统计样本', className: 'green' }
  if (BigInt(row.observation_count || '0') > 0n) return { text: '基线已建立', className: 'amber' }
  return { text: '等待采集', className: 'muted' }
}
export function sum(field: 'observation_count' | 'sample_games') { return records.value.reduce((n, r) => n + BigInt(r[field]), 0n).toLocaleString('zh-CN') }
export function selectedStats(row: Shikigami, grade: string) { return grade === 'all' ? row : row.grade_statistics.find(g => g.grade === Number(grade))! }
export function portrait(id: string) { return (portraitAssets as Record<string, string>)[id] ?? `/portraits/${id}.png` }
