<template>
  <div class="feature-navigation">
    <!-- 筛选条件区 -->
    <div class="filter-panel">
      <div class="filter-row">
        <div class="filter-item">
          <span class="filter-label">年级:</span>
          <el-select 
            v-model="selectedGrade" 
            placeholder="选择年级"
            @change="handleGradeChange"
            size="large"
            style="width: 180px;"
          >
            <el-option
              v-for="grade in grades"
              :key="grade.grade_id"
              :label="grade.grade_name"
              :value="grade.grade_id"
            ></el-option>
          </el-select>
          <div class="filter-help">可选，不选则处理所有年级</div>
        </div>
      </div>
      
      <div class="filter-row">
        <div class="filter-item">
          <span class="filter-label">考试:</span>
          <el-select 
            v-model="selectedExam" 
            placeholder="选择考试"
            @change="handleExamChange"
            size="large"
            style="width: 180px;"
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
          <div class="filter-help">可选，不选则处理所有考试</div>
        </div>
      </div>
      
      <!-- 时间轴区域 -->
      <div v-if="showTimeline" class="timeline-container">
        <h4>学习历程时间轴</h4>
        <div class="timeline">
          <div 
            v-for="exam in timelineExams" 
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
          </div>
        </div>
      </div>
    </div>
    
    <!-- 分析层级切换 -->
    <div class="level-tabs">
      <el-radio-group v-model="activeLevel" @change="handleLevelChange">
        <el-radio-button :label="1">区级</el-radio-button>
        <el-radio-button :label="2">学校</el-radio-button>
        <el-radio-button :label="3">班级</el-radio-button>
        <el-radio-button :label="4">学生</el-radio-button>
      </el-radio-group>
    </div>
    
    <!-- 导航路径 -->
    <div class="breadcrumb-container">
      <el-breadcrumb separator="/">
        <el-breadcrumb-item :to="{ name: 'FeatureAnalysis' }">特征分析</el-breadcrumb-item>
        <el-breadcrumb-item 
          v-if="currentLevel >= 1" 
          :to="{ name: 'DistrictAnalysis', params: { examId: examId } }"
        >区级分析</el-breadcrumb-item>
        <el-breadcrumb-item 
          v-if="currentLevel >= 2" 
          :to="{ name: 'SchoolAnalysis', params: { examId: examId, districtId: districtId } }"
        >学校分析</el-breadcrumb-item>
        <el-breadcrumb-item 
          v-if="currentLevel >= 3" 
          :to="{ name: 'ClassAnalysis', params: { examId: examId, schoolId: schoolId } }"
        >班级分析</el-breadcrumb-item>
        <el-breadcrumb-item 
          v-if="currentLevel >= 4"
        >学生分析</el-breadcrumb-item>
      </el-breadcrumb>
    </div>
  </div>
</template>

<script>
import featureAnalysisApi from '@/api/feature-analysis-api';

export default {
  name: 'FeatureNavigation',
  props: {
    currentLevel: {
      type: Number,
      required: true
    },
    examId: {
      type: String,
      default: null
    },
    districtId: {
      type: String,
      default: null
    },
    schoolId: {
      type: String,
      default: null
    },
    classId: {
      type: String,
      default: null
    }
  },
  data() {
    return {
      activeLevel: 1,
      grades: [],
      exams: [],
      timelineExams: [],
      selectedGrade: null,
      selectedExam: this.examId,
      loadingGrades: false,
      loadingExams: false,
      showTimeline: false
    };
  },
  watch: {
    currentLevel: {
      immediate: true,
      handler(val) {
        this.activeLevel = val;
      }
    },
    examId: {
      immediate: true,
      handler(val) {
        this.selectedExam = val;
      }
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
          // 如果URL中没有examId，默认选择第一个年级
          if (!this.examId) {
            this.selectedGrade = this.grades[0].grade_id;
            this.fetchExams();
          } else {
            // 如果URL中有examId，需要根据考试ID获取对应的年级
            await this.fetchExamInfo();
          }
        }
      } catch (error) {
        console.error('获取年级数据失败:', error);
      } finally {
        this.loadingGrades = false;
      }
    },
    
    async fetchExamInfo() {
      if (!this.examId) return;
      
      try {
        // 根据考试ID获取考试信息（包括年级）
        const response = await featureAnalysisApi.getExamInfo(this.examId);
        const examInfo = response.data;
        
        if (examInfo && examInfo.grade_id) {
          this.selectedGrade = examInfo.grade_id;
          await this.fetchExams();
        }
      } catch (error) {
        console.error('获取考试信息失败:', error);
      }
    },
    
    async fetchExams() {
      if (!this.selectedGrade) return;
      
      this.loadingExams = true;
      try {
        const response = await featureAnalysisApi.getAnalyzableExams({
          grade_id: this.selectedGrade
        });
        
        this.exams = response.data || [];
        
        // 设置时间轴数据
        if (this.exams.length > 0) {
          this.showTimeline = true;
          this.timelineExams = [...this.exams].sort((a, b) => 
            new Date(a.exam_date) - new Date(b.exam_date)
          );
        } else {
          this.showTimeline = false;
        }
        
        // 如果存在examId但不在当前列表中，可能需要获取更多信息
        if (this.examId && !this.exams.find(e => e.exam_id === this.examId)) {
          await this.fetchAdditionalExamInfo();
        }
      } catch (error) {
        console.error('获取考试数据失败:', error);
      } finally {
        this.loadingExams = false;
      }
    },
    
    async fetchAdditionalExamInfo() {
      try {
        // 获取指定考试的信息
        const response = await featureAnalysisApi.getExamInfo(this.examId);
        const examInfo = response.data;
        
        // 将考试信息添加到列表中
        if (examInfo && !this.exams.find(e => e.exam_id === examInfo.exam_id)) {
          this.exams.push(examInfo);
          
          // 更新时间轴
          this.timelineExams = [...this.exams].sort((a, b) => 
            new Date(a.exam_date) - new Date(b.exam_date)
          );
          this.showTimeline = true;
        }
      } catch (error) {
        console.error('获取额外考试信息失败:', error);
      }
    },
    
    handleGradeChange() {
      this.fetchExams();
    },
    
    handleExamChange(examId) {
      this.selectedExam = examId;
      this.navigateToLevel(this.activeLevel);
    },
    
    selectExam(examId) {
      this.selectedExam = examId;
      this.navigateToLevel(this.activeLevel);
    },
    
    handleLevelChange(level) {
      this.navigateToLevel(level);
    },
    
    navigateToLevel(level) {
      if (!this.selectedExam) return;
      
      if (level === 1) {
        this.$router.push({ name: 'DistrictAnalysis', params: { examId: this.selectedExam } });
      } else if (level === 2) {
        this.$router.push({ name: 'SchoolAnalysis', params: { examId: this.selectedExam, districtId: this.districtId } });
      } else if (level === 3) {
        this.$router.push({ name: 'ClassAnalysis', params: { examId: this.selectedExam, schoolId: this.schoolId } });
      } else if (level === 4) {
        this.$router.push({ name: 'StudentAnalysis', params: { examId: this.selectedExam, classId: this.classId } });
      }
    },
    
    formatDate(dateString) {
      if (!dateString) return '';
      
      const date = new Date(dateString);
      const month = date.getMonth() + 1;
      const day = date.getDate();
      
      return `${month}/${day}`;
    }
  }
};
</script>

<style scoped>
.feature-navigation {
  display: flex;
  flex-direction: column;
  margin-bottom: 20px;
  border-bottom: 1px solid #ebeef5;
  padding-bottom: 15px;
}

.filter-panel {
  margin-bottom: 20px;
}

.filter-row {
  margin-bottom: 15px;
}

.filter-item {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
}

.filter-label {
  font-weight: bold;
  margin-right: 10px;
  min-width: 60px;
}

.filter-help {
  color: #909399;
  font-size: 12px;
  margin-top: 5px;
  margin-left: 70px;
  width: 100%;
}

/* 时间轴样式 */
.timeline-container {
  margin: 20px 0;
  padding: 15px;
  border: 1px solid #ddd;
  border-radius: 5px;
}

.timeline {
  display: flex;
  justify-content: space-between;
  margin: 20px 0;
  position: relative;
}

.timeline::before {
  content: "";
  position: absolute;
  top: 50%;
  left: 0;
  right: 0;
  height: 2px;
  background-color: #ddd;
  z-index: 1;
}

.timeline-item {
  position: relative;
  z-index: 2;
}

.time-point {
  width: 80px;
  height: 30px;
  background-color: #f8f9fa;
  border: 1px solid #ddd;
  border-radius: 15px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.3s;
}

.time-point:hover {
  background-color: #e9ecef;
}

.time-point.active {
  background-color: #007bff;
  color: white;
  border-color: #007bff;
}

.level-tabs {
  margin: 15px 0;
  text-align: center;
}

.breadcrumb-container {
  margin-top: 10px;
}
</style> 