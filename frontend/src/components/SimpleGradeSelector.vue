<template>
  <div>
    <div class="simple-selector">
      <h3>年级数据状态: {{ dataStatus }}</h3>
      
      <div v-if="grades.length > 0" class="grades-list">
        <div
          v-for="grade in grades"
          :key="grade.grade_id"
          class="grade-item"
          @click="selectGrade(grade)"
        >
          {{ grade.grade_name }} 
          <span v-if="grade.graduation_info">({{ grade.graduation_info }})</span>
        </div>
      </div>
      
      <div v-else-if="loading" class="loading-indicator">
        正在加载年级数据...
      </div>
      
      <div v-else class="no-data">
        没有找到年级数据
      </div>
    </div>
  </div>
</template>

<script>
import educationDataApi from '@/api/education-data';

export default {
  name: 'SimpleGradeSelector',
  data() {
    return {
      grades: [],
      loading: false,
      error: null
    }
  },
  computed: {
    dataStatus() {
      if (this.loading) return '加载中';
      if (this.error) return '加载出错';
      if (this.grades.length === 0) return '无数据';
      return `已加载 ${this.grades.length} 条记录`;
    }
  },
  created() {
    this.fetchGrades();
  },
  methods: {
    fetchGrades() {
      this.loading = true;
      
      console.log('SimpleGradeSelector: 开始获取年级数据');
      
      // 先尝试直接从educationDataApi获取
      const api = this.$api || educationDataApi;
      
      api.getGradesWithGraduationInfo()
        .then(response => {
          console.log('SimpleGradeSelector: 获取到数据', response);
          
          if (Array.isArray(response.data)) {
            this.grades = response.data;
          } else {
            console.warn('SimpleGradeSelector: 响应数据不是数组', response.data);
            this.grades = [];
          }
        })
        .catch(err => {
          console.error('SimpleGradeSelector: 获取年级数据失败', err);
          this.error = err.toString();
        })
        .finally(() => {
          this.loading = false;
        });
    },
    
    selectGrade(grade) {
      this.$emit('grade-selected', grade);
    }
  }
}
</script>

<style scoped>
.simple-selector {
  border: 1px solid #ddd;
  border-radius: 4px;
  padding: 15px;
}
.grades-list {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 15px;
}
.grade-item {
  padding: 8px 12px;
  background-color: #f0f2f5;
  border-radius: 4px;
  cursor: pointer;
}
.grade-item:hover {
  background-color: #e6f7ff;
}
.loading-indicator, .no-data {
  padding: 20px 0;
  text-align: center;
  color: #909399;
}
</style> 