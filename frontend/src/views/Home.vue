<template>
  <div class="home-page">
    <el-row :gutter="20">
      <el-col :span="24">
        <div class="welcome-banner">
          <h1>欢迎使用江门市开平市教学质量综合评价管理平台</h1>
          <p>集成学校增值、教师增值与学生成长画像的综合分析系统</p>
        </div>
      </el-col>
    </el-row>
    
    <el-row :gutter="20" class="feature-cards">
      <el-col :span="8">
        <el-card class="feature-card">
          <template #header>
            <h3>学校增值分析</h3>
          </template>
          <div class="feature-content">
            <i class="el-icon-school"></i>
            <p>基于多种统计模型，客观评价学校教育质量，发现优势与不足</p>
            <el-button type="primary" @click="$router.push('/school-value-added')">开始分析</el-button>
          </div>
        </el-card>
      </el-col>
      
      <el-col :span="8">
        <el-card class="feature-card">
          <template #header>
            <h3>教师增值分析</h3>
          </template>
          <div class="feature-content">
            <i class="el-icon-user"></i>
            <p>深入剖析教师教学效能，支持个性化教学改进建议</p>
            <el-button type="primary" @click="$router.push('/teacher-value-added')">开始分析</el-button>
          </div>
        </el-card>
      </el-col>
      
      <el-col :span="8">
        <el-card class="feature-card">
          <template #header>
            <h3>学生成长画像</h3>
          </template>
          <div class="feature-content">
            <i class="el-icon-data-analysis"></i>
            <p>通过聚类分析，揭示学生成长轨迹与模式，提供精准辅导方案</p>
            <el-button type="primary" @click="$router.push('/student-portrait')">开始分析</el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>
    
    <el-row :gutter="20" class="dashboard-section">
      <el-col :span="16">
        <el-card class="dashboard-card">
          <template #header>
            <div class="dashboard-header">
              <h3>最近分析结果</h3>
              <el-button type="text" @click="$router.push('/results')">查看全部</el-button>
            </div>
          </template>
          <el-table :data="recentReports" stripe style="width: 100%">
            <el-table-column prop="date" label="日期" width="180"></el-table-column>
            <el-table-column prop="type" label="分析类型" width="180"></el-table-column>
            <el-table-column prop="name" label="名称"></el-table-column>
            <el-table-column label="操作" width="120">
              <template #default="scope">
                <el-button type="text" size="small" @click="viewReport(scope.row)">查看</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
      
      <el-col :span="8">
        <el-card class="stats-card">
          <template #header>
            <h3>平台数据统计</h3>
          </template>
          <div class="stats-content">
            <div class="stat-item">
              <div class="stat-value">{{ stats.schools }}</div>
              <div class="stat-label">学校数量</div>
            </div>
            <div class="stat-item">
              <div class="stat-value">{{ stats.teachers }}</div>
              <div class="stat-label">教师数量</div>
            </div>
            <div class="stat-item">
              <div class="stat-value">{{ stats.students }}</div>
              <div class="stat-label">学生数量</div>
            </div>
            <div class="stat-item">
              <div class="stat-value">{{ stats.reports }}</div>
              <div class="stat-label">分析报告</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script>
export default {
  name: 'HomePage',
  data() {
    return {
      recentReports: [
        { date: '2024-04-08', type: '学校增值', name: '2024年春季学期期中考试分析' },
        { date: '2024-04-06', type: '教师增值', name: '高三数学教师教学效能分析' },
        { date: '2024-04-05', type: '学生画像', name: '八年级学生学习模式分析' }
      ],
      stats: {
        schools: 116,
        teachers: 6164,
        students: 81572,
        reports: 215
      }
    }
  },
  methods: {
    viewReport(report) {
      console.log('查看报告:', report.name);
      this.$router.push({
        path: '/results',
        query: { 
          id: report.id,
          type: report.type 
        }
      });
    }
  }
}
</script>

<style scoped>
.home-page {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px 0;
}

.welcome-banner {
  background: linear-gradient(135deg, #1976d2, #2196f3);
  color: white;
  padding: 30px;
  border-radius: 4px;
  text-align: center;
  margin-bottom: 30px;
}

.welcome-banner h1 {
  margin-top: 0;
  font-size: 28px;
}

.feature-cards {
  margin-bottom: 30px;
}

.feature-card {
  height: 100%;
}

.feature-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 10px 0;
}

.feature-content i {
  font-size: 50px;
  margin-bottom: 20px;
  color: #409EFF;
}

.feature-content p {
  margin-bottom: 20px;
  height: 60px;
}

.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.dashboard-section {
  margin-bottom: 30px;
}

.stats-content {
  display: flex;
  flex-wrap: wrap;
}

.stat-item {
  width: 50%;
  text-align: center;
  padding: 15px 0;
}

.stat-value {
  font-size: 24px;
  font-weight: bold;
  color: #409EFF;
}

.stat-label {
  color: #606266;
  margin-top: 5px;
}
</style> 