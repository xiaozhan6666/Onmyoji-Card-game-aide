<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { records, portrait, state, count, percent, date, gradeNames } from '../data'
import Icon from '../components/Icon.vue'
import GradeTable from '../components/GradeTable.vue'
const route = useRoute()
const row = computed(() => records.value.find(r => r.id === route.params.id))
const maxCoverage = computed(() => Math.max(1, ...(row.value?.latest_observed_grades.map(g => Number(g.player_count)) || [])))
const primaryGrades = computed(() => row.value?.grade_statistics.filter(g => g.grade! >= 9) || [])
const otherGrades = computed(() => row.value?.grade_statistics.filter(g => g.grade! < 9 && BigInt(g.sample_games) > 0n) || [])
const primaryCoverage = computed(() => row.value?.latest_observed_grades.filter(g => g.grade >= 9) || [])
const otherCoverage = computed(() => row.value?.latest_observed_grades.filter(g => g.grade < 9 && BigInt(g.player_count) > 0n) || [])
</script>
<template>
  <RouterLink to="/" class="back-link"><Icon name="arrow" :size="16" class="flipped"/>返回数据总览</RouterLink>
  <template v-if="row">
    <section class="detail-heading"><div class="detail-portrait"><img :src="portrait(row.id)" :alt="row.name"/></div><div><div class="eyebrow dark">SHIKIGAMI OBSERVATION</div><h1>{{ row.name }}<span class="badge" :class="state(row).className">{{ state(row).text }}</span></h1><p>{{ row.season_key }} 赛季 · 百炼榜观察 · 最近 7 天</p></div><div class="detail-last"><span>最近一次采集</span><strong>{{ date(row.latest_capture_at) }}</strong></div></section>
    <section class="metrics detail-metrics"><article><span class="metric-label">样本胜率</span><div class="metric-value">{{ percent(row.win_rate) }}</div><span class="metric-note">{{ row.win_rate == null ? '等待有效变化区间' : '由服务端按有效区间汇总' }}</span></article><article><span class="metric-label">近 7 天新增场数</span><div class="metric-value">{{ count(row.sample_games) }}<small>场</small></div><span class="metric-note">{{ count(row.sample_wins) }} 胜 / {{ count(row.sample_losses) }} 负</span></article><article><span class="metric-label">已观察玩家</span><div class="metric-value">{{ count(row.observed_players) }}<small>人</small></div><span class="metric-note">参与有效统计 {{ count(row.contributing_players) }} 人</span></article><article><span class="metric-label">已保存观察</span><div class="metric-value">{{ count(row.observation_count) }}<small>条</small></div><span class="metric-note">当前赛季 · 最近 7 天</span></article></section>
    <div v-if="row.win_rate == null" class="baseline-notice"><Icon name="info"/><div><strong>{{ BigInt(row.observation_count) ? '基线已就位，等待下一次变化。' : '这位式神还在等待首次观察。' }}</strong><p>累计式神胜场不等于本期胜场。需要同一玩家前后两次有效观察，才能推算区间胜负。</p></div></div>
    <div class="detail-grid">
      <section class="panel grade-performance">
        <div class="panel-heading"><div><h2>分段位表现</h2><p>重点观察名士与大名士，按有效新增场数加权。</p></div><span class="subtle-tag">近 7 天</span></div>
        <GradeTable :rows="primaryGrades" label="名士与大名士表现"/>
        <details class="other-grades"><summary>其他段位（五至八段）<span>{{ otherGrades.length ? `${otherGrades.length} 个段位有样本` : '暂无有效样本' }}</span></summary>
          <GradeTable v-if="otherGrades.length" :rows="otherGrades" label="其他段位表现"/>
          <p v-else class="small-note">保留已采集的真实段位；有有效变化区间后，在这里展示。</p>
        </details>
        <div class="table-foot">跨段位但同计分组：{{ count(row.unassigned_grade.sample_games) }} 场，单列未分配，不归入任一段位。</div>
      </section>
      <section class="panel distribution">
        <div class="panel-heading"><div><h2>观察玩家分布</h2><p>每位玩家最近一次记录的段位</p></div></div>
        <div v-for="g in primaryCoverage" :key="g.grade" class="distribution-row"><div><span>{{ gradeNames[g.grade] }}</span><strong>{{ count(g.player_count) }}<small> 人</small></strong></div><div class="distribution-track"><span :style="{ width: `${Number(g.player_count) / maxCoverage * 100}%` }"></span></div></div>
        <details class="other-grades"><summary>其他段位玩家<span>{{ otherCoverage.reduce((n, g) => n + BigInt(g.player_count), 0n).toString() }} 人</span></summary>
          <div v-for="g in otherCoverage" :key="g.grade" class="distribution-row"><div><span>{{ gradeNames[g.grade] }}</span><strong>{{ count(g.player_count) }}<small> 人</small></strong></div><div class="distribution-track"><span :style="{ width: `${Number(g.player_count) / maxCoverage * 100}%` }"></span></div></div>
          <p v-if="!otherCoverage.length" class="small-note">尚未观察到五至八段玩家。</p>
        </details>
        <p class="small-note">这里只表示采集覆盖，不代表各段位的对局占比。</p>
      </section>
    </div>
    <section class="panel games-explanation"><div class="panel-heading"><div><h2>场数变化</h2><p>近 7 天内，同一玩家前后有效观察区间的新增胜场与负场之和。</p></div></div><p class="small-note">当前为 {{ count(row.sample_wins) }} 胜 + {{ count(row.sample_losses) }} 负 = {{ count(row.sample_games) }} 场。首次基线不计入场数，重复刷新不会重复累加。尚未采齐可比较的对局样本，登场率暂不展示。</p></section>
    <section class="panel detail-explanation"><h2>这份数据如何理解</h2><p>{{ row.method }}。</p><details><summary>规则与排除信息</summary><dl class="meta-list"><div><dt>规则版本</dt><dd>{{ row.rule_version }}</dd></div><div><dt>计算模式</dt><dd>{{ row.calculation_mode === 'observation' ? '观察推算' : '规则确认模式' }}</dd></div><div><dt>附加计分条件</dt><dd>{{ row.conditions_confirmed ? '已确认' : '仍待确认' }}</dd></div><div><dt>统计窗口</dt><dd>{{ date(row.window_start) }} — {{ date(row.window_end) }}</dd></div></dl><p v-if="!Object.keys(row.excluded_intervals).length">当前没有被排除的区间。</p><ul v-else><li v-for="(value, reason) in row.excluded_intervals" :key="reason">{{ reason }}：{{ count(value) }} 个区间</li></ul></details></section>
  </template>
  <div v-else class="empty-state panel"><h1>未找到这位式神</h1><p>该式神尚未登记，或地址中的编号不正确。</p><RouterLink to="/shikigami" class="text-button">浏览式神图鉴 <Icon name="arrow" :size="16"/></RouterLink></div>
</template>
