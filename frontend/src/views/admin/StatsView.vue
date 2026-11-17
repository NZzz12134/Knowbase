<template>
  <div class="admin-page">
    <div class="page-header"><div><span class="eyebrow">WORKSPACE INSIGHTS</span><h1>每一份知识，都在被使用</h1><p>了解知识的积累与流动，持续改善你的问答体验。</p></div><span class="insights-period">最近 30 天 · 实时概览</span></div>

    <div class="stats-grid" v-loading="loading">
        <div class="stat-card" v-for="(card,index) in cards" :key="card.label" :class="{ 'stat-card--featured': index === 2 }">
          <div class="stat-label">{{ card.label }}<span aria-hidden="true">↗</span></div>
          <div class="stat-value">{{ card.value }}</div>
        </div>
    </div>

    <el-card style="margin-top: 16px">
      <template #header><b>近 30 天问答趋势</b></template>
      <div ref="qaChartRef" role="img" aria-label="近三十天每日提问、回答与反馈趋势" style="height: 320px"></div>
    </el-card>

    <el-card style="margin-top: 16px">
      <template #header><b>各知识库文档状态分布</b></template>
      <div ref="docChartRef" role="img" aria-label="各知识库文档解析成功、失败与待处理状态分布" style="height: 300px"></div>
    </el-card>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart, BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, AriaComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { statsApi } from '../../api/admin'
echarts.use([LineChart, BarChart, GridComponent, TooltipComponent, LegendComponent, AriaComponent, CanvasRenderer])

const loading = ref(false)
const overview = ref({})
const daily = ref([])
const docStats = ref([])
const qaChartRef = ref(null)
const docChartRef = ref(null)
let qaChart = null
let docChart = null
let resizeObserver
let disposed = false
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
const number = value => value == null ? '—' : new Intl.NumberFormat('zh-CN').format(value)

function onResize() {
  qaChart?.resize()
  docChart?.resize()
}

const cards = computed(() => [
  { label: '消息总数', value: number(overview.value.message_count) },
  { label: '会话总数', value: number(overview.value.session_count) },
  { label: '累计问答', value: number(overview.value.assistant_answer_count) },
  { label: '今日提问', value: number(overview.value.today_qa) },
  { label: '知识库数', value: number(overview.value.kb_count) },
  { label: '文档总数', value: number(overview.value.document_count) },
  { label: '知识分块', value: number(overview.value.chunk_count) },
  { label: '解析成功率', value: overview.value.parse_success_rate != null ? `${overview.value.parse_success_rate}%` : '-' },
  { label: '点赞 / 点踩', value: `${overview.value.feedback_like ?? 0} / ${overview.value.feedback_dislike ?? 0}` },
])

async function fetchAll() {
  loading.value = true
  try {
    ;[overview.value, daily.value, docStats.value] = await Promise.all([
      statsApi.overview(),
      statsApi.dailyQa(),
      statsApi.documents(),
    ])
  } finally {
    loading.value = false
  }
  await nextTick()
  if (disposed) return
  renderCharts()
}

function renderCharts() {
  // 问答趋势
  qaChart = echarts.init(qaChartRef.value)
  qaChart.setOption({
    animation: !reducedMotion,
    animationDuration: 650,
    aria: { enabled: true },
    textStyle: { fontFamily: 'Segoe UI, Microsoft YaHei, sans-serif', color: '#6b776f' },
    tooltip: { trigger: 'axis' },
    legend: { data: ['提问', '回答', '点赞', '点踩'] },
    grid: { left: 40, right: 20, top: 40, bottom: 30 },
    xAxis: { type: 'category', data: daily.value.map((d) => new Intl.DateTimeFormat('zh-CN', { month: 'numeric', day: 'numeric' }).format(new Date(`${d.day}T00:00:00`))) },
    yAxis: { type: 'value', minInterval: 1 },
    series: [
      { name: '提问', type: 'line', smooth: true, areaStyle: { color: '#17634d0d' }, data: daily.value.map((d) => d.questions), itemStyle: { color: '#17634d' } },
      { name: '回答', type: 'line', smooth: true, data: daily.value.map((d) => d.answers), itemStyle: { color: '#a6bd79' } },
      { name: '点赞', type: 'bar', data: daily.value.map((d) => d.likes), itemStyle: { color: '#d0b477', borderRadius: [3,3,0,0] } },
      { name: '点踩', type: 'bar', data: daily.value.map((d) => d.dislikes), itemStyle: { color: '#c9887d', borderRadius: [3,3,0,0] } },
    ],
  })

  // 文档状态分布（堆叠柱状）
  docChart = echarts.init(docChartRef.value)
  docChart.setOption({
    animation: !reducedMotion,
    animationDuration: 650,
    aria: { enabled: true },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { data: ['成功', '失败', '解析中', '待解析'] },
    grid: { left: 40, right: 20, top: 40, bottom: 30 },
    xAxis: { type: 'category', data: docStats.value.map((d) => d.kb_name) },
    yAxis: { type: 'value', minInterval: 1 },
    series: [
      { name: '成功', type: 'bar', stack: 'total', barMaxWidth: 48, data: docStats.value.map((d) => d.statuses.succeeded || 0), itemStyle: { color: '#398367' } },
      { name: '失败', type: 'bar', stack: 'total', data: docStats.value.map((d) => d.statuses.failed || 0), itemStyle: { color: '#c9887d' } },
      { name: '解析中', type: 'bar', stack: 'total', data: docStats.value.map((d) => d.statuses.parsing || 0), itemStyle: { color: '#d0b477' } },
      { name: '待解析', type: 'bar', stack: 'total', data: docStats.value.map((d) => d.statuses.pending || 0), itemStyle: { color: '#b8c5ab' } },
    ],
  })
  resizeObserver = new ResizeObserver(onResize)
  resizeObserver.observe(qaChartRef.value)
  resizeObserver.observe(docChartRef.value)
}

onMounted(() => {
  fetchAll().catch(() => {})
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
  disposed = true
  resizeObserver?.disconnect()
  window.removeEventListener('resize', onResize)
  qaChart?.dispose()
  docChart?.dispose()
})
</script>

<style scoped>
.stats-grid { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 14px; }.stat-card { border: 1px solid var(--line); border-radius: 12px; padding: 21px 24px; background: #fff; }.stat-value { font-size: 32px; font-weight: 550; color: var(--ink); font-variant-numeric: tabular-nums; letter-spacing: -1px; margin-top: 17px; }.stat-label { font-size: 11px; color: var(--muted); display: flex; justify-content: space-between; }.stat-label>span { color: #a5b095; }.stat-card--featured { background: #1d503c; border-color: #1d503c; }.stat-card--featured .stat-label { color: #cbdbc0; }.stat-card--featured .stat-value { color: #f4f8ed; }.insights-period { font-size: 10px; color: #7b896f; padding: 8px 12px; border: 1px solid var(--line); border-radius: 20px; }
@media (max-width: 700px) { .stats-grid { grid-template-columns: repeat(2,minmax(0,1fr)); gap: 10px; }.stat-card { padding: 18px; }.stat-value { font-size: 27px; } }
</style>
