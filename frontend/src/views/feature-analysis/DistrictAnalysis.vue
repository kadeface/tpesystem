<template>
  <div class="district-analysis">
    <!-- 导航栏 -->
    <feature-navigation :current-level="1" :exam-id="examId" />
    
    <!-- 加载状态 -->
    <div v-if="loading" class="loading-container">
      <el-skeleton style="width: 100%" animated :rows="10" />
    </div>
    
    <div v-else-if="error" class="error-container">
      <el-result
        icon="error"
        title="加载失败"
        :sub-title="error"
      >
        <template #extra>
          <el-button type="primary" @click="fetchDistrictFeature">重试</el-button>
        </template>
      </el-result>
    </div>
    
    <div v-else-if="districtFeature" class="analysis-content">
      <!-- 区级总览面板 -->
      <el-row :gutter="20">
        <el-col :span="6">
          <stat-card 
            title="考试总人数" 
            :value="districtFeature.total_students" 
            icon="user"
            color="#409EFF" 
          />
        </el-col>
        <el-col :span="6">
          <stat-card 
            title="考试平均分" 
            :value="formatScore(districtFeature.avg_score)" 
            icon="data-analysis"
            color="#67C23A" 
          />
        </el-col>
        <el-col :span="6">
          <stat-card 
            title="最高分" 
            :value="formatScore(districtFeature.max_score)" 
            icon="top"
            color="#E6A23C" 
          />
        </el-col>
        <el-col :span="6">
          <stat-card 
            title="最低分" 
            :value="formatScore(districtFeature.min_score)" 
            icon="bottom"
            color="#F56C6C" 
          />
        </el-col>
      </el-row>
      
      <!-- 分析图表面板 -->
      <el-row :gutter="20" class="chart-row">
        <!-- 分数分布图 -->
        <el-col :span="12">
          <el-card class="chart-card">
            <template #header>
              <div class="card-header">
                <span>考试分数分布</span>
              </div>
            </template>
            <div class="chart-container" id="score-distribution-chart"></div>
          </el-card>
        </el-col>
        
        <!-- 学科分析图 -->
        <el-col :span="12">
          <el-card class="chart-card">
            <template #header>
              <div class="card-header">
                <span>学科平均分</span>
              </div>
            </template>
            <div class="chart-container" id="subject-avg-chart"></div>
          </el-card>
        </el-col>
      </el-row>
      
      <!-- 学校汇总表格 -->
      <el-card class="data-card">
        <template #header>
          <div class="card-header">
            <span>学校成绩汇总</span>
            <el-button 
              type="primary" 
              size="small" 
              @click="navigateToSchoolAnalysis"
            >查看详细分析</el-button>
          </div>
        </template>
        
        <el-table :data="schoolsData" stripe style="width: 100%" height="400">
          <el-table-column prop="rank" label="排名" width="80" />
          <el-table-column prop="school_name" label="学校名称" />
          <el-table-column prop="avg_score" label="平均分" sortable />
          <el-table-column prop="max_score" label="最高分" sortable />
          <el-table-column prop="std_dev" label="标准差" sortable />
          <el-table-column prop="student_count" label="学生数" sortable />
          <el-table-column label="操作" width="150">
            <template #default="scope">
              <el-button 
                type="text" 
                size="small" 
                @click="navigateToSchoolDetail(scope.row.school_id)"
              >详情</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </div>
  </div>
</template>

<script>
import FeatureNavigation from '@/components/feature-analysis/FeatureNavigation.vue';
import StatCard from '@/components/common/StatCard.vue';
import featureAnalysisApi from '@/api/feature-analysis-api';
import * as echarts from 'echarts';

export default {
  name: 'DistrictAnalysis',
  components: {
    FeatureNavigation,
    StatCard
  },
  props: {
    examId: {
      type: String,
      required: true
    }
  },
  data() {
    return {
      loading: true,
      error: null,
      districtFeature: null,
      schoolsData: [],
      charts: {}
    };
  },
  created() {
    this.fetchDistrictFeature();
  },
  beforeUnmount() {
    // 销毁图表实例
    Object.values(this.charts).forEach(chart => {
      if (chart && chart.dispose) {
        chart.dispose();
      }
    });
  },
  methods: {
    async fetchDistrictFeature() {
      this.loading = true;
      this.error = null;
      
      try {
        // 获取区级特征数据
        const response = await featureAnalysisApi.getDistrictFeature(this.examId);
        this.districtFeature = response.data;
        
        // 获取学校特征数据
        const schoolsResponse = await featureAnalysisApi.getSchoolFeatures(this.examId);
        this.schoolsData = schoolsResponse.data.map((school, index) => ({
          ...school,
          rank: index + 1
        }));
        
        // 在下一个DOM更新周期渲染图表
        this.$nextTick(() => {
          this.renderCharts();
        });
      } catch (error) {
        console.error('获取区级特征数据失败:', error);
        this.error = '加载数据失败，请稍后再试';
      } finally {
        this.loading = false;
      }
    },
    
    formatScore(score) {
      return Number(score).toFixed(1);
    },
    
    renderCharts() {
      this.renderScoreDistribution();
      this.renderSubjectAvgChart();
    },
    
    renderScoreDistribution() {
      const chartDom = document.getElementById('score-distribution-chart');
      if (!chartDom) return;
      
      const chart = echarts.init(chartDom);
      this.charts.scoreDistribution = chart;
      
      // 模拟分数分布数据
      // 实际项目中应该从API获取
      const bins = [
        {score: '0-10', count: 5},
        {score: '10-20', count: 15},
        {score: '20-30', count: 25},
        {score: '30-40', count: 50},
        {score: '40-50', count: 80},
        {score: '50-60', count: 120},
        {score: '60-70', count: 180},
        {score: '70-80', count: 220},
        {score: '80-90', count: 150},
        {score: '90-100', count: 80}
      ];
      
      const option = {
        tooltip: {
          trigger: 'axis',
          axisPointer: {
            type: 'shadow'
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
          data: bins.map(bin => bin.score)
        },
        yAxis: {
          type: 'value',
          name: '学生数量'
        },
        series: [
          {
            name: '学生数量',
            type: 'bar',
            data: bins.map(bin => bin.count),
            itemStyle: {
              color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                { offset: 0, color: '#83bff6' },
                { offset: 0.5, color: '#188df0' },
                { offset: 1, color: '#188df0' }
              ])
            }
          }
        ]
      };
      
      chart.setOption(option);
      
      // 添加窗口大小变化监听
      window.addEventListener('resize', () => {
        chart.resize();
      });
    },
    
    renderSubjectAvgChart() {
      const chartDom = document.getElementById('subject-avg-chart');
      if (!chartDom) return;
      
      const chart = echarts.init(chartDom);
      this.charts.subjectAvg = chart;
      
      // 从区级特征获取学科平均分
      // 实际项目中应确保数据格式正确
      const subjectData = this.districtFeature.subject_avg_scores || {};
      const subjects = Object.keys(subjectData);
      const scores = subjects.map(subject => subjectData[subject]);
      
      const option = {
        tooltip: {
          trigger: 'axis',
          axisPointer: {
            type: 'shadow'
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
          data: subjects
        },
        yAxis: {
          type: 'value',
          name: '平均分',
          min: function(value) {
            return Math.max(0, value.min - 10);
          }
        },
        series: [
          {
            name: '平均分',
            type: 'bar',
            data: scores,
            itemStyle: {
              color: function(params) {
                // 不同学科不同颜色
                const colorList = [
                  '#c23531', '#2f4554', '#61a0a8', 
                  '#d48265', '#91c7ae', '#749f83', 
                  '#ca8622', '#bda29a', '#6e7074'
                ];
                return colorList[params.dataIndex % colorList.length];
              }
            },
            label: {
              show: true,
              position: 'top',
              formatter: '{c}'
            }
          }
        ]
      };
      
      chart.setOption(option);
      
      // 添加窗口大小变化监听
      window.addEventListener('resize', () => {
        chart.resize();
      });
    },
    
    navigateToSchoolAnalysis() {
      this.$router.push({
        name: 'SchoolAnalysis',
        params: { examId: this.examId }
      });
    },
    
    navigateToSchoolDetail(schoolId) {
      this.$router.push({
        name: 'SchoolAnalysis',
        params: { 
          examId: this.examId,
          schoolId: schoolId
        }
      });
    }
  }
};
</script>

<style scoped>
.district-analysis {
  padding: 10px 0;
}

.loading-container, .error-container {
  padding: 20px;
  margin-top: 20px;
}

.chart-row {
  margin-top: 20px;
}

.chart-card {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.chart-container {
  height: 300px;
}

.data-card {
  margin-top: 20px;
}
</style> 