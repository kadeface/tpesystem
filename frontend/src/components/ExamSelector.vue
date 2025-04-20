<template>
  <div class="exam-selector">
    <h3>选择考试</h3>
    
    <!-- 学科筛选器 -->
    <div class="filters">
      <el-select 
        v-model="selectedSubject" 
        placeholder="按学科筛选" 
        clearable 
        @change="fetchExams"
        style="width: 150px; margin-bottom: 10px;"
      >
        <el-option
          v-for="subject in subjects"
          :key="subject.subject_id"
          :label="subject.subject_name"
          :value="subject"
        />
      </el-select>
    </div>
    
    <!-- 加载状态 -->
    <el-skeleton :loading="loading" animated :rows="5" v-if="loading">
      <template #template>
        <div style="padding: 20px;">
          <p>加载考试数据中...</p>
        </div>
      </template>
    </el-skeleton>
    
    <!-- 考试列表 -->
    <template v-else>
      <div v-if="exams.length > 0" class="exam-list-container">
        <div class="exam-list-header">
          <div>考试ID</div>
          <div>考试名称</div>
          <div>操作</div>
        </div>
        <el-scrollbar height="300px">
          <div class="exam-list">
            <div 
              v-for="exam in exams" 
              :key="exam.exam_id" 
              class="exam-item"
            >
              <div class="exam-id">{{ exam.exam_id }}</div>
              <div class="exam-name">{{ exam.exam_name || '未命名考试' }}</div>
              <div class="exam-action">
                <el-button 
                  type="primary" 
                  size="small" 
                  @click="selectExam(exam)"
                >选择</el-button>
              </div>
            </div>
          </div>
        </el-scrollbar>
      </div>
      <div v-else class="no-data">
        加载考试数据中...
      </div>
    </template>
    
    <!-- 调试信息 -->
    <div class="debug-panel">
      <el-collapse>
        <el-collapse-item title="调试信息" name="1">
          <pre>{{ debugInfo }}</pre>
        </el-collapse-item>
      </el-collapse>
    </div>
  </div>
</template>

<script>
import educationDataApi from '@/api/education-data';

export default {
  name: 'ExamSelector',
  props: {
    selectedGrade: {
      type: Object,
      default: null
    }
  },
  data() {
    return {
      selectedSubject: null,
      exams: [],
      loading: false,
      subjects: [],
      lastParams: {},
      error: null
    };
  },
  computed: {
    debugInfo() {
      return JSON.stringify({
        hasGrade: !!this.selectedGrade,
        gradeId: this.selectedGrade?.grade_id,
        requestParams: this.lastParams,
        examCount: this.exams.length,
        examExample: this.exams.length > 0 ? {
          id: this.exams[0].exam_id,
          name: this.exams[0].exam_name
        } : null
      }, null, 2);
    }
  },
  watch: {
    selectedGrade(newVal) {
      if (newVal) {
        console.log('通过props接收到年级选择:', newVal);
        this.fetchExams();
      }
    },
    exams: {
      handler(newExams) {
        console.log('考试数据已更新到组件:', 
                    newExams.length, 
                    newExams.length > 0 ? newExams[0].exam_id : '无数据');
      },
      immediate: true
    }
  },
  created() {
    // 确保API被正确注入
    this.$api = this.$api || educationDataApi;
    console.log('ExamSelector组件初始化');
    
    this.loadSubjects();
    // 立即加载所有考试数据
    this.fetchExams();
  },
  methods: {
    async loadSubjects() {
      console.log('加载学科数据');
      try {
        const response = await this.$api.getSubjects();
        
        // 确保response.data存在且为数组
        if (response && response.data && Array.isArray(response.data)) {
          this.subjects = response.data;
        } else {
          // 使用默认学科数据
          this.subjects = [
            { subject_id: 'math', subject_name: '数学' },
            { subject_id: 'chinese', subject_name: '语文' },
            { subject_id: 'english', subject_name: '英语' }
          ];
        }
        
        console.log('加载到学科数据:', this.subjects.length);
      } catch (error) {
        console.error('获取学科数据失败:', error);
        // 使用默认数据
        this.subjects = [
          { subject_id: 'math', subject_name: '数学' },
          { subject_id: 'chinese', subject_name: '语文' },
          { subject_id: 'english', subject_name: '英语' }
        ];
      }
    },
    
    selectExam(exam) {
      console.log('选择考试:', exam);
      this.$emit('exam-selected', exam);
    },
    
    async fetchExams() {
      console.log('使用硬编码测试数据');
      
      // 使用硬编码考试数据测试渲染
      const testExams = [
        {
          exam_id: "2025-DIST-M-202501",
          exam_name: "测试考试1"
        },
        {
          exam_id: "202307-DIST-M-2023",
          exam_name: "测试考试2"
        },
        {
          exam_id: "202207-DIST-M-2022",
          exam_name: "测试考试3"
        }
      ];
      
      // 直接赋值测试
      this.exams = testExams;
      this.loading = false;
      console.log('设置测试数据完成:', this.exams.length);
    }
  },
  mounted() {
    console.log('ExamSelector已挂载到DOM');
    // 获取组件的DOM元素
    const el = this.$el;
    console.log('ExamSelector DOM:', {
      width: el.offsetWidth,
      height: el.offsetHeight,
      visible: !(el.offsetWidth === 0 && el.offsetHeight === 0)
    });
  }
};
</script>

<style scoped>
.exam-selector {
  margin: 0;
  border: none;
  padding: 0;
  background-color: transparent;
}

.exam-list-container {
  border: 1px solid #ebeef5;
  border-radius: 4px;
  overflow: hidden;
}

.exam-list-header {
  display: grid;
  grid-template-columns: 200px 1fr 100px;
  background-color: #f5f7fa;
  padding: 10px 15px;
  font-weight: bold;
  border-bottom: 1px solid #ebeef5;
}

.exam-list {
  max-height: 300px;
}

.exam-item {
  display: grid;
  grid-template-columns: 200px 1fr 100px;
  padding: 12px 15px;
  align-items: center;
  border-bottom: 1px solid #ebeef5;
}

.exam-item:hover {
  background-color: #f5f7fa;
}

.exam-item:last-child {
  border-bottom: none;
}

.exam-id {
  font-weight: bold;
  color: #409EFF;
}

.no-data {
  text-align: center;
  padding: 40px 0;
  color: #909399;
  background-color: #f8f8f8;
  border-radius: 4px;
}

.debug-panel {
  margin-top: 20px;
}

.filters {
  margin-bottom: 15px;
}
</style> 