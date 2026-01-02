<template>
  <div class="exam-selector">
    <el-form :inline="true">
      <el-form-item label="年级:">
        <el-select 
          v-model="selectedGrade" 
          placeholder="选择年级"
          @change="handleGradeChange"
          size="large"
        >
          <el-option
            v-for="grade in grades"
            :key="grade.grade_id"
            :label="grade.grade_name"
            :value="grade.grade_id"
          ></el-option>
        </el-select>
        <div class="helper-text">可选，不选则处理所有年级</div>
      </el-form-item>
      
      <el-form-item v-if="!showTimeline" label="考试:">
        <el-select 
          v-model="selectedExam" 
          placeholder="选择考试"
          @change="handleExamChange"
          size="large"
          :loading="loadingExams"
          :disabled="!selectedGrade || loadingExams"
        >
          <el-option
            v-for="exam in exams"
            :key="exam.exam_id"
            :label="exam.exam_name"
            :value="exam.exam_id"
          ></el-option>
        </el-select>
        <div class="helper-text">选择要分析的考试</div>
      </el-form-item>
    </el-form>
    
    <!-- 时间轴区域 -->
    <div v-if="showTimeline && exams.length > 0" class="timeline-container">
      <div class="timeline-header">
        <h4>学习历程时间轴</h4>
        <el-tooltip content="通过时间轴可以直观查看学习进程，点击时间点进入对应考试分析" placement="top">
          <el-icon><question-filled /></el-icon>
        </el-tooltip>
      </div>
      
      <div class="timeline">
        <div 
          v-for="exam in exams" 
          :key="exam.exam_id"
          class="timeline-item"
        >
          <div 
            class="time-point" 
            :class="{ active: selectedExam === exam.exam_id }"
            @click="selectExam(exam.exam_id)"
          >
            {{ formatDate(exam.exam_date) }}
          </div>
          <div class="exam-name">{{ exam.exam_name }}</div>
        </div>
      </div>
      
      <div class="exam-action" v-if="selectedExam">
        <el-button type="primary" @click="enterAnalysis">
          进入特征分析 <el-icon><arrow-right /></el-icon>
        </el-button>
      </div>
    </div>
    
    <!-- 提示信息 -->
    <div v-if="selectedGrade && exams.length === 0 && !loadingExams" class="no-exams-tip">
      <el-empty description="该年级暂无可分析的考试数据" :image-size="100">
        <template #image>
          <el-icon style="font-size: 60px; color: #909399;"><data-analysis /></el-icon>
        </template>
      </el-empty>
    </div>
  </div>
</template>

<script>
import featureAnalysisApi from '@/api/feature-analysis-api';
import { QuestionFilled, ArrowRight, DataAnalysis } from '@element-plus/icons-vue';

export default {
  name: 'ExamSelector',
  components: {
    QuestionFilled,
    ArrowRight,
    DataAnalysis
  },
  props: {
    value: {
      type: String,
      default: null
    }
  },
  data() {
    return {
      grades: [],
      exams: [],
      selectedGrade: null,
      selectedExam: this.value,
      loadingGrades: false,
      loadingExams: false,
      showTimeline: true // 默认显示时间轴
    };
  },
  watch: {
    value(newVal) {
      this.selectedExam = newVal;
    }
  },
  created() {
    this.fetchGrades();
  },
  methods: {
    async fetchGrades() {
      this.loadingGrades = true;
      try {
        // 这里使用现有的API获取年级列表
        const response = await this.$api.getGrades();
        this.grades = response.data || [];
        
        if (this.grades.length > 0) {
          this.selectedGrade = this.grades[0].grade_id;
          this.fetchExams();
        }
      } catch (error) {
        console.error('获取年级数据失败:', error);
      } finally {
        this.loadingGrades = false;
      }
    },
    
    async fetchExams() {
      if (!this.selectedGrade) return;
      
      this.loadingExams = true;
      try {
        const response = await featureAnalysisApi.getAnalyzableExams({
          grade_id: this.selectedGrade
        });
        
        // 添加日期信息用于时间轴展示
        this.exams = (response.data || []).map(exam => ({
          ...exam,
          exam_date: exam.exam_date || new Date().toISOString().split('T')[0]
        })).sort((a, b) => new Date(a.exam_date) - new Date(b.exam_date));
        
        // 如果当前选择的考试不在列表中，重置选择
        if (this.selectedExam && !this.exams.find(e => e.exam_id === this.selectedExam)) {
          this.selectedExam = null;
        }
        
        // 如果没有选择考试且有可用考试，选择第一个
        if (!this.selectedExam && this.exams.length > 0) {
          this.selectedExam = this.exams[0].exam_id;
          this.handleExamChange(this.selectedExam);
        }
      } catch (error) {
        console.error('获取考试数据失败:', error);
      } finally {
        this.loadingExams = false;
      }
    },
    
    handleGradeChange() {
      this.selectedExam = null;
      this.fetchExams();
    },
    
    selectExam(examId) {
      this.selectedExam = examId;
      this.handleExamChange(examId);
    },
    
    handleExamChange(examId) {
      this.$emit('input', examId);
      this.$emit('change', examId);
    },
    
    enterAnalysis() {
      if (this.selectedExam) {
        this.$emit('enter-analysis', this.selectedExam);
        // 这里的导航逻辑已经在 FeatureAnalysisHome 中实现
      }
    },
    
    formatDate(dateString) {
      if (!dateString) return '未知';
      
      const date = new Date(dateString);
      const year = date.getFullYear();
      const month = date.getMonth() + 1;
      const day = date.getDate();
      
      return `${year}年${month}月${day}日`;
    }
  }
};
</script>

<style scoped>
.exam-selector {
  margin-bottom: 30px;
  background-color: #f8f9fa;
  padding: 20px;
  border-radius: 8px;
}

.helper-text {
  color: #909399;
  font-size: 12px;
  margin-top: 5px;
}

/* 时间轴样式 */
.timeline-container {
  margin-top: 20px;
  padding: 15px;
  border: 1px solid #ddd;
  border-radius: 5px;
  background-color: white;
}

.timeline-header {
  display: flex;
  align-items: center;
  margin-bottom: 15px;
}

.timeline-header h4 {
  margin: 0;
  margin-right: 10px;
}

.timeline {
  display: flex;
  justify-content: space-between;
  margin: 20px 0;
  position: relative;
  overflow-x: auto;
  padding: 0 10px;
}

.timeline::before {
  content: "";
  position: absolute;
  top: 15px;
  left: 15px;
  right: 15px;
  height: 2px;
  background-color: #ddd;
  z-index: 1;
}

.timeline-item {
  position: relative;
  z-index: 2;
  display: flex;
  flex-direction: column;
  align-items: center;
  margin: 0 15px;
  min-width: 80px;
}

.time-point {
  width: 30px;
  height: 30px;
  background-color: #f8f9fa;
  border: 1px solid #ddd;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.3s;
  margin-bottom: 8px;
}

.time-point:hover {
  background-color: #e9ecef;
}

.time-point.active {
  background-color: #409EFF;
  color: white;
  border-color: #409EFF;
}

.exam-name {
  font-size: 12px;
  text-align: center;
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.exam-action {
  margin-top: 20px;
  text-align: center;
}

.no-exams-tip {
  margin-top: 30px;
  text-align: center;
}
</style> 