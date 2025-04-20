<template>
  <div>
    <div class="grade-selector">
      <!-- 按毕业年份分组显示 -->
      <div class="graduation-years">
        <div 
          v-for="group in graduationGroups" 
          :key="group.year"
          @click="selectGraduationYear(group.year, group.education_stage)"
          :class="{ 'active': selectedGraduationYear === group.year && selectedEducationStage === group.education_stage }"
          class="graduation-year-item"
        >
          {{ group.display }}
        </div>
      </div>
      
      <!-- 年级选择器 -->
      <div class="grade-list">
        <div 
          v-for="grade in filteredGrades" 
          :key="grade.grade_id" 
          @click="selectGrade(grade)"
          :class="{ 'active': selectedGrade && selectedGrade.grade_id === grade.grade_id }"
          class="grade-item"
        >
          {{ grade.grade_name }}
        </div>
      </div>
    </div>
    
    <!-- 无数据提示 -->
    <div v-if="grades.length === 0" class="no-data-tip">
      未找到年级数据
    </div>
  </div>
</template>

<script>
export default {
  name: 'GradeSelector',
  props: {
    educationStage: String
  },
  data() {
    return {
      grades: [],
      selectedGrade: null,
      selectedGraduationYear: null,
      selectedEducationStage: null
    }
  },
  computed: {
    // 按毕业年份和教育阶段分组
    graduationGroups() {
      const groups = [];
      const groupMap = new Map();
      
      this.grades.forEach(grade => {
        if (grade.graduation_year && grade.education_stage) {
          const key = `${grade.graduation_year}_${grade.education_stage}`;
          if (!groupMap.has(key)) {
            groupMap.set(key, true);
            groups.push({
              year: grade.graduation_year,
              education_stage: grade.education_stage,
              display: grade.graduation_info
            });
          }
        }
      });
      
      // 按照学段和毕业年份排序(同学段内按毕业年份降序)
      return groups.sort((a, b) => {
        // 先按学段排序
        const stageOrder = {
          'elementary': 1,
          'junior': 2, 
          'senior': 3
        };
        
        const stageA = stageOrder[a.education_stage] || 0;
        const stageB = stageOrder[b.education_stage] || 0;
        
        if (stageA !== stageB) return stageA - stageB;
        
        // 同学段内按毕业年份降序(近期毕业年份优先)
        return b.year - a.year;
      });
    },
    
    // 根据选择的毕业年份筛选年级
    filteredGrades() {
      if (!this.selectedGraduationYear || !this.selectedEducationStage) {
        return this.grades;
      }
      
      return this.grades.filter(grade => 
        grade.graduation_year === this.selectedGraduationYear && 
        grade.education_stage === this.selectedEducationStage
      );
    }
  },
  created() {
    this.fetchGrades();
  },
  methods: {
    fetchGrades() {
      const params = {};
      if (this.educationStage) {
        params.stage = this.educationStage;
      }
      
      console.log('开始获取年级数据, 参数:', params);
      
      // 使用带毕业年份信息的API
      this.$api.getGradesWithGraduationInfo(params)
        .then(response => {
          console.log('获取到年级数据:', response.data);
          this.grades = response.data || [];
          
          // 默认选择第一个毕业年份组
          if (this.graduationGroups.length > 0) {
            console.log('可用的届次组:', this.graduationGroups);
            const firstGroup = this.graduationGroups[0];
            this.selectGraduationYear(firstGroup.year, firstGroup.education_stage);
          } else {
            console.warn('没有可用的届次组!');
          }
        })
        .catch(error => {
          console.error('获取年级数据失败:', error);
          this.grades = []; // 确保grades至少是空数组
        });
    },
    
    selectGraduationYear(year, educationStage) {
      this.selectedGraduationYear = year;
      this.selectedEducationStage = educationStage;
      this.selectedGrade = null;
      
      // 触发事件通知父组件
      this.$emit('graduation-year-selected', {
        year: year,
        education_stage: educationStage
      });
    },
    
    selectGrade(grade) {
      this.selectedGrade = grade;
      
      // 触发事件通知父组件
      this.$emit('grade-selected', {
        ...grade,
        graduation_year: this.selectedGraduationYear,
        education_stage: this.selectedEducationStage
      });
    }
  }
}
</script>

<style scoped>
/* 样式沿用原有的，补充毕业年份选择器样式 */
.graduation-years {
  display: flex;
  flex-wrap: wrap;
  margin-bottom: 15px;
}
.graduation-year-item {
  padding: 8px 12px;
  margin-right: 8px;
  margin-bottom: 8px;
  border: 1px solid #ddd;
  border-radius: 4px;
  cursor: pointer;
}
.graduation-year-item.active {
  background-color: #1890ff;
  color: white;
}
/* 其他样式与原有组件一致 */
.grade-list {
  display: flex;
  flex-wrap: wrap;
}
.grade-item {
  padding: 8px 12px;
  margin-right: 8px;
  margin-bottom: 8px;
  border: 1px solid #ddd;
  border-radius: 4px;
  cursor: pointer;
}
.grade-item.active {
  background-color: #1890ff;
  color: white;
}
.no-data-tip {
  text-align: center;
  padding: 20px;
  color: #909399;
}
</style>