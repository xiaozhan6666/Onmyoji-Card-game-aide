<script setup lang="ts">
import { count, percent, type GradeStats } from '../data'
defineProps<{ rows: GradeStats[]; label: string }>()
</script>
<template>
  <div class="table-wrap"><table :aria-label="label">
    <thead><tr><th>段位</th><th>样本胜率</th><th>胜 / 负</th><th>新增场数</th><th>参与玩家</th></tr></thead>
    <tbody><tr v-for="g in rows" :key="g.grade!">
      <td><span class="grade-seal">{{ g.grade! < 9 ? g.grade : g.grade === 9 ? '名' : '大' }}</span><strong>{{ g.grade_name }}</strong></td>
      <td class="rate">{{ percent(g.win_rate) }}</td>
      <td class="numeric">{{ count(g.sample_wins) }} / {{ count(g.sample_losses) }}</td>
      <td class="numeric">{{ count(g.sample_games) }}</td>
      <td class="numeric">{{ count(g.contributing_players) }}</td>
    </tr></tbody>
  </table></div>
</template>
