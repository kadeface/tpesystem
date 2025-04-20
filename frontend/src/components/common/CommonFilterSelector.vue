<template>
  <div class="common-filter-selector">
    <el-form-item label="区域:">
      <el-select 
        v-model="selectedDistrict" 
        placeholder="请选择区域"
        clearable
        style="width: 100%"
        @change="emitChange"
        :loading="loadingRegions"
      >
        <el-option
          v-for="district in districts"
          :key="district.value"
          :label="district.label"
          :value="district.value"
        />
      </el-select>
    </el-form-item>
    
    <el-form-item label="学段:">
      <el-select 
        v-model="selectedEducationStage" 
        placeholder="请选择学段"
        clearable
        style="width: 100%"
        @change="handleStageChange"
      >
        <el-option
          v-for="stage in educationStages"
          :key="stage.value"
          :label="stage.label"
          :value="stage.value"
        />
      </el-select>
    </el-form-item>
    
    <el-form-item label="年级:">
      <el-select 
        v-model="selectedGrade" 
        placeholder="请选择年级"
        clearable
        style="width: 100%"
        :disabled="!selectedEducationStage"
        @change="handleGradeChange"
        :loading="loadingGrades"
      >
        <el-option
          v-for="grade in filteredGrades"
          :key="grade.value"
          :label="grade.label"
          :value="grade.value"
        />
      </el-select>
    </el-form-item>
    
    <el-form-item label="考试:">
      <el-select
        v-model="selectedExams"
        multiple
        collapse-tags
        collapse-tags-tooltip
        placeholder="请选择至少两次考试"
        style="width: 100%"
        @change="handleExamChange"
      >
        <el-option
          v-for="(exam, index) in examList"
          :key="exam && exam.exam_id ? exam.exam_id : `unknown-${index}`"
          :label="exam ? getExamLabel(exam) : '未知考试'"
          :value="exam && exam.exam_id ? exam.exam_id : ''"
        />
      </el-select>
      <div class="form-hint">请按照时间顺序选择考试，至少选择两次</div>
    </el-form-item>
    
    <el-form-item label="学科:">
      <el-select 
        v-model="selectedSubject" 
        placeholder="请选择学科" 
        style="width: 100%"
        @change="handleSubjectChange"
      >
        <el-option
          v-for="subject in subjectList"
          :key="subject.subject_id"
          :label="subject.subject_name"
          :value="subject.subject_id"
        />
      </el-select>
    </el-form-item>
    
    <div class="result-section" v-if="analysisComplete">
      <!-- 聚类散点图 -->
      <div class="visualization-container">
        <h3>学生聚类散点图</h3>
        <div id="cluster-chart" style="width: 100%; height: 400px;"></div>
      </div>
      
      <!-- 成长轨迹图 -->
      <div class="visualization-container">
        <h3>学生群体成长轨迹</h3>
        <div id="growth-chart" style="width: 100%; height: 400px;"></div>
      </div>
      
      <!-- 聚类概况表格 -->
      <div class="cluster-profiles">
        <h3>聚类概况</h3>
        <el-table :data="getClusterProfilesAsArray()" border>
          <el-table-column prop="name" label="聚类名称"></el-table-column>
          <el-table-column prop="size" label="学生数量"></el-table-column>
          <el-table-column prop="avg_growth" label="平均增长"></el-table-column>
          <el-table-column prop="characteristics" label="特征描述"></el-table-column>
        </el-table>
      </div>
    </div>
  </div>
</template>

<script>
/**
 * 通用筛选选择器组件
 * 
 * 包含区域、学段、年级选择功能
 * 
 * @component
 */
import educationDataApi from '@/api/education-data';

export default {
  name: 'CommonFilterSelector',
  props: {
    district: {
      type: String,
      default: ''
    },
    educationStage: {
      type: String,
      default: ''
    },
    grade: {
      type: String,
      default: ''
    },
    exam: {
      type: Array,
      default: () => []
    },
    subject: {
      type: String,
      default: ''
    }
  },
  emits: ['update:district', 'update:educationStage', 'update:grade', 'update:exam', 'update:subject', 'change'],
  data() {
    return {
      selectedDistrict: this.district,
      selectedEducationStage: this.educationStage,
      selectedGrade: this.grade,
      selectedExams: this.exam,
      selectedSubject: this.subject,
      
      districts: [],
      educationStages: [],
      grades: [],
      examList: [],
      subjectList: [],
      
      loadingRegions: false,
      loadingGrades: false,
      loadingExams: false,
      loadingSubjects: false,
      analysisComplete: false,
      chartInstances: {}
    }
  },
  computed: {
    /**
     * 根据所选学段筛选年级
     * 
     * @returns {Array} 筛选后的年级列表
     */
    filteredGrades() {
      if (!this.selectedEducationStage) {
        return [];
      }
      
      return this.grades.filter(grade => grade.stage === this.selectedEducationStage);
    }
  },
  watch: {
    district(newVal) {
      this.selectedDistrict = newVal;
    },
    educationStage(newVal) {
      this.selectedEducationStage = newVal;
      // 当学段变化时，重新加载年级
      if (newVal) {
        this.loadGrades({ stage: newVal });
      }
    },
    grade(newVal) {
      this.selectedGrade = newVal;
    },
    exam(newVal) {
      this.selectedExams = newVal;
    },
    subject(newVal) {
      this.selectedSubject = newVal;
    }
  },
  created() {
    // 组件创建时加载数据
    this.loadRegions();
    this.loadEducationStages();
    if (this.selectedEducationStage) {
      this.loadGrades({ stage: this.selectedEducationStage });
    }
    this.loadExams();
    this.loadSubjects();
  },
  methods: {
    /**
     * 加载区域数据
     */
    loadRegions() {
      this.loadingRegions = true;
      educationDataApi.getRegions()
        .then(response => {
          // 转换后端数据为组件所需格式
          this.districts = response.data.map(region => ({
            value: region.region_id,
            label: region.region_name
          }));
        })
        .catch(error => {
          console.error('加载区域数据失败:', error);
          this.$message.error('加载区域数据失败');
        })
        .finally(() => {
          this.loadingRegions = false;
        });
    },
    
    /**
     * 加载学段数据
     */
    loadEducationStages() {
      educationDataApi.getEducationStages()
        .then(response => {
          this.educationStages = response.data;
        })
        .catch(error => {
          console.error('加载学段数据失败:', error);
        });
    },
    
    /**
     * 加载年级数据
     * 
     * @param {Object} params - 查询参数
     */
    loadGrades(params = {}) {
      this.loadingGrades = true;
      educationDataApi.getGradesWithGraduationInfo(params)
        .then(response => {
          // 转换后端数据为组件所需格式
          this.grades = response.data.map(grade => {
            // 从grade_level确定学段
            let stage = 'elementary';
            const level = parseInt(grade.grade_level);
            if (level >= 7 && level <= 9) {
              stage = 'junior';
            } else if (level >= 10) {
              stage = 'senior';
            }
            
            return {
              value: grade.grade_id,
              label: grade.grade_name,
              stage: stage
            };
          });
        })
        .catch(error => {
          console.error('加载年级数据失败:', error);
          this.$message.error('加载年级数据失败');
        })
        .finally(() => {
          this.loadingGrades = false;
        });
    },
    
    /**
     * 处理学段变化
     * 当学段改变时，可能需要重置年级
     */
    handleStageChange() {
      // 如果年级不属于当前学段，重置年级选择
      if (this.selectedGrade && 
          this.selectedEducationStage && 
          !this.filteredGrades.some(g => g.value === this.selectedGrade)) {
        this.selectedGrade = '';
        this.$emit('update:grade', '');
      }
      
      this.$emit('update:educationStage', this.selectedEducationStage);
      this.emitChange();
      
      // 学段改变时，重新加载考试和学科数据
      this.loadExams();
      this.loadSubjects();
    },
    
    /**
     * 触发变更事件
     * 用于通知父组件筛选条件已变更
     */
    emitChange() {
      // 先更新各个单独的属性
      this.$emit('update:district', this.selectedDistrict);
      this.$emit('update:educationStage', this.selectedEducationStage);
      this.$emit('update:grade', this.selectedGrade);
      this.$emit('update:exam', this.selectedExams);
      this.$emit('update:subject', this.selectedSubject);
      
      // 然后发送统一的change事件，带上所有筛选参数
      const filterParams = {
        district: this.selectedDistrict,
        education_stage: this.selectedEducationStage,
        grade: this.selectedGrade,
        exams: this.selectedExams,
        subject: this.selectedSubject
      };
      
      this.$emit('change', filterParams);
      
      // 当关键筛选条件变化时，重新加载考试数据
      this.loadExams();
    },
    
    async loadExams() {
      // 添加include_history参数
      const params = {
        district: this.selectedDistrict,
        education_stage: this.selectedEducationStage,
        grade_id: this.selectedGrade,
        subject: this.selectedSubject,
        include_history: true,
        all_exams: true
      };
      
      try {
        const response = await educationDataApi.getExams(params);
        
        // 确保数据是数组
        if (response && response.data) {
          if (Array.isArray(response.data)) {
            this.examList = response.data.filter(exam => exam != null);
          } else {
            console.warn('API返回的考试数据不是数组:', response.data);
            this.examList = [];
          }
          
          // 只有当examList是数组时才排序
          if (Array.isArray(this.examList) && this.examList.length > 0) {
            this.examList.sort((a, b) => {
              const dateA = new Date(a.start_time || a.exam_date || 0);
              const dateB = new Date(b.start_time || b.exam_date || 0);
              return dateB - dateA;
            });
          }
          
          console.log(`加载了${this.examList.length}个考试（包含历史考试）`);
        } else {
          this.examList = [];
        }
      } catch (error) {
        console.error('加载考试数据失败:', error);
        this.examList = [];
      }
    },
    
    async loadSubjects() {
      this.loadingSubjects = true;
      
      try {
        const response = await educationDataApi.getSubjects();
        if (response && response.data) {
          this.subjectList = response.data;
        } else {
          // 使用默认学科数据
          this.subjectList = [
            { subject_id: 'math', subject_name: '数学' },
            { subject_id: 'chinese', subject_name: '语文' },
            { subject_id: 'english', subject_name: '英语' },
            { subject_id: 'physics', subject_name: '物理' },
            { subject_id: 'chemistry', subject_name: '化学' }
          ];
        }
        console.log('加载学科数据:', this.subjectList.length);
      } catch (error) {
        console.error('加载学科数据失败:', error);
        // 使用默认学科数据
        this.subjectList = [
          { subject_id: 'math', subject_name: '数学' },
          { subject_id: 'chinese', subject_name: '语文' },
          { subject_id: 'english', subject_name: '英语' }
        ];
      } finally {
        this.loadingSubjects = false;
      }
    },
    
    handleExamChange() {
      this.$emit('update:exam', this.selectedExams);
      
      // 创建完整的筛选参数对象
      const filterParams = {
        district: this.selectedDistrict,
        education_stage: this.selectedEducationStage,
        grade: this.selectedGrade,
        exams: this.selectedExams,
        subject: this.selectedSubject
      };
      
      // 直接发送change事件，不调用emitChange以避免循环
      this.$emit('change', filterParams);
    },
    
    handleSubjectChange() {
      this.$emit('update:subject', this.selectedSubject);
      
      // 创建完整的筛选参数对象
      const filterParams = {
        district: this.selectedDistrict,
        education_stage: this.selectedEducationStage,
        grade: this.selectedGrade,
        exams: this.selectedExams,
        subject: this.selectedSubject
      };
      
      // 直接发送change事件，不调用emitChange以避免循环
      this.$emit('change', filterParams);
    },
    
    /**
     * 获取考试的显示标签，包含年级信息
     */
    getExamLabel(exam) {
      if (!exam.grade_name) {
        return exam.exam_name;
      }
      return `${exam.exam_name} (${exam.grade_name})`;
    },
    
    /**
     * 当年级选择变化时处理
     */
    handleGradeChange() {
      this.$emit('update:grade', this.selectedGrade);
      
      // 重置考试选择
      this.selectedExams = [];
      this.$emit('update:exam', []);
      
      // 发送筛选条件变更事件
      this.emitChange();
      
      // 加载所选年级的所有考试（包括历史考试）
      this.loadGradeExams(this.selectedGrade);
    },
    
    /**
     * 加载指定年级的所有考试（包括历史考试）
     * 
     * @param {String} gradeId - 年级ID
     */
    async loadGradeExams(gradeId) {
      if (!gradeId) {
        console.log('未选择年级，不加载考试');
        this.examList = [];
        return;
      }
      
      console.log(`【重要】加载年级 ${gradeId} 的所有考试（包括历史考试）`);
      this.loadingExams = true;
      
      try {
        const params = {
          grade_id: gradeId,
          subject: this.selectedSubject,
          district: this.selectedDistrict,
          include_history: true,
          all_exams: true,
          _debug: Date.now() // 添加随机参数避免缓存
        };
        
        console.log('【重要】发送考试API请求，参数:', params);
        
        const response = await educationDataApi.getExams(params);
        
        console.log('【重要】考试API响应:', response);
        
        // 确保数据是数组并过滤掉null
        if (response && response.data) {
          if (Array.isArray(response.data)) {
            this.examList = response.data.filter(exam => exam != null);
            console.log(`成功加载${this.examList.length}个考试`);
            
            // 安全地排序
            if (this.examList.length > 0) {
              this.sortExamsByDate();
            }
          } else {
            console.warn('API返回的考试数据不是数组:', response.data);
            this.examList = [];
          }
        } else {
          this.examList = [];
          console.log('未找到考试数据');
        }
      } catch (error) {
        console.error('【重要】加载年级考试失败，详细错误:', error);
        this.examList = [];
      } finally {
        this.loadingExams = false;
      }
    },
    
    /**
     * 按考试日期排序考试列表
     */
    sortExamsByDate() {
      // 检查this.examList是否为数组
      if (!Array.isArray(this.examList)) {
        console.warn('考试列表不是数组，无法排序', this.examList);
        // 确保examList始终是数组
        this.examList = [];
        return;
      }
      
      // 过滤掉null和undefined值
      this.examList = this.examList.filter(exam => exam != null);
      
      // 然后进行排序
      this.examList.sort((a, b) => {
        // 按考试日期降序排列（最新的考试排在前面）
        const dateA = new Date(a.exam_date || a.start_time || 0);
        const dateB = new Date(b.exam_date || b.start_time || 0);
        return dateB - dateA;
      });
    },
    
    /**
     * 将聚类概况转为数组格式用于表格显示
     * 
     * @returns {Array} 聚类概况数组
     */
    getClusterProfilesAsArray() {
      // 如果没有聚类数据，返回空数组
      if (!this.$parent.clusterProfiles || Object.keys(this.$parent.clusterProfiles).length === 0) {
        console.log('CommonFilterSelector: 没有聚类配置数据可显示');
        return [];
      }
      
      // 从父组件获取聚类数据
      return Object.entries(this.$parent.clusterProfiles).map(([id, profile]) => {
        return {
          id: id,
          name: profile.name || `聚类 ${id}`,
          size: profile.size || 0,
          avg_growth: profile.avg_growth || 'N/A',
          characteristics: profile.characteristics || '无详细描述'
        };
      });
    },
    
    handleResize() {
      // Implementation of handleResize method
    }
  },
  beforeUnmount() {
    // 清理图表实例
    Object.values(this.chartInstances).forEach(chart => {
      if (chart && chart.dispose) {
        chart.dispose();
      }
    });
    
    // 移除事件监听器
    window.removeEventListener('resize', this.handleResize);
  }
}
</script>

<style scoped>
.common-filter-selector {
  margin-bottom: 10px;
}

.form-hint {
  font-size: 12px;
  color: #909399;
  margin-top: 5px;
}

.result-section {
  margin-top: 20px;
}

.visualization-container {
  margin-bottom: 20px;
}

.cluster-profiles {
  margin-top: 20px;
}
</style> 