<template>
  <div class="example-view">
    <h2>教育数据示例</h2>
    
    <!-- 年级选择器 -->
    <el-card class="section-card">
      <template #header>
        <div class="card-header">
          <span>步骤1: 选择年级</span>
        </div>
      </template>
      <grade-selector @grade-selected="onGradeSelected" />
    </el-card>
    
    <!-- 考试选择器 -->
    <el-card class="section-card" v-if="selectedGrade">
      <template #header>
        <div class="card-header">
          <span>步骤2: 选择考试</span>
        </div>
      </template>
      <exam-selector 
        :selected-grade="selectedGrade" 
        @exam-selected="onExamSelected" 
      />
    </el-card>
    
    <!-- 选中的考试信息 -->
    <el-card class="section-card" v-if="selectedExam">
      <template #header>
        <div class="card-header">
          <span>步骤3: 已选择考试</span>
        </div>
      </template>
      <div class="selected-exam-info">
        <h3>{{ selectedExam.exam_name || selectedExam.exam_id }}</h3>
        <pre>{{ JSON.stringify(selectedExam, null, 2) }}</pre>
      </div>
    </el-card>
    
    <!-- 调试信息 -->
    <el-card class="section-card" v-if="debugging">
      <template #header>
        <div class="card-header">
          <span>调试信息</span>
        </div>
      </template>
      <pre>{{ debugInfo }}</pre>
    </el-card>
  </div>
</template>

<script>
import GradeSelector from '@/components/GradeSelector.vue'
import ExamSelector from '@/components/ExamSelector.vue'
import educationDataApi from '@/api/education-data'

export default {
  components: {
    GradeSelector,
    ExamSelector
  },
  data() {
    return {
      debugging: true,
      debugInfo: null,
      selectedGrade: null,
      selectedExam: null
    }
  },
  created() {
    this.$api = this.$api || educationDataApi;
  },
  methods: {
    onGradeSelected(grade) {
      console.log('选择年级:', grade);
      this.selectedGrade = grade;
      this.selectedExam = null; // 清除已选择的考试
      this.debugInfo = { type: 'grade', data: grade };
    },
    onExamSelected(exam) {
      console.log('选择考试:', exam);
      this.selectedExam = exam;
      this.debugInfo = { type: 'exam', data: exam };
    }
  }
}
</script>

<style scoped>
.example-view {
  max-width: 1000px;
  margin: 0 auto;
  padding: 20px;
}

.section-card {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.selected-exam-info {
  padding: 10px;
  background-color: #f8f9fa;
  border-radius: 4px;
}

pre {
  white-space: pre-wrap;
  background-color: #f8f9fa;
  padding: 10px;
  border-radius: 4px;
  max-height: 300px;
  overflow: auto;
}
</style> 