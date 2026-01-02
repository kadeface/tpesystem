<template>
  <div class="feature-analysis-home">
    <h2>考试分层特征分析</h2>
    
    <p class="description">
      本模块提供基于分层特征数据的多维度分析功能，帮助教育工作者了解考试在区域、学校、班级和学生层面的表现情况，
      发现教育教学中的问题和优势，为教育决策和个性化教学提供数据支持。
    </p>
    
    <!-- 考试选择器 -->
    <exam-selector 
      v-model="selectedExamId"
      @change="handleExamChange"
      @enter-analysis="navigateToAnalysis"
    />
    
    <!-- 主内容区 -->
    <div class="analysis-content" v-if="selectedExamId">
      <router-view :key="$route.fullPath"></router-view>
    </div>
    
    <!-- 未选择考试的提示 -->
    <div class="empty-state" v-else>
      <el-empty description="请选择要分析的考试">
        <template #image>
          <el-icon style="font-size: 80px; color: #909399;">
            <data-analysis />
          </el-icon>
        </template>
      </el-empty>
    </div>
  </div>
</template>

<script>
import ExamSelector from '@/components/feature-analysis/ExamSelector.vue';
import { DataAnalysis } from '@element-plus/icons-vue';

export default {
  name: 'FeatureAnalysisHome',
  components: {
    ExamSelector,
    DataAnalysis
  },
  data() {
    return {
      selectedExamId: null
    };
  },
  created() {
    // 如果路由中有考试ID，则使用路由中的
    const routeExamId = this.$route.params.examId;
    if (routeExamId) {
      this.selectedExamId = routeExamId;
    }
  },
  methods: {
    handleExamChange(examId) {
      // 这里只更新选中的考试ID，不进行导航
      this.selectedExamId = examId;
    },
    
    navigateToAnalysis(examId) {
      // 用户点击"进入特征分析"按钮时执行导航
      let targetName = 'DistrictAnalysis';
      
      if (this.$route.name === 'FeatureAnalysis') {
        // 如果在主页，默认跳转到区级分析
        this.$router.push({ 
          name: targetName,
          params: { examId: examId }
        });
      } else {
        // 否则在当前层级更新考试ID
        this.$router.push({
          name: this.$route.name,
          params: { 
            ...this.$route.params,
            examId: examId
          }
        });
      }
    }
  }
};
</script>

<style scoped>
.feature-analysis-home {
  padding: 20px;
}

.description {
  max-width: 800px;
  margin-bottom: 30px;
  color: #606266;
  line-height: 1.6;
}

.analysis-content {
  margin-top: 20px;
  min-height: 500px;
}

.empty-state {
  margin-top: 100px;
  text-align: center;
}
</style> 