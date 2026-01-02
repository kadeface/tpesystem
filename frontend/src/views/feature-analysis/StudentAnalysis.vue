<template>
  <div class="student-analysis">
    <!-- 导航栏 -->
    <feature-navigation 
      :current-level="4" 
      :exam-id="examId" 
      :class-id="classId" 
    />
    
    <el-card>
      <template #header>
        <div class="card-header">
          <span>学生特征分析</span>
        </div>
      </template>
      <div class="placeholder-content">
        <el-alert
          title="学生特征分析模块正在开发中"
          type="info"
          :closable="false"
          show-icon
        />
      </div>
    </el-card>
  </div>
</template>

<script>
import FeatureNavigation from '@/components/feature-analysis/FeatureNavigation.vue';

export default {
  name: 'StudentAnalysis',
  components: {
    FeatureNavigation
  },
  props: {
    examId: {
      type: String,
      required: true
    },
    classId: {
      type: String,
      default: null
    }
  }
};
</script>

<style scoped>
.student-analysis {
  padding: 10px 0;
}
.placeholder-content {
  min-height: 300px;
  display: flex;
  justify-content: center;
  align-items: center;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style> 