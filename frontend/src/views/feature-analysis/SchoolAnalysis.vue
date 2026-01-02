<template>
  <div class="school-analysis">
    <!-- 导航栏 -->
    <feature-navigation 
      :current-level="2" 
      :exam-id="examId" 
      :district-id="districtId" 
    />
    
    <el-card>
      <template #header>
        <div class="card-header">
          <span>学校特征分析</span>
        </div>
      </template>
      <div class="placeholder-content">
        <el-alert
          title="学校特征分析模块正在开发中"
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
  name: 'SchoolAnalysis',
  components: {
    FeatureNavigation
  },
  props: {
    examId: {
      type: String,
      required: true
    },
    districtId: {
      type: String,
      default: null
    }
  }
};
</script>

<style scoped>
.school-analysis {
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