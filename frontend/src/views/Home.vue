<template>
  <!-- eslint-disable vue/multi-word-component-names -->
  <div class="home-dashboard-container">
    <!-- 欢迎横幅 -->
    <div class="welcome-banner">
      <div class="banner-content">
        <div class="banner-text">
          <h1 class="welcome-title">
            <span class="title-highlight">欢迎回来</span>
            管理员
          </h1>
          <p class="welcome-subtitle">
            江门市开平市教学质量综合评价管理平台 v1.0
          </p>
          <p class="welcome-date">
            <el-icon><Calendar /></el-icon>
            {{ currentDate }}
          </p>
        </div>
        <div class="banner-decoration">
          <div class="decoration-circle circle-1"></div>
          <div class="decoration-circle circle-2"></div>
          <div class="decoration-circle circle-3"></div>
        </div>
      </div>
    </div>

    <!-- 数据概览卡片 -->
    <el-row :gutter="20" class="stats-row">
      <el-col :xs="24" :sm="12" :md="6" :lg="6" v-for="(stat, index) in stats" :key="index">
        <el-card class="stat-card" :class="`stat-card-${index}`" shadow="hover">
          <div class="stat-content">
            <div class="stat-icon" :style="{ background: stat.iconBg }">
              <el-icon :size="32" :color="stat.iconColor">
                <component :is="stat.icon" />
              </el-icon>
            </div>
            <div class="stat-info">
              <p class="stat-label">{{ stat.label }}</p>
              <h3 class="stat-value">{{ stat.value }}</h3>
              <p class="stat-trend" :class="stat.trendClass">
                <el-icon><component :is="stat.trendIcon" /></el-icon>
                <span>{{ stat.trend }}</span>
              </p>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 主要功能区 -->
    <el-row :gutter="20" class="feature-row">
      <!-- 快速操作 -->
      <el-col :xs="24" :lg="8">
        <el-card class="feature-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <h3>
                <el-icon><Operation /></el-icon>
                快速操作
              </h3>
            </div>
          </template>
          <div class="quick-actions">
            <div 
              class="action-item" 
              v-for="(action, index) in quickActions" 
              :key="index"
              @click="handleQuickAction(action.path)"
            >
              <div class="action-icon" :style="{ background: action.bg }">
                <el-icon :color="action.color" :size="24">
                  <component :is="action.icon" />
                </el-icon>
              </div>
              <div class="action-text">
                <h4>{{ action.title }}</h4>
                <p>{{ action.desc }}</p>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- 数据分析图表 -->
      <el-col :xs="24" :lg="16">
        <el-card class="chart-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <h3>
                <el-icon><TrendCharts /></el-icon>
                教学质量趋势
              </h3>
              <el-radio-group v-model="chartPeriod" size="small">
                <el-radio-button label="week">周</el-radio-button>
                <el-radio-button label="month">月</el-radio-button>
                <el-radio-button label="quarter">季</el-radio-button>
              </el-radio-group>
            </div>
          </template>
          <div class="chart-container" ref="chartContainer" style="height: 300px"></div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 分析模块 -->
    <el-row :gutter="20" class="analysis-row">
      <el-col :xs="24" :sm="12" :md="6" :lg="6" v-for="(module, index) in analysisModules" :key="index">
        <el-card class="analysis-card" shadow="hover" @click="navigateTo(module.path)">
          <div class="analysis-content">
            <div class="analysis-icon" :style="{ background: module.bg }">
              <el-icon :color="module.color" :size="40">
                <component :is="module.icon" />
              </el-icon>
            </div>
            <div class="analysis-text">
              <h4>{{ module.title }}</h4>
              <p>{{ module.desc }}</p>
              <div class="analysis-tags">
                <el-tag 
                  v-for="(tag, tagIndex) in module.tags" 
                  :key="tagIndex"
                  size="small"
                  :type="tag.type"
                  effect="plain"
                >
                  {{ tag.label }}
                </el-tag>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 最新通知 -->
    <el-row :gutter="20" class="notice-row">
      <el-col :xs="24" :lg="12">
        <el-card class="notice-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <h3>
                <el-icon><Bell /></el-icon>
                最新通知
              </h3>
              <el-button text type="primary" size="small">查看全部</el-button>
            </div>
          </template>
          <el-timeline class="notice-timeline">
            <el-timeline-item 
              v-for="(notice, index) in notices" 
              :key="index"
              :timestamp="notice.date"
              placement="top"
              :color="notice.color"
            >
              <el-card class="notice-item-card">
                <h4>{{ notice.title }}</h4>
                <p>{{ notice.content }}</p>
              </el-card>
            </el-timeline-item>
          </el-timeline>
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="12">
        <el-card class="ranking-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <h3>
                <el-icon><Trophy /></el-icon>
                优秀学校排行榜
              </h3>
              <el-select v-model="rankingType" size="small" style="width: 120px">
                <el-option label="小学" value="primary"></el-option>
                <el-option label="初中" value="middle"></el-option>
                <el-option label="高中" value="high"></el-option>
              </el-select>
            </div>
          </template>
          <div class="ranking-list">
            <div 
              class="ranking-item" 
              v-for="(school, index) in topSchools" 
              :key="index"
            >
              <div class="ranking-number" :class="`rank-${index}`">
                {{ index + 1 }}
              </div>
              <div class="ranking-info">
                <h4>{{ school.name }}</h4>
                <p>{{ school.score }}分</p>
              </div>
              <div class="ranking-trend">
                <el-tag :type="school.trendType" size="small">
                  <el-icon><component :is="school.trendIcon" /></el-icon>
                  {{ school.trend }}
                </el-tag>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
/* eslint-disable vue/multi-word-component-names */
import { ref, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import {
  Calendar,
  School,
  User,
  Avatar,
  Document,
  Operation,
  TrendCharts,
  Bell,
  Trophy,
  ArrowUp,
  ArrowDown,
  Minus
} from '@element-plus/icons-vue'

const router = useRouter()
const chartContainer = ref(null)
const chartPeriod = ref('month')
const rankingType = ref('primary')

const currentDate = ref('')
const stats = ref([
  {
    label: '学校总数',
    value: '128',
    trend: '较上月 +12',
    trendClass: 'trend-up',
    trendIcon: ArrowUp,
    icon: School,
    iconBg: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    iconColor: '#fff'
  },
  {
    label: '教师总数',
    value: '3,456',
    trend: '较上月 +5.8%',
    trendClass: 'trend-up',
    trendIcon: ArrowUp,
    icon: User,
    iconBg: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)',
    iconColor: '#fff'
  },
  {
    label: '学生总数',
    value: '45,678',
    trend: '较上月 +8.2%',
    trendClass: 'trend-up',
    trendIcon: ArrowUp,
    icon: Avatar,
    iconBg: 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)',
    iconColor: '#fff'
  },
  {
    label: '分析报告',
    value: '1,234',
    trend: '较上月 -3.2%',
    trendClass: 'trend-down',
    trendIcon: ArrowDown,
    icon: Document,
    iconBg: 'linear-gradient(135deg, #43e97b 0%, #38f9d7 100%)',
    iconColor: '#fff'
  }
])

const quickActions = [
  {
    title: '学校增值分析',
    desc: '分析学校教学质量增值情况',
    path: '/school-value-added',
    icon: School,
    bg: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    color: '#fff'
  },
  {
    title: '教师增值分析',
    desc: '评估教师教学效果',
    path: '/teacher-value-added',
    icon: User,
    bg: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)',
    color: '#fff'
  },
  {
    title: '学生成长画像',
    desc: '构建学生个人成长档案',
    path: '/student-portrait',
    icon: Avatar,
    bg: 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)',
    color: '#fff'
  }
]

const analysisModules = [
  {
    title: '学校增值分析',
    desc: '基于多维度数据评估学校教学质量的增值效果，发现优秀学校与待改进领域',
    path: '/school-value-added',
    icon: School,
    bg: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    color: '#fff',
    tags: [
      { label: '增值评价', type: 'primary' },
      { label: '多维分析', type: 'success' }
    ]
  },
  {
    title: '教师增值分析',
    desc: '通过学业数据评估教师教学效果，识别优秀教学实践和需要支持的领域',
    path: '/teacher-value-added',
    icon: User,
    bg: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)',
    color: '#fff',
    tags: [
      { label: '教师评估', type: 'warning' },
      { label: '效果分析', type: 'info' }
    ]
  },
  {
    title: '学生成长画像',
    desc: '整合学生多维数据，构建个人成长轨迹，提供个性化学习建议',
    path: '/student-portrait',
    icon: Avatar,
    bg: 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)',
    color: '#fff',
    tags: [
      { label: '个人画像', type: 'success' },
      { label: '成长追踪', type: 'primary' }
    ]
  },
  {
    title: '特征分析',
    desc: '深度挖掘教学数据特征，发现影响教学质量的关键因素和规律',
    path: '/feature-analysis',
    icon: TrendCharts,
    bg: 'linear-gradient(135deg, #fa709a 0%, #fee140 100%)',
    color: '#fff',
    tags: [
      { label: '特征挖掘', type: 'danger' },
      { label: '数据挖掘', type: 'info' }
    ]
  }
]

const notices = ref([
  {
    title: '系统升级通知',
    content: '系统已升级至 v1.0.0 版本，新增学生成长画像功能',
    date: '2025-01-03',
    color: '#67c23a'
  },
  {
    title: '数据导入提醒',
    content: '请及时更新本学期考试成绩数据，确保评价结果准确',
    date: '2025-01-02',
    color: '#409eff'
  },
  {
    title: '分析报告发布',
    content: '2024年度教学质量分析报告已发布，请查看详情',
    date: '2025-01-01',
    color: '#e6a23c'
  }
])

const topSchools = ref([
  {
    name: '开平第一小学',
    score: '95.8',
    trend: '上升 3 位',
    trendType: 'success',
    trendIcon: ArrowUp
  },
  {
    name: '开平实验中学',
    score: '94.2',
    trend: '上升 2 位',
    trendType: 'success',
    trendIcon: ArrowUp
  },
  {
    name: '开平第一中学',
    score: '93.5',
    trend: '持平',
    trendType: 'info',
    trendIcon: Minus
  },
  {
    name: '开平第二小学',
    score: '92.8',
    trend: '下降 1 位',
    trendType: 'warning',
    trendIcon: ArrowDown
  },
  {
    name: '开平第三小学',
    score: '91.3',
    trend: '上升 5 位',
    trendType: 'success',
    trendIcon: ArrowUp
  }
])

let myChart = null

const initChart = () => {
  if (!chartContainer.value) return
  
  myChart = echarts.init(chartContainer.value)
  
  const option = {
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(50,50,50,0.7)',
      borderWidth: 0,
      textStyle: {
        color: '#fff'
      }
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'],
      axisLine: {
        lineStyle: {
          color: 'rgba(255,255,255,0.1)'
        }
      },
      axisLabel: {
        color: 'rgba(255,255,255,0.6)',
        fontSize: 12
      }
    },
    yAxis: {
      type: 'value',
      splitLine: {
        lineStyle: {
          color: 'rgba(255,255,255,0.1)'
        }
      },
      axisLabel: {
        color: 'rgba(255,255,255,0.6)',
        fontSize: 12
      }
    },
    series: [
      {
        name: '教学质量指数',
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 8,
        showSymbol: false,
        lineStyle: {
          width: 3,
          color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
            { offset: 0, color: '#4facfe' },
            { offset: 1, color: '#00f2fe' }
          ])
        },
        areaStyle: {
          opacity: 0.8,
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(79, 172, 254, 0.3)' },
            { offset: 1, color: 'rgba(0, 242, 254, 0.1)' }
          ])
        },
        data: [82, 85, 83, 88, 90, 87, 92, 95, 91, 94, 96, 98]
      }
    ]
  }
  
  myChart.setOption(option)
}

const handleQuickAction = (path) => {
  router.push(path)
}

const navigateTo = (path) => {
  router.push(path)
}

const updateDate = () => {
  const now = new Date()
  const options = {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    weekday: 'long',
    hour: '2-digit',
    minute: '2-digit'
  }
  currentDate.value = now.toLocaleDateString('zh-CN', options)
}

onMounted(async () => {
  updateDate()
  await nextTick()
  initChart()
  
  window.addEventListener('resize', () => {
    myChart?.resize()
  })
})
</script>

<style scoped>
.home-dashboard-container {
  padding: 0;
}

/* 欢迎横幅 */
.welcome-banner {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 20px;
  padding: 40px;
  margin-bottom: 30px;
  position: relative;
  overflow: hidden;
  box-shadow: 0 10px 30px rgba(102, 126, 234, 0.3);
}

.banner-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  position: relative;
  z-index: 1;
}

.banner-text {
  color: #fff;
}

.welcome-title {
  font-size: 36px;
  font-weight: 700;
  margin: 0 0 15px 0;
  letter-spacing: 2px;
}

.title-highlight {
  background: linear-gradient(90deg, #4facfe 0%, #00f2fe 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.welcome-subtitle {
  font-size: 16px;
  opacity: 0.9;
  margin: 0 0 10px 0;
  font-weight: 400;
}

.welcome-date {
  font-size: 15px;
  opacity: 0.8;
  margin: 0;
  display: flex;
  align-items: center;
  gap: 6px;
}

.banner-decoration {
  position: absolute;
  right: -50px;
  top: -50px;
}

.decoration-circle {
  position: absolute;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.1);
}

.circle-1 {
  width: 200px;
  height: 200px;
  right: 0;
  top: 0;
}

.circle-2 {
  width: 150px;
  height: 150px;
  right: 100px;
  top: 80px;
}

.circle-3 {
  width: 100px;
  height: 100px;
  right: 180px;
  top: 150px;
}

/* 统计卡片行 */
.stats-row {
  margin-bottom: 30px;
}

.stat-card {
  border-radius: 16px;
  border: none;
  transition: all 0.3s ease;
  height: 140px;
  cursor: pointer;
}

.stat-card:hover {
  transform: translateY(-8px);
  box-shadow: 0 12px 24px rgba(0, 0, 0, 0.15);
}

.stat-content {
  display: flex;
  align-items: center;
  gap: 20px;
  height: 100%;
}

.stat-icon {
  width: 70px;
  height: 70px;
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.stat-info {
  flex: 1;
  color: #2c3e50;
}

.stat-label {
  font-size: 14px;
  color: #606266;
  margin: 0 0 8px 0;
  font-weight: 500;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  margin: 0 0 8px 0;
  background: linear-gradient(90deg, #2c3e50 0%, #409eff 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.stat-trend {
  font-size: 13px;
  margin: 0;
  display: flex;
  align-items: center;
  gap: 4px;
}

.trend-up {
  color: #67c23a;
}

.trend-down {
  color: #f56c6c;
}

/* 功能区 */
.feature-row {
  margin-bottom: 30px;
}

.feature-card {
  border-radius: 16px;
  border: none;
  height: 100%;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 0;
}

.card-header h3 {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 18px;
  font-weight: 600;
  color: #2c3e50;
  margin: 0;
}

.card-header .el-icon {
  color: #409eff;
}

/* 快速操作 */
.quick-actions {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.action-item {
  display: flex;
  align-items: center;
  gap: 15px;
  padding: 15px;
  border-radius: 12px;
  background: #f8f9fa;
  cursor: pointer;
  transition: all 0.3s ease;
  border: 1px solid transparent;
}

.action-item:hover {
  background: #ecf5ff;
  border-color: #409eff;
  transform: translateX(8px);
}

.action-icon {
  width: 50px;
  height: 50px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.action-text {
  flex: 1;
}

.action-text h4 {
  font-size: 15px;
  font-weight: 600;
  color: #2c3e50;
  margin: 0 0 4px 0;
}

.action-text p {
  font-size: 13px;
  color: #909399;
  margin: 0;
}

/* 图表卡片 */
.chart-card {
  border-radius: 16px;
  border: none;
  height: 100%;
}

.chart-container {
  width: 100%;
}

/* 分析模块行 */
.analysis-row {
  margin-bottom: 30px;
}

.analysis-card {
  border-radius: 16px;
  border: none;
  height: 100%;
  cursor: pointer;
  transition: all 0.3s ease;
  overflow: hidden;
}

.analysis-card:hover {
  transform: translateY(-8px);
  box-shadow: 0 12px 24px rgba(0, 0, 0, 0.15);
}

.analysis-content {
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.analysis-icon {
  width: 70px;
  height: 70px;
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  align-self: flex-start;
}

.analysis-text {
  flex: 1;
}

.analysis-text h4 {
  font-size: 17px;
  font-weight: 600;
  color: #2c3e50;
  margin: 0 0 8px 0;
}

.analysis-text p {
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
  margin: 0 0 12px 0;
}

.analysis-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

/* 通知行 */
.notice-row {
  margin-bottom: 30px;
}

.notice-card {
  border-radius: 16px;
  border: none;
  height: 100%;
}

.notice-timeline {
  padding: 10px 0;
}

.notice-item-card {
  background: #f8f9fa;
  border: none;
  padding: 15px;
  margin-bottom: 0;
}

.notice-item-card h4 {
  font-size: 14px;
  font-weight: 600;
  color: #2c3e50;
  margin: 0 0 8px 0;
}

.notice-item-card p {
  font-size: 13px;
  color: #606266;
  margin: 0;
}

/* 排行榜样行 */
.ranking-card {
  border-radius: 16px;
  border: none;
  height: 100%;
}

.ranking-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 10px 0;
}

.ranking-item {
  display: flex;
  align-items: center;
  gap: 15px;
  padding: 12px;
  border-radius: 10px;
  background: #f8f9fa;
  transition: all 0.3s ease;
}

.ranking-item:hover {
  background: #ecf5ff;
  transform: translateX(8px);
}

.ranking-number {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 14px;
  color: #fff;
  flex-shrink: 0;
}

.rank-0 {
  background: linear-gradient(135deg, #ffd700 0%, #ffec8b 100%);
}

.rank-1 {
  background: linear-gradient(135deg, #c0c0c0 0%, #808080 100%);
}

.rank-2 {
  background: linear-gradient(135deg, #b87333 0%, #cd7f32 100%);
}

.ranking-number:not([class*="rank-"]) {
  background: #909399;
}

.ranking-info {
  flex: 1;
}

.ranking-info h4 {
  font-size: 15px;
  font-weight: 600;
  color: #2c3e50;
  margin: 0 0 4px 0;
}

.ranking-info p {
  font-size: 14px;
  color: #409eff;
  font-weight: 600;
  margin: 0;
}

/* 响应式设计 */
@media (max-width: 1200px) {
  .welcome-title {
    font-size: 30px;
  }
  
  .stat-value {
    font-size: 24px;
  }
  
  .analysis-text h4 {
    font-size: 15px;
  }
}

@media (max-width: 768px) {
  .welcome-banner {
    padding: 25px;
  }
  
  .banner-decoration {
    display: none;
  }
  
  .banner-content {
    flex-direction: column;
    align-items: flex-start;
    gap: 20px;
  }
  
  .welcome-title {
    font-size: 24px;
  }
  
  .stat-card {
    height: auto;
    padding: 15px;
  }
  
  .stat-content {
    flex-direction: column;
    text-align: center;
  }
}
</style>
