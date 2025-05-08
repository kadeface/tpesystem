<template>
  <div class="teacher-value-added">
    <h2>教师增值分析</h2>
    
    <!-- 筛选区域 -->
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
      
      <!-- 添加按钮区域 -->
      <div class="filter-buttons">
        <el-button type="primary" @click="startAnalysis" :disabled="!canAnalyze">开始分析</el-button>
        <el-button @click="resetFilters">重置</el-button>
      </div>
    </div>
    
    <!-- 无数据提示 -->
    <el-empty v-if="!currentTeacher && !isLoading" description="请选择筛选条件以查看教师增值分析"></el-empty>
    
    <!-- 加载中 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="10" animated />
    </div>
    
    <!-- 教师总体增值概览 -->
    <el-card class="overview-card">
      <template #header>教师增值概览</template>
      <el-row v-if="currentTeacher">
        <el-col :span="6">
          <div class="metric-box">
            <div class="metric-label">总体增值</div>
            <div class="metric-value">
              {{ (currentTeacher.overallValueAdded || 0).toFixed(2) }}
            </div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="metric-box">
            <div class="metric-label">排名</div>
            <div class="metric-value">{{ currentTeacher.rank || '未排名' }}</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="metric-box">
            <div class="metric-label">百分位</div>
            <div class="metric-value">
              {{ (currentTeacher.percentile || 0).toFixed(1) }}%
            </div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="metric-box">
            <div class="metric-label">学生总数</div>
            <div class="metric-value">{{ currentTeacher.totalStudents || 0 }}</div>
          </div>
        </el-col>
      </el-row>
      <div v-else class="no-data-placeholder">
        <el-empty description="暂无教师增值数据"></el-empty>
      </div>
    </el-card>
    
    <!-- 分层增值分析 -->
    <el-card class="layer-analysis-card">
      <template #header>分层增值分析</template>
      
      <div v-if="currentTeacherLayers && currentTeacherLayers.length > 0">
        <!-- 分层增值柱状图 -->
        <div id="layerValueAddedChart" class="chart-container"></div>
        
        <!-- 分层增值详细数据表格 -->
        <el-table :data="currentTeacherLayers" stripe>
          <el-table-column prop="layer" label="学生层次"></el-table-column>
          <el-table-column prop="studentCount" label="学生数量"></el-table-column>
          <el-table-column prop="valueAdded" label="平均增值">
            <template #default="{row}">
              <span :class="getValueClass(row.valueAdded)">{{ row.valueAdded.toFixed(2) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="contribution" label="贡献率">
            <template #default="{row}">
              {{ (row.contribution * 100).toFixed(1) }}%
            </template>
          </el-table-column>
          <!-- 其他列... -->
        </el-table>
      </div>
      <div v-else class="no-data-placeholder">
        <el-empty description="暂无分层增值数据"></el-empty>
      </div>
    </el-card>
    
    <!-- 教师能力雷达图 -->
    <el-card class="ability-radar-card">
      <template #header>教学能力分析</template>
      <div id="abilityRadarChart" class="chart-container"></div>
    </el-card>
    
    <!-- 教学提升建议卡片 -->
    <el-card class="recommendation-card">
      <template #header>教学提升建议</template>
      <div v-if="currentTeacher && currentTeacher.teachingAdvice" class="recommendation-content">
        <div class="advice-section">
          <h4>教学优势</h4>
          <ul>
            <li v-for="(strength, index) in currentTeacher.teachingAdvice.strengths" :key="`strength-${index}`">
              {{ strength }}
            </li>
          </ul>
        </div>
        
        <div class="advice-section">
          <h4>改进方向</h4>
          <ul>
            <li v-for="(improvement, index) in currentTeacher.teachingAdvice.improvements" :key="`improvement-${index}`">
              {{ improvement }}
            </li>
          </ul>
        </div>
        
        <div class="advice-section">
          <h4>教学策略建议</h4>
          <ul>
            <li v-for="(strategy, index) in currentTeacher.teachingAdvice.strategies" :key="`strategy-${index}`">
              {{ strategy }}
            </li>
          </ul>
        </div>
      </div>
      <div v-else class="no-data-placeholder">
        <el-empty description="暂无教学提升建议"></el-empty>
      </div>
    </el-card>
    
    <!-- 学校-班级选择区域 -->
    <el-card v-if="dataLoaded && !currentTeacher" class="hierarchy-select-card">
      <template #header>选择班级查看教师增值分析</template>
      
      <el-collapse v-model="activeSchools" accordion>
        <el-collapse-item 
          v-for="school in schoolsData" 
          :key="school.schoolName" 
          :title="school.schoolName"
          :name="school.schoolName"
        >
          <div class="class-list">
            <el-card 
              v-for="cls in school.classes" 
              :key="cls.className" 
              shadow="hover"
              class="class-card"
              @click="selectTeacher(cls)"
            >
              <div class="class-info">
                <div class="class-name">{{ cls.className }}</div>
                <div class="class-metrics">
                  <div class="metric">
                    <div class="metric-label">总体增值</div>
                    <div class="metric-value highlight">{{ (cls.overallValueAdded || 0).toFixed(2) }}</div>
                  </div>
                  <div class="metric">
                    <div class="metric-label">学生数量</div>
                    <div class="metric-value">{{ cls.totalStudents }}</div>
                  </div>
                </div>
              </div>
            </el-card>
          </div>
        </el-collapse-item>
      </el-collapse>
    </el-card>
    
    <!-- 返回按钮，当显示具体教师数据时可返回学校班级选择 -->
    <div v-if="currentTeacher" class="back-button-container">
      <el-button type="primary" plain icon="el-icon-back" @click="backToSelection">
        返回班级列表
      </el-button>
    </div>
    
    <!-- 教师增值详情区域 - 仅在选择了具体班级后显示 -->
    <div v-if="currentTeacher" class="teacher-detail-container">
      <!-- 原有的教师增值概览、分层分析等卡片 -->
    </div>
    
    <!-- 在页面底部添加 -->
    <div v-if="isDevelopment" class="debug-panel">
      <el-button @click="showDebugData" type="info" size="small">显示API数据</el-button>
    </div>
  </div>
</template>

<script>
import * as echarts from 'echarts'
import educationData from '@/api/education-data'

// 辅助函数 - 定义在组件外部
function getWeightedAbilityScore(layerData, ...targetLayerIndices) {
  // 找出匹配的层次数据
  const matchingLayers = layerData.filter((item) => {
    // 如果是按层次名称匹配
    if (typeof targetLayerIndices[0] === 'string') {
      return targetLayerIndices.includes(item.layer);
    }
    
    // 按索引匹配 - 将层次名称转换为A、B、C、D、E类的索引
    const layerIndex = ['A类', 'B类', 'C类', 'D类', 'E类'].findIndex(prefix => 
      item.layer.includes(prefix));
    return targetLayerIndices.includes(layerIndex);
  });
  
  if (matchingLayers.length === 0) {
    return 50 + Math.random() * 30; // 默认随机值
  }
  
  // 计算加权平均值
  const totalStudents = matchingLayers.reduce((sum, layer) => sum + layer.studentCount, 0);
  const weightedSum = matchingLayers.reduce((sum, layer) => 
    sum + (layer.valueAdded * layer.studentCount), 0);
  
  // 转换为0-100分数范围
  return Math.min(95, Math.max(30, (weightedSum / totalStudents) * 4));
}

function generateTeachingAdvice(layerData, abilityDimensions) {
  const advice = {
    strengths: [],
    improvements: [],
    strategies: []
  };
  
  // 根据能力维度生成优势
  if (abilityDimensions.topStudentTeaching > 85) {
    advice.strengths.push('优秀学生培养成效显著，在保持高分学生成绩的同时有效提升其综合能力');
  }
  
  if (abilityDimensions.middleStudentImprovement > 80) {
    advice.strengths.push('对中等生的提升效果突出，有效帮助大部分学生取得进步');
  }
  
  if (abilityDimensions.weakStudentSupport > 80) {
    advice.strengths.push('后进生帮扶措施有效，基础薄弱学生进步明显');
  }
  
  if (abilityDimensions.balancedDevelopment > 85) {
    advice.strengths.push('教学覆盖面广，各层次学生均衡发展，体现了优质的教学管理能力');
  }
  
  // 确保至少有一项优势
  if (advice.strengths.length === 0) {
    const highestAbility = Object.entries(abilityDimensions)
      .sort((a, b) => b[1] - a[1])[0];
    
    switch (highestAbility[0]) {
      case 'topStudentTeaching':
        advice.strengths.push('在优等生培养方面展现出较好的教学能力');
        break;
      case 'middleStudentImprovement':
        advice.strengths.push('对中等生的辅导和提升效果较好');
        break;
      case 'weakStudentSupport':
        advice.strengths.push('关注基础薄弱学生，帮扶措施有一定成效');
        break;
      case 'balancedDevelopment':
        advice.strengths.push('教学覆盖面较广，关注各层次学生的发展');
        break;
      case 'potentialExploration':
        advice.strengths.push('善于挖掘学生潜能，激发学习积极性');
        break;
    }
  }
  
  // 分析层次数据
  let lowestLayerValueAdded = Infinity;
  let lowestLayer = '';
  
  for (const layer of layerData) {
    if (layer.valueAdded < lowestLayerValueAdded) {
      lowestLayerValueAdded = layer.valueAdded;
      lowestLayer = layer.layer;
    }
  }
  
  // 添加基于层次的建议
  if (lowestLayer && lowestLayerValueAdded < 10) {
    advice.improvements.push(`${lowestLayer}学生增值较低，建议加强针对性辅导`);
  }
  
  // 生成改进建议
  if (abilityDimensions.topStudentTeaching < 70) {
    advice.improvements.push('优等生培养体系有待完善，建议增强拔高训练');
  }
  
  if (abilityDimensions.middleStudentImprovement < 65) {
    advice.improvements.push('中等生提升空间较大，可加强针对性辅导');
  }
  
  if (abilityDimensions.weakStudentSupport < 60) {
    advice.improvements.push('后进生帮扶措施效果不明显，需调整辅导策略');
  }
  
  if (abilityDimensions.balancedDevelopment < 70) {
    advice.improvements.push('各层次学生发展不均衡，建议调整资源分配和关注度');
  }
  
  // 确保至少有一项改进建议
  if (advice.improvements.length === 0) {
    const lowestAbility = Object.entries(abilityDimensions)
      .sort((a, b) => a[1] - b[1])[0];
    
    switch (lowestAbility[0]) {
      case 'topStudentTeaching':
        advice.improvements.push('可进一步优化优等生培养策略，提供更多发展机会');
        break;
      case 'middleStudentImprovement':
        advice.improvements.push('中等生提升策略可更加个性化，关注不同学生的学习需求');
        break;
      case 'weakStudentSupport':
        advice.improvements.push('可进一步完善后进生帮扶体系，建立更有效的学习支持机制');
        break;
      case 'balancedDevelopment':
        advice.improvements.push('可进一步平衡各层次学生的教学资源分配');
        break;
      case 'potentialExploration':
        advice.improvements.push('可采用更多元化的教学方法，挖掘学生多方面潜能');
        break;
    }
  }
  
  // 生成教学策略
  advice.strategies = [
    '结合学生层次数据，实施分层教学，提供差异化学习材料和任务',
    '建立每周一次的"生生互助"小组，由优等生带领中等生和后进生共同学习',
    '利用"微课程资源库"，为不同层次学生提供针对性的自主学习材料',
    '设计"进阶式作业"，包含基础、提高和挑战三个层次，学生可根据能力选择完成',
    '定期开展"一对一辅导"，关注学习困难学生的具体问题',
    '利用数字化工具进行学情追踪，及时调整教学策略'
  ];
  
  // 随机选择3-4条策略
  const strategyCount = 3 + Math.floor(Math.random() * 2);
  advice.strategies = advice.strategies
    .sort(() => Math.random() - 0.5)
    .slice(0, strategyCount);
  
  return advice;
}

export default {
  name: 'TeacherValueAddedPage',
  data() {
    /**
     * 组件数据
     * 
     * Returns:
     *   包含组件数据的对象
     */
    return {
      // 筛选表单
      filterForm: {
        region: '',
        stage: '',
        grade: '',
        subject: '',
        targetExam: '',
        baselineExam: '',
        teacher: ''
      },
      
      // 选项数据
      regionOptions: [],
      stageOptions: [
        { value: 'elementary', label: '小学' },
        { value: 'junior', label: '初中' },
        { value: 'senior', label: '高中' }
      ],
      gradeOptions: [],
      subjectOptions: [],
      examOptions: [],
      teacherOptions: [],
      
      // 页面数据
      overviewData: {
        regionAvg: 0,
        schoolAvg: 0, 
        subjectAvg: 0
      },
      teacherRankingData: [],
      schoolRankingData: [],
      currentTeacher: null,
      
      // 分页
      pagination: {
        currentPage: 1,
        pageSize: 10,
        total: 0
      },
      
      // 图表实例
      trendChart: null,
      comparisonChart: null,
      layerChart: null,
      
      // 能力分析数据
      abilityScores: {
        overall: 78.5,
        topStudents: 85.2,
        middleStudents: 76.8,
        bottomStudents: 68.3,
        progress: 82.1
      },
      abilityLabels: {
        overall: '整体提升能力',
        topStudents: '优等生培养',
        middleStudents: '中等生提升',
        bottomStudents: '学困生帮扶',
        progress: '学生进步率'
      },
      
      // 教学特点
      teachingFeatures: [
        '善于激发学习兴趣',
        '教学方法多样化',
        '重视基础知识',
        '个性化辅导',
        '注重思维培养',
        '课堂氛围活跃'
      ],
      
      // 教学总结
      teachingSummary: '该教师教学风格活泼生动，善于激发学生学习兴趣，特别擅长帮助中等生提升成绩。教学过程中注重基础知识的巩固，同时培养学生的思维能力。建议在学困生的针对性辅导方面进一步加强，可以尝试更多的分层教学策略。',
      
      // 学生层级数据
      layerData: {
        labels: ['优等生', '中等生', '学困生'],
        beforeScores: [85, 72, 45],
        afterScores: [92, 82, 58]
      },
      
      // 图表实例
      charts: {
        trendChart: null,
        comparisonChart: null,
        layerChart: null
      },
      
      isLoading: false,
      // 添加模拟数据标志
      useMockData: true,
      
      // 从CommonFilterSelector移植的数据属性
      // 区域相关
      selectedDistrict: '',
      districts: [],
      loadingRegions: false,
      
      // 学段相关
      selectedEducationStage: '',
      educationStages: [
        { value: 'elementary', label: '小学' },
        { value: 'junior', label: '初中' },
        { value: 'senior', label: '高中' }
      ],
      
      // 年级相关
      selectedGrade: '',
      grades: [],
      loadingGrades: false,
      
      // 考试相关
      selectedExams: [],
      examList: [],
      loadingExams: false,
      
      // 学科相关
      selectedSubject: '',
      subjectList: [],
      loadingSubjects: false,
      
      // 图表实例
      chartInstances: {},
      
      // 确保初始化时有默认值
      teacherData: [],
      
      // 默认能力维度（用于没有数据时显示）
      defaultAbilityDimensions: {
        topStudentTeaching: 0,
        middleStudentImprovement: 0,
        weakStudentSupport: 0,
        balancedDevelopment: 0,
        potentialExploration: 0
      },
      
      // 学校-班级选择数据
      schoolsData: [],
      activeSchools: [],
      dataLoaded: false,
      isDevelopment: process.env.NODE_ENV === 'development'
    }
  },
  
  computed: {
    /**
     * 根据所选学段过滤年级列表
     * 
     * @returns {Array} 过滤后的年级列表
     */
    filteredGrades() {
      if (!this.selectedEducationStage || !this.grades.length) {
        return []
      }
      
      return this.grades.filter(grade => {
        const gradeLevel = parseInt(grade.grade_level || '0')
        
        if (this.selectedEducationStage === 'elementary') {
          return gradeLevel >= 1 && gradeLevel <= 6
        } else if (this.selectedEducationStage === 'junior') {
          return gradeLevel >= 7 && gradeLevel <= 9
        } else if (this.selectedEducationStage === 'senior') {
          return gradeLevel >= 10 && gradeLevel <= 12
        }
        
        return true
      })
    },
    
    /**
     * 判断是否可以开始分析
     * 
     * @returns {Boolean} 是否可以开始分析
     */
    canAnalyze() {
      // 需要至少选择区域、学段、年级、两次考试和学科
      return (
        this.selectedDistrict && 
        this.selectedEducationStage && 
        this.selectedGrade && 
        this.selectedExams.length >= 2 && 
        this.selectedSubject
      )
    },
    
    // 安全获取当前教师的能力维度
    currentTeacherAbilities() {
      return this.currentTeacher?.abilityDimensions || this.defaultAbilityDimensions;
    },
    
    // 安全获取当前教师的层次增值数据
    currentTeacherLayers() {
      return this.currentTeacher?.layerValueAdded || [];
    }
  },
  
  mounted() {
    /**
     * 组件挂载完成后执行
     */
    this.loadRegions()
    
    // 如果没有选择参数，自动加载一些模拟数据
    if (!this.selectedExams || this.selectedExams.length < 2) {
      console.log('没有足够的筛选条件，加载模拟数据');
      this.teacherData = this.generateMockTeacherData(3);
      this.currentTeacher = this.teacherData[0];
      
      this.$nextTick(() => {
        this.initCharts();
      });
      
      this.dataLoaded = true;
    } else {
      // 仅当有足够参数时调用数据加载
      this.loadTeacherValueAddedData();
    }
  },
  
  methods: {
    /**
     * 加载区域数据
     */
    async loadRegions() {
      this.loadingRegions = true
      
      try {
        const response = await educationData.getRegions()
        
        this.districts = response.data.map(region => ({
          value: region.region_id,
          label: region.region_name
        }))
      } catch (error) {
        console.error('加载区域数据失败:', error)
        this.$message.error('获取区域数据失败')
      } finally {
        this.loadingRegions = false
      }
    },
    
    /**
     * 区域变更处理
     */
    handleRegionChange() {
      // 清空后续所有选择
      this.filterForm.stage = ''
      this.filterForm.grade = ''
      this.filterForm.targetExam = ''
      this.filterForm.baselineExam = ''
      this.filterForm.subject = ''
      
      // 清空相关数据
      this.gradeOptions = []
      this.examOptions = []
      this.subjectOptions = []
      this.currentTeacher = null
    },
    
    /**
     * 处理学段变更
     */
    handleStageChange() {
      // 清空后续所有选择
      this.selectedGrade = ''
      this.selectedExams = []
      this.selectedSubject = ''
      
      // 清空相关数据
      this.grades = []
      this.examList = []
      this.subjectList = []
      
      // 清空教师数据
      this.currentTeacher = null
      
      // 加载该学段对应的年级
      this.loadGradesByStage()
    },
    
    /**
     * 根据学段加载年级
     */
    async loadGradesByStage() {
      if (!this.selectedEducationStage) {
        return
      }
      
      this.loadingGrades = true
      
      try {
        const response = await educationData.getGradesWithGraduationInfo({
          stage: this.selectedEducationStage
        })
        
        if (response.data && Array.isArray(response.data)) {
          this.grades = response.data.map(grade => ({
            value: grade.grade_id,
            label: grade.grade_name,
            grade_level: grade.grade_level
          }))
          
          console.log(`已加载${this.grades.length}个年级数据`)
        } else {
          console.warn('API返回的年级数据格式不正确:', response.data)
          this.grades = []
        }
      } catch (error) {
        console.error('加载年级数据失败:', error)
        this.$message.error('获取年级数据失败')
        this.grades = []
      } finally {
        this.loadingGrades = false
      }
    },
    
    /**
     * 处理年级变更
     */
    handleGradeChange() {
      // 清空后续所有选择
      this.selectedExams = []
      this.selectedSubject = ''
      
      // 清空相关数据
      this.examList = []
      this.subjectList = []
      
      // 清空教师数据
      this.currentTeacher = null
      
      // 加载该年级的考试数据
      this.loadExamsByGrade()
    },
    
    /**
     * 根据年级加载考试数据
     */
    async loadExamsByGrade() {
      if (!this.selectedGrade) {
        return
      }
      
      this.loadingExams = true
      this.examList = []
      
      try {
        // 确保请求参数中包含年级信息
        const response = await educationData.getExams({
          grade: this.selectedGrade,
          stage: this.selectedEducationStage,
          region: this.selectedDistrict
        })
        
        if (response.data && Array.isArray(response.data)) {
          // 先获取完整考试列表
          const allExams = response.data.map(exam => ({
            exam_id: exam.exam_id,
            exam_name: exam.exam_name || '未命名考试',
            exam_date: exam.exam_date || exam.start_time || null,
            grade: exam.grade || {},
            grade_id: exam.grade?.grade_id || null,
            grade_name: exam.grade?.grade_name || '',
            grade_level: exam.grade?.grade_level || '',
            subject: exam.subject || null
          }))
          
          // 明确进行年级筛选
          this.examList = allExams.filter(exam => {
            // 提取考试名称中的年级信息
            const examNameLower = exam.exam_name.toLowerCase()
            
            // 筛选方式1: 根据考试关联的年级ID直接匹配
            if (exam.grade_id && exam.grade_id === this.selectedGrade) {
              return true
            }
            
            // 筛选方式2: 尝试从考试名称中判断年级
            // 检查考试名称是否包含"八年级"或"8年级"等字样
            const gradeMatch = examNameLower.includes('八年级') || 
                              examNameLower.includes('8年级') ||
                              examNameLower.includes('八年') ||
                              (this.selectedGrade.toString().includes('8') && examNameLower.includes('年级'))
            
            return gradeMatch
          })
          
          console.log(`筛选后的考试数量: ${this.examList.length}/${allExams.length}`)
          
          // 按日期排序
          this.sortExamsByDate()
          
          if (this.examList.length === 0) {
            this.$message.warning(`未找到${this.selectedGrade}年级的考试数据`)
          }
        } else {
          console.warn('API返回的考试数据格式不正确:', response.data)
          this.examList = []
        }
      } catch (error) {
        console.error('加载考试数据失败:', error)
        this.$message.error('获取考试数据失败')
        this.examList = []
      } finally {
        this.loadingExams = false
      }
    },
    
    /**
     * 按考试日期排序考试列表
     */
    sortExamsByDate() {
      // 检查examList是否为数组
      if (!Array.isArray(this.examList)) {
        console.warn('考试列表不是数组，无法排序', this.examList)
        // 确保examList始终是数组
        this.examList = []
        return
      }
      
      // 过滤掉null和undefined值
      this.examList = this.examList.filter(exam => exam != null)
      
      // 然后进行排序
      this.examList.sort((a, b) => {
        // 按考试日期降序排列（最新的考试排在前面）
        const dateA = new Date(a.exam_date || a.start_time || 0)
        const dateB = new Date(b.exam_date || b.start_time || 0)
        return dateB - dateA
      })
    },
    
    /**
     * 获取考试显示标签
     */
    getExamLabel(exam) {
      if (!exam) return '未知考试'
      
      let label = exam.exam_name || '未命名考试'
      
      // 如果有考试日期，添加到标签中
      if (exam.exam_date) {
        const date = new Date(exam.exam_date)
        if (!isNaN(date.getTime())) {
          label += ` (${date.getFullYear()}-${(date.getMonth() + 1).toString().padStart(2, '0')}-${date.getDate().toString().padStart(2, '0')})`
        }
      }
      
      return label
    },
    
    /**
     * 处理考试变更事件
     */
    handleExamChange() {
      // 清空学科选择
      this.selectedSubject = ''
      this.subjectList = []
      
      // 清空教师数据
      this.currentTeacher = null
      
      // 如果选择了至少两次考试，加载学科数据
      if (this.selectedExams.length >= 2) {
        this.loadSubjectsByExams()
      }
    },
    
    /**
     * 根据考试加载学科数据
     */
    async loadSubjectsByExams() {
      if (this.selectedExams.length < 2) {
        return
      }
      
      this.loadingSubjects = true
      this.subjectList = []
      
      try {
        // 这里需要根据API的实际情况调整
        const response = await educationData.getSubjects({
          grade_id: this.selectedGrade,
          exams: this.selectedExams
        })
        
        if (response.data && Array.isArray(response.data)) {
          this.subjectList = response.data
          console.log(`已加载${this.subjectList.length}个学科数据`)
        } else {
          console.warn('API返回的学科数据格式不正确:', response.data)
          this.subjectList = []
          this.mockSubjectData() // 如果API失败，使用模拟数据
        }
      } catch (error) {
        console.error('加载学科数据失败:', error)
        this.$message.error('获取学科数据失败')
        this.mockSubjectData() // 如果API失败，使用模拟数据
      } finally {
        this.loadingSubjects = false
      }
    },
    
    /**
     * 生成模拟学科数据
     */
    mockSubjectData() {
      this.subjectList = [
        { subject_id: 'MATH', subject_name: '数学' },
        { subject_id: 'CHINESE', subject_name: '语文' },
        { subject_id: 'ENGLISH', subject_name: '英语' },
        { subject_id: 'PHYSICS', subject_name: '物理' },
        { subject_id: 'CHEMISTRY', subject_name: '化学' }
      ]
    },
    
    /**
     * 处理学科变更事件
     */
    handleSubjectChange() {
      // 清空教师数据
      this.currentTeacher = null
    },
    
    /**
     * 发送变更事件（区域变更时触发）
     */
    emitChange() {
      // 清空后续所有选择
      this.selectedEducationStage = ''
      this.selectedGrade = ''
      this.selectedExams = []
      this.selectedSubject = ''
      
      // 清空相关数据
      this.grades = []
      this.examList = []
      this.subjectList = []
      
      // 清空教师数据
      this.currentTeacher = null
    },
    
    /**
     * 根据筛选条件加载教师增值数据
     */
    async loadData() {
      // 检查是否有足够的筛选条件
      if (!this.filterForm.subject || !this.filterForm.targetExam || !this.filterForm.baselineExam) {
        console.warn('筛选条件不足，无法加载数据')
        return
      }
      
      this.isLoading = true
      
      try {
        // 构建筛选参数
        const params = {
          region: this.filterForm.region,
          stage: this.filterForm.stage,
          grade: this.filterForm.grade,
          subject: this.filterForm.subject,
          targetExam: this.filterForm.targetExam,
          baselineExam: this.filterForm.baselineExam,
          page: this.pagination.currentPage,
          pageSize: this.pagination.pageSize
        }
        
        // 直接使用模拟数据
        if (this.useMockData) {
          this.mockTeacherData()
          this.$nextTick(() => {
            this.initCharts()
          })
          return
        }
        
        // 调用API获取数据
        const response = await educationData.getTeacherValueAddedData(params)
        
        if (response && response.data) {
          this.processApiResponse(response.data)
          
          // 初始化图表
          this.$nextTick(() => {
            this.initCharts()
          })
          
          this.$notify({
            title: '成功',
            message: '教师增值数据加载成功',
            type: 'success'
          })
        } else {
          throw new Error('返回数据格式不正确')
        }
      } catch (error) {
        console.error('加载教师增值数据失败:', error)
        this.$message.error('加载教师增值数据失败，使用模拟数据')
        
        // 获取失败时使用模拟数据
        this.mockTeacherData()
        this.$nextTick(() => {
          this.initCharts()
        })
      } finally {
        this.isLoading = false
      }
    },
    
    /**
     * 处理API返回的数据
     */
    processApiResponse(data) {
      // 处理教师排名数据
      this.teacherRankingData = data.teacherRanking || []
      
      // 为教师数据添加唯一ID（如果后端未提供）
      this.teacherRankingData = this.teacherRankingData.map((teacher, index) => {
        if (!teacher.teacherId) {
          teacher.teacherId = `T${index + 1}`.padStart(4, '0')
        }
        return teacher
      })
      
      // 更新教师选项
      this.teacherOptions = this.teacherRankingData.map(teacher => ({
        value: teacher.teacherId,
        label: teacher.teacherName
      }))
      
      // 处理学校排名数据
      this.schoolRankingData = data.schoolRanking || []
      
      // 处理概览数据
      this.overviewData = data.overview || {
        regionAvg: 0,
        schoolAvg: 0,
        subjectAvg: 0
      }
      
      // 更新分页信息
      this.pagination.total = data.total || 0
      
      // 默认选择第一个教师
      if (this.teacherRankingData.length > 0 && !this.filterForm.teacher) {
        this.filterForm.teacher = this.teacherRankingData[0].teacherId
        this.currentTeacher = this.teacherRankingData[0]
      } else {
        this.currentTeacher = null
      }
    },
    
    /**
     * 加载教师详细数据
     */
    loadTeacherData() {
      if (!this.filterForm.teacher) return
      
      // 找到选中的教师
      const selectedTeacher = this.teacherRankingData.find(
        t => t.teacherId === this.filterForm.teacher
      )
      
      if (selectedTeacher) {
        this.currentTeacher = selectedTeacher
        this.$nextTick(() => {
          this.initCharts()
        })
      }
    },
    
    /**
     * 加载教师列表
     */
    loadTeachers() {
      if (!this.filterForm.targetExam || !this.filterForm.baselineExam) {
        return
      }
      
      this.loadData()
    },
    
    /**
     * 初始化图表
     * 
     * 初始化所有需要的图表
     */
    initCharts() {
      if (this.currentTeacher) {
        this.initTrendChart()
        this.initComparisonChart()
        this.initLayerChart()
        this.initAbilityRadarChart()
      }
    },
    
    /**
     * 初始化趋势图表
     * 
     * 初始化教师增值趋势图表
     */
    initTrendChart() {
      const chartDom = document.getElementById('teacherTrendChart')
      if (!chartDom) return
      
      this.trendChart = echarts.init(chartDom)
      
      // 模拟数据
      const option = {
        tooltip: {
          trigger: 'axis'
        },
        legend: {
          data: ['增值分数', '区域平均']
        },
        grid: {
          left: '3%',
          right: '4%',
          bottom: '3%',
          containLabel: true
        },
        xAxis: {
          type: 'category',
          boundaryGap: false,
          data: ['2022上学期', '2022下学期', '2023上学期', '2023下学期', '2024上学期']
        },
        yAxis: {
          type: 'value',
          name: '增值分数'
        },
        series: [
          {
            name: '增值分数',
            type: 'line',
            data: [65, 70, 80, 85, 88],
            itemStyle: {
              color: '#409EFF'
            },
            lineStyle: {
              width: 3
            },
            emphasis: {
              focus: 'series'
            }
          },
          {
            name: '区域平均',
            type: 'line',
            data: [60, 62, 65, 68, 70],
            itemStyle: {
              color: '#909399'
            },
            lineStyle: {
              width: 2,
              type: 'dashed'
            }
          }
        ]
      }
      
      this.trendChart.setOption(option)
      window.addEventListener('resize', this.trendChart.resize)
    },
    
    /**
     * 初始化比较图表
     * 
     * 初始化教师与同学科教师的比较图表
     */
    initComparisonChart() {
      const chartDom = document.getElementById('teacherComparisonChart')
      if (!chartDom) return
      
      this.comparisonChart = echarts.init(chartDom)
      
      // 模拟数据
      const option = {
        tooltip: {
          trigger: 'axis',
          axisPointer: {
            type: 'shadow'
          }
        },
        legend: {
          show: false
        },
        grid: {
          left: '3%',
          right: '4%',
          bottom: '3%',
          containLabel: true
        },
        xAxis: {
          type: 'value',
          name: '增值分数'
        },
        yAxis: {
          type: 'category',
          data: ['教师A', '教师B', '教师C', this.currentTeacher.teacherName, '教师E']
        },
        series: [
          {
            name: '增值分数',
            type: 'bar',
            data: [
              65,
              70,
              75,
              {
                value: this.currentTeacher.valueAdded,
                itemStyle: {
                  color: '#409EFF'
                }
              },
              60
            ],
            emphasis: {
              itemStyle: {
                shadowBlur: 10,
                shadowOffsetX: 0,
                shadowColor: 'rgba(0, 0, 0, 0.5)'
              }
            }
          }
        ]
      }
      
      this.comparisonChart.setOption(option)
      window.addEventListener('resize', this.comparisonChart.resize)
    },
    
    /**
     * 初始化学生层级图表
     * 
     * 初始化不同层级学生增值情况图表
     */
    initLayerChart() {
      if (!this.currentTeacher) {
        console.warn('当前没有选中的教师数据，无法初始化层次增值图表');
        return;
      }
      
      // 防御性检查：确保layerValueAdded存在且是数组
      if (!this.currentTeacher.layerValueAdded || !Array.isArray(this.currentTeacher.layerValueAdded)) {
        console.warn('教师层次增值数据不存在或格式不正确', this.currentTeacher);
        // 创建一个空的图表或显示提示信息
        const chartDom = document.getElementById('layerValueAddedChart');
        if (chartDom) {
          const chart = echarts.init(chartDom);
          chart.setOption({
            title: {
              text: '暂无层次增值数据',
              left: 'center',
              top: 'center',
              textStyle: {
                color: '#999',
                fontSize: 16
              }
            }
          });
          this.layerChart = chart;
        }
        return;
      }
      
      const chartDom = document.getElementById('layerValueAddedChart');
      if (!chartDom) {
        console.warn('找不到图表DOM元素：layerValueAddedChart');
        return;
      }
      
      const chart = echarts.init(chartDom);
      
      // 安全地访问数据
      const layers = this.currentTeacher.layerValueAdded.map(item => item.layer || '未知层次');
      const valueAdded = this.currentTeacher.layerValueAdded.map(item => item.valueAdded || 0);
      const studentCounts = this.currentTeacher.layerValueAdded.map(item => item.studentCount || 0);
      
      // 图表配置
      const option = {
        tooltip: {
          trigger: 'axis',
          axisPointer: {
            type: 'shadow'
          }
        },
        legend: {
          data: ['增值分数', '学生人数']
        },
        grid: {
          left: '3%',
          right: '4%',
          bottom: '3%',
          containLabel: true
        },
        xAxis: {
          type: 'category',
          data: layers
        },
        yAxis: [
          {
            type: 'value',
            name: '增值分数',
            min: 0,
            axisLabel: {
              formatter: '{value}'
            }
          },
          {
            type: 'value',
            name: '学生人数',
            min: 0,
            axisLabel: {
              formatter: '{value}人'
            }
          }
        ],
        series: [
          {
            name: '增值分数',
            type: 'bar',
            data: valueAdded
          },
          {
            name: '学生人数',
            type: 'line',
            yAxisIndex: 1,
            data: studentCounts
          }
        ]
      };
      
      chart.setOption(option);
      this.layerChart = chart;
    },
    
    /**
     * 初始化能力雷达图
     */
    initAbilityRadarChart() {
      if (!this.currentTeacher) {
        console.warn('当前没有选中的教师数据，无法初始化能力雷达图');
        return;
      }
      
      // 防御性检查：确保abilityDimensions存在
      if (!this.currentTeacher.abilityDimensions) {
        console.warn('教师能力维度数据不存在', this.currentTeacher);
        
        // 创建一个空的雷达图或显示提示信息
        const chartDom = document.getElementById('abilityRadarChart');
        if (chartDom) {
          const chart = echarts.init(chartDom);
          chart.setOption({
            title: {
              text: '暂无能力维度数据',
              left: 'center',
              top: 'center',
              textStyle: {
                color: '#999',
                fontSize: 16
              }
            }
          });
          this.abilityChart = chart;
        }
        return;
      }
      
      const chartDom = document.getElementById('abilityRadarChart');
      if (!chartDom) {
        console.warn('找不到图表DOM元素：abilityRadarChart');
        return;
      }
      
      const chart = echarts.init(chartDom);
      
      // 安全地获取能力维度数据
      const abilities = Object.keys(this.currentTeacher.abilityDimensions);
      const values = abilities.map(key => this.currentTeacher.abilityDimensions[key] || 0);
      
      // 能力维度中文标签映射
      const abilityLabels = {
        topStudentTeaching: '优等生培养',
        middleStudentImprovement: '中等生提升',
        weakStudentSupport: '后进生帮扶',
        balancedDevelopment: '均衡发展',
        potentialExploration: '潜能激发'
      };
      
      const option = {
        tooltip: {
          trigger: 'item'
        },
        radar: {
          indicator: abilities.map(key => ({
            name: abilityLabels[key] || key,
            max: 100
          }))
        },
        series: [
          {
            type: 'radar',
            data: [
              {
                value: values,
                name: '教师能力',
                areaStyle: {
                  color: 'rgba(64, 158, 255, 0.6)'
                },
                lineStyle: {
                  color: '#409EFF',
                  width: 2
                },
                itemStyle: {
                  color: '#409EFF'
                }
              }
            ]
          }
        ]
      };
      
      chart.setOption(option);
      this.abilityChart = chart;
    },
    
    /**
     * 获取百分位颜色
     * 
     * Args:
     *   percentile: 百分位数值
     * 
     * Returns:
     *   颜色值
     */
    getPercentileColor(percentile) {
      if (percentile >= 80) return '#67C23A'
      if (percentile >= 60) return '#409EFF'
      if (percentile >= 40) return '#E6A23C'
      return '#F56C6C'
    },
    
    /**
     * 获取进度条颜色
     * 
     * Args:
     *   value: 进度值
     * 
     * Returns:
     *   颜色值
     */
    getProgressColor(value) {
      if (value >= 80) return '#67C23A'
      if (value >= 60) return '#409EFF'
      if (value >= 40) return '#E6A23C'
      return '#F56C6C'
    },
    
    /**
     * 获取排名样式类
     * 
     * Args:
     *   rank: 排名值
     * 
     * Returns:
     *   CSS类名
     */
    getRankClass(rank) {
      if (rank <= 3) return 'top-rank'
      if (rank <= 10) return 'good-rank'
      return 'normal-rank'
    },
    
    /**
     * 获取分数样式类
     * 
     * Args:
     *   value: 分数值
     * 
     * Returns:
     *   CSS类名
     */
    getValueClass(value) {
      if (value >= 85) return 'excellent-value'
      if (value >= 70) return 'good-value'
      if (value >= 60) return 'average-value'
      return 'below-value'
    },
    
    /**
     * 获取百分位样式类
     * 
     * Args:
     *   percentile: 百分位值
     * 
     * Returns:
     *   CSS类名
     */
    getPercentileClass(percentile) {
      if (percentile >= 90) return 'excellent-percentile'
      if (percentile >= 75) return 'good-percentile'
      if (percentile >= 50) return 'average-percentile'
      return 'below-percentile'
    },
    
    /**
     * 获取标签类型
     * 
     * Args:
     *   index: 标签索引
     * 
     * Returns:
     *   标签类型
     */
    getTagType(index) {
      const types = ['', 'success', 'info', 'warning', 'danger']
      return types[index % types.length]
    },
    
    /**
     * 处理页面大小变化
     * 
     * Args:
     *   size: 新的页面大小
     */
    handleSizeChange(size) {
      this.pagination.pageSize = size
      this.loadData()
    },
    
    /**
     * 处理当前页变化
     * 
     * Args:
     *   page: 新的页码
     */
    handleCurrentChange(page) {
      this.pagination.currentPage = page
      this.loadData()
    },
    
    /**
     * 生成模拟教师数据
     */
    mockTeacherData() {
      // 模拟教师排名数据
      const mockTeachers = [
        { teacherId: 'T001', teacherName: '张老师', school: '实验中学', subject: '数学', rank: 1, valueAdded: 93.5, percentile: 95 },
        { teacherId: 'T002', teacherName: '李老师', school: '第一中学', subject: '数学', rank: 2, valueAdded: 87.2, percentile: 85 },
        { teacherId: 'T003', teacherName: '王老师', school: '实验中学', subject: '数学', rank: 3, valueAdded: 82.9, percentile: 75 },
        { teacherId: 'T004', teacherName: '赵老师', school: '第二中学', subject: '数学', rank: 4, valueAdded: 78.4, percentile: 65 },
        { teacherId: 'T005', teacherName: '刘老师', school: '第三中学', subject: '数学', rank: 5, valueAdded: 73.8, percentile: 55 }
      ]
      
      this.teacherRankingData = mockTeachers
      
      // 更新教师选项
      this.teacherOptions = mockTeachers.map(t => ({
        value: t.teacherId,
        label: t.teacherName
      }))
      
      // 模拟学校排名数据
      this.schoolRankingData = [
        { schoolName: '实验中学', valueAdded: 87.2 },
        { schoolName: '第一中学', valueAdded: 82.5 },
        { schoolName: '第二中学', valueAdded: 78.4 },
        { schoolName: '第三中学', valueAdded: 75.8 },
        { schoolName: '第四中学', valueAdded: 72.3 }
      ]
      
      // 模拟概览数据
      this.overviewData = {
        regionAvg: 78.5,
        schoolAvg: 82.6,
        subjectAvg: 79.8
      }
      
      // 更新分页信息
      this.pagination.total = mockTeachers.length
      
      // 默认选择第一个教师
      if (mockTeachers.length > 0) {
        this.currentTeacher = mockTeachers[0]
      }
      
      // 模拟下拉选项
      if (this.regionOptions.length === 0) {
        this.regionOptions = [
          { value: 'region1', label: '开平市' },
          { value: 'region2', label: '恩平市' },
          { value: 'region3', label: '台山市' }
        ]
      }
      
      if (this.gradeOptions.length === 0) {
        this.gradeOptions = [
          { value: '7', label: '七年级' },
          { value: '8', label: '八年级' },
          { value: '9', label: '九年级' }
        ]
      }
      
      if (this.examOptions.length === 0) {
        this.examOptions = [
          { value: 'exam1', label: '2023年1月期中考试' },
          { value: 'exam2', label: '2023年6月期末考试' },
          { value: 'exam3', label: '2023年9月期初考试' }
        ]
      }
    },
    
    /**
     * 开始分析
     * 加载教师增值分析数据
     */
    startAnalysis() {
      this.loadTeacherData()
    },
    
    /**
     * 重置所有筛选条件
     */
    resetFilters() {
      // 清空筛选表单
      this.filterForm = {
        region: '',
        stage: '',
        grade: '',
        subject: '',
        targetExam: '',
        baselineExam: '',
        teacher: ''
      }
      
      // 清空选项数据(保留区域和学段选项)
      this.gradeOptions = []
      this.subjectOptions = []
      this.examOptions = []
      this.teacherOptions = []
      
      // 清空分析结果
      this.currentTeacher = null
      this.teacherRankingData = []
      this.schoolRankingData = []
      this.overviewData = {
        regionAvg: 0,
        schoolAvg: 0,
        subjectAvg: 0
      }
      
      // 重新加载区域数据
      this.loadRegions()
    },
    
    /**
     * 处理目标考试变更
     */
    handleTargetExamChange() {
      // 清空学科选择
      this.filterForm.subject = ''
      this.subjectOptions = []
      this.currentTeacher = null
      
      // 检查是否可以加载学科
      if (this.filterForm.targetExam && this.filterForm.baselineExam) {
        this.loadSubjectsByExams()
      }
    },
    
    /**
     * 处理基准考试变更
     */
    handleBaselineExamChange() {
      // 清空学科选择
      this.filterForm.subject = ''
      this.subjectOptions = []
      this.currentTeacher = null
      
      // 检查是否可以加载学科
      if (this.filterForm.targetExam && this.filterForm.baselineExam) {
        this.loadSubjectsByExams()
      }
    },
    
    /**
     * 模拟考试数据（当API调用失败时使用）
     */
    mockExamData() {
      const stage = this.filterForm.stage
      let mockExams = []
      
      if (stage === 'elementary') {
        // 小学考试
        mockExams = [
          { value: 'elem-exam1', label: '2023年小学期中考试' },
          { value: 'elem-exam2', label: '2023年小学期末考试' }
        ]
      } else if (stage === 'junior') {
        // 初中考试
        mockExams = [
          { value: 'junior-exam1', label: '2023年初中期中考试' },
          { value: 'junior-exam2', label: '2023年初中期末考试' }
        ]
      } else if (stage === 'senior') {
        // 高中考试
        mockExams = [
          { value: 'senior-exam1', label: '2023年高中期中考试' },
          { value: 'senior-exam2', label: '2023年高中期末考试' }
        ]
      } else {
        // 通用考试
        mockExams = [
          { value: 'exam1', label: '2023年1月期中考试' },
          { value: 'exam2', label: '2023年6月期末考试' }
        ]
      }
      
      this.examOptions = mockExams
    },
    
    /**
     * 加载教师增值数据
     */
    async loadTeacherValueAddedData() {
      this.loading = true;
      this.dataLoaded = false;
      
      try {
        // 构建参数
        const params = {
          region: this.selectedDistrict,
          grade: this.selectedGrade,
          subject: this.selectedSubject,
          exams: this.selectedExams
        };
        
        // 记录请求参数
        console.log('请求教师增值数据，参数:', params);
        
        // 检查是否有足够的筛选条件
        if (!this.selectedDistrict || !this.selectedGrade || !this.selectedSubject || this.selectedExams.length < 2) {
          console.log('没有足够的筛选条件，加载模拟数据');
          this.useSimulatedData();
          return;
        }
        
        const response = await educationData.getTeacherValueAdded(params);
        
        // 添加这一行来记录原始数据
        console.log('API返回的原始数据:', response.data);
        
        // 处理数据格式
        const responseData = response.data.data || response.data;
        
        // 使用responseData变量处理数据
        if (Array.isArray(responseData) && responseData.length > 0) {
          // 标准化每个班级的数据
          this.teacherData = responseData.map(classData => ({
            teacherId: classData.classId || `${classData.schoolName}-${classData.className}`,
            teacherName: classData.className || '未知班级',
            schoolName: classData.schoolName || '未知学校',
            overallValueAdded: classData.overallValueAdded || 0,
            rank: classData.rank || 0,
            percentile: classData.percentile || 0,
            layerValueAdded: classData.layerValueAdded || [],
            abilityDimensions: classData.abilityDimensions || {
              topStudentTeaching: 0,
              middleStudentImprovement: 0,
              weakStudentSupport: 0,
              balancedDevelopment: 0,
              potentialExploration: 0
            },
            totalStudents: classData.totalStudents || 0,
            teachingAdvice: classData.teachingAdvice || {
              strengths: [],
              improvements: [],
              strategies: []
            }
          }));
          
          // 设置当前选中的班级为第一位
          this.currentTeacher = this.teacherData[0];
          
          // 按学校组织数据
          this.schoolsData = this.organizeDataBySchool(this.teacherData);
          
          // 默认展开第一个学校
          if (this.schoolsData.length > 0) {
            this.activeSchools = [this.schoolsData[0].schoolName];
          }
          
          this.$nextTick(() => {
            this.initCharts();
          });
          
          this.dataLoaded = true;
        } else {
          console.warn('API返回的数据为空，使用模拟数据');
          this.useSimulatedData();
        }
      } catch (error) {
        console.error('加载教师增值数据失败:', error);
        this.$message.error('获取教师增值数据失败');
        
        // 使用模拟数据
        this.useSimulatedData();
      } finally {
        this.loading = false;
      }
    },
    
    // 添加新方法用于加载模拟数据
    useSimulatedData() {
      this.teacherData = this.generateMockTeacherData();
      this.currentTeacher = this.teacherData[0];
      this.schoolsData = this.organizeDataBySchool(this.teacherData);
      
      // 延迟初始化图表，确保DOM已更新
      setTimeout(() => {
        this.initCharts();
      }, 100);
      
      this.dataLoaded = true;
    },
    
    /**
     * 生成模拟教师数据
     * 
     * @param {Number} count 要生成的教师数量
     * @returns {Array} 模拟教师数据数组
     */
    generateMockTeacherData(count = 5) {
      // 层次标签
      const layers = ['A类(优秀)', 'B类(良好)', 'C类(中等)', 'D类(基础)', 'E类(提升)'];
      
      // 教师名称
      const teacherNames = ['张明', '王丽', '李强', '赵华', '陈静', '周伟', '吴芳', '刘勇'];
      const schoolNames = ['育才中学', '实验中学', '第一中学', '新华中学', '光明中学'];
      const subjects = ['语文', '数学', '英语', '物理', '化学'];
      
      // 生成教师数据
      const teachers = [];
      
      for (let i = 0; i < count; i++) {
        // 基础教师信息
        const teacherName = teacherNames[Math.floor(Math.random() * teacherNames.length)];
        const schoolName = schoolNames[Math.floor(Math.random() * schoolNames.length)];
        const subject = subjects[Math.floor(Math.random() * subjects.length)];
        
        // 总体增值和学生数量
        const totalStudents = 30 + Math.floor(Math.random() * 20);
        let overallValueAdded = 0;
        
        // 生成各层次学生数据
        const layerData = [];
        const usedLayers = [];
        
        // 随机选择3-5个层次
        const layerCount = 3 + Math.floor(Math.random() * (layers.length - 2));
        for (let j = 0; j < layerCount; j++) {
          // 随机选择一个未使用的层次
          let layerIndex;
          do {
            layerIndex = Math.floor(Math.random() * layers.length);
          } while (usedLayers.includes(layerIndex));
          usedLayers.push(layerIndex);
          
          const layer = layers[layerIndex];
          
          // 层次学生数量 - 确保总数等于totalStudents
          let studentCount;
          if (j === layerCount - 1) {
            studentCount = totalStudents - layerData.reduce((sum, item) => sum + item.studentCount, 0);
          } else {
            const maxCount = totalStudents - layerData.reduce((sum, item) => sum + item.studentCount, 0) - (layerCount - j - 1);
            studentCount = Math.max(1, Math.min(maxCount, Math.floor(totalStudents / layerCount) + Math.floor(Math.random() * 10) - 5));
          }
          
          // 层次增值 - 根据层次调整增值范围
          let valueAdded;
          switch (layerIndex) {
            case 0: // 优秀层
              valueAdded = 10 + Math.random() * 15;
              break;
            case 1: // 良好层
              valueAdded = 15 + Math.random() * 10;
              break;
            case 2: // 中等层
              valueAdded = 20 + Math.random() * 10;
              break;
            case 3: // 基础层
              valueAdded = 25 + Math.random() * 15;
              break;
            case 4: // 提升层
              valueAdded = 15 + Math.random() * 20;
              break;
            default:
              valueAdded = 15 + Math.random() * 15;
          }
          
          // 基准分数和目标分数
          const baselineScore = 60 + (4 - layerIndex) * 10 + Math.random() * 5;
          const targetScore = baselineScore + valueAdded;
          
          // 计算该层对总体增值的贡献
          const layerContribution = valueAdded * studentCount / totalStudents;
          overallValueAdded += layerContribution;
          
          layerData.push({
            layer,
            studentCount,
            valueAdded,
            contribution: layerContribution / overallValueAdded, // 将在最后调整
            baselineScore,
            targetScore
          });
        }
        
        // 重新计算贡献率，确保总和为1
        layerData.forEach(layer => {
          layer.contribution = (layer.valueAdded * layer.studentCount / totalStudents) / overallValueAdded;
        });
        
        // 能力维度 - 基于层次数据生成
        const abilityDimensions = {
          topStudentTeaching: getWeightedAbilityScore(layerData, 0),
          middleStudentImprovement: getWeightedAbilityScore(layerData, 1, 2),
          weakStudentSupport: getWeightedAbilityScore(layerData, 3, 4),
          balancedDevelopment: 100 - (Math.max(...layerData.map(l => l.valueAdded)) - Math.min(...layerData.map(l => l.valueAdded))) * 2,
          potentialExploration: Math.max(...layerData.map(l => l.valueAdded)) * 3.5
        };
        
        // 标准化能力分数范围
        Object.keys(abilityDimensions).forEach(key => {
          abilityDimensions[key] = Math.max(30, Math.min(95, abilityDimensions[key]));
        });
        
        // 教学提升建议
        const teachingAdvice = generateTeachingAdvice(layerData, abilityDimensions);
        
        // 添加教师数据
        teachers.push({
          teacherId: `mock-teacher-${i + 1}`,
          teacherName: `${teacherName}老师（${subject}）`,
          schoolName: schoolName,
          subject: subject,
          overallValueAdded: parseFloat(overallValueAdded.toFixed(2)),
          rank: i + 1,
          percentile: parseFloat((100 * (count - i) / count).toFixed(1)),
          totalStudents,
          layerValueAdded: layerData,
          abilityDimensions,
          teachingAdvice
        });
      }
      
      // 根据总体增值排序
      return teachers.sort((a, b) => b.overallValueAdded - a.overallValueAdded);
    },
    
    /**
     * 生成教学提升建议
     */
    generateTeachingAdvice(layerData, abilityDimensions) {
      const advice = {
        strengths: [],
        improvements: [],
        strategies: []
      };
      
      // 根据能力维度生成优势
      if (abilityDimensions.topStudentTeaching > 85) {
        advice.strengths.push('优秀学生培养成效显著，在保持高分学生成绩的同时有效提升其综合能力');
      }
      
      if (abilityDimensions.middleStudentImprovement > 80) {
        advice.strengths.push('对中等生的提升效果突出，有效帮助大部分学生取得进步');
      }
      
      if (abilityDimensions.weakStudentSupport > 80) {
        advice.strengths.push('后进生帮扶措施有效，基础薄弱学生进步明显');
      }
      
      if (abilityDimensions.balancedDevelopment > 85) {
        advice.strengths.push('教学覆盖面广，各层次学生均衡发展，体现了优质的教学管理能力');
      }
      
      // 确保至少有一项优势
      if (advice.strengths.length === 0) {
        const highestAbility = Object.entries(abilityDimensions)
          .sort((a, b) => b[1] - a[1])[0];
        
        switch (highestAbility[0]) {
          case 'topStudentTeaching':
            advice.strengths.push('在优等生培养方面展现出较好的教学能力');
            break;
          case 'middleStudentImprovement':
            advice.strengths.push('对中等生的辅导和提升效果较好');
            break;
          case 'weakStudentSupport':
            advice.strengths.push('关注基础薄弱学生，帮扶措施有一定成效');
            break;
          case 'balancedDevelopment':
            advice.strengths.push('教学覆盖面较广，关注各层次学生的发展');
            break;
          case 'potentialExploration':
            advice.strengths.push('善于挖掘学生潜能，激发学习积极性');
            break;
        }
      }
      
      // 分析层次数据
      let lowestLayerValueAdded = Infinity;
      let lowestLayer = '';
      
      for (const layer of layerData) {
        if (layer.valueAdded < lowestLayerValueAdded) {
          lowestLayerValueAdded = layer.valueAdded;
          lowestLayer = layer.layer;
        }
      }
      
      // 添加基于层次的建议
      if (lowestLayer && lowestLayerValueAdded < 10) {
        advice.improvements.push(`${lowestLayer}学生增值较低，建议加强针对性辅导`);
      }
      
      // 生成改进建议
      if (abilityDimensions.topStudentTeaching < 70) {
        advice.improvements.push('优等生培养体系有待完善，建议增强拔高训练');
      }
      
      if (abilityDimensions.middleStudentImprovement < 65) {
        advice.improvements.push('中等生提升空间较大，可加强针对性辅导');
      }
      
      if (abilityDimensions.weakStudentSupport < 60) {
        advice.improvements.push('后进生帮扶措施效果不明显，需调整辅导策略');
      }
      
      if (abilityDimensions.balancedDevelopment < 70) {
        advice.improvements.push('各层次学生发展不均衡，建议调整资源分配和关注度');
      }
      
      // 确保至少有一项改进建议
      if (advice.improvements.length === 0) {
        const lowestAbility = Object.entries(abilityDimensions)
          .sort((a, b) => a[1] - b[1])[0];
        
        switch (lowestAbility[0]) {
          case 'topStudentTeaching':
            advice.improvements.push('可进一步优化优等生培养策略，提供更多发展机会');
            break;
          case 'middleStudentImprovement':
            advice.improvements.push('中等生提升策略可更加个性化，关注不同学生的学习需求');
            break;
          case 'weakStudentSupport':
            advice.improvements.push('可进一步完善后进生帮扶体系，建立更有效的学习支持机制');
            break;
          case 'balancedDevelopment':
            advice.improvements.push('可进一步平衡各层次学生的教学资源分配');
            break;
          case 'potentialExploration':
            advice.improvements.push('可采用更多元化的教学方法，挖掘学生多方面潜能');
            break;
        }
      }
      
      // 生成教学策略
      advice.strategies = [
        '结合学生层次数据，实施分层教学，提供差异化学习材料和任务',
        '建立每周一次的"生生互助"小组，由优等生带领中等生和后进生共同学习',
        '利用"微课程资源库"，为不同层次学生提供针对性的自主学习材料',
        '设计"进阶式作业"，包含基础、提高和挑战三个层次，学生可根据能力选择完成',
        '定期开展"一对一辅导"，关注学习困难学生的具体问题',
        '利用数字化工具进行学情追踪，及时调整教学策略'
      ];
      
      // 随机选择3-4条策略
      const strategyCount = 3 + Math.floor(Math.random() * 2);
      advice.strategies = advice.strategies
        .sort(() => Math.random() - 0.5)
        .slice(0, strategyCount);
      
      return advice;
    },
    
    /**
     * 安全地获取对象属性值，不存在时返回默认值
     * 
     * @param {Object} obj 要检查的对象
     * @param {String} path 属性路径，如 'user.name'
     * @param {*} defaultValue 默认值
     * @returns {*} 属性值或默认值
     */
    safeGet(obj, path, defaultValue = undefined) {
      if (!obj) return defaultValue;
      
      const keys = path.split('.');
      let result = obj;
      
      for (const key of keys) {
        if (result === undefined || result === null) {
          return defaultValue;
        }
        result = result[key];
      }
      
      return result === undefined ? defaultValue : result;
    },
    
    /**
     * 根据层次权重计算能力分数
     * 
     * @param {Array} layerData 层次数据数组
     * @param {Number|Array} targetLayerIndices 目标层次索引或索引数组
     * @returns {Number} 计算后的能力分数
     */
    getWeightedAbilityScore(layerData, ...targetLayerIndices) {
      // 找出匹配的层次数据
      const matchingLayers = layerData.filter((item) => {
        // 如果是按层次名称匹配
        if (typeof targetLayerIndices[0] === 'string') {
          return targetLayerIndices.includes(item.layer);
        }
        
        // 按索引匹配 - 将层次名称转换为A、B、C、D、E类的索引
        const layerIndex = ['A类', 'B类', 'C类', 'D类', 'E类'].findIndex(prefix => 
          item.layer.includes(prefix));
        return targetLayerIndices.includes(layerIndex);
      });
      
      if (matchingLayers.length === 0) {
        return 50 + Math.random() * 30; // 默认随机值
      }
      
      // 计算加权平均值
      const totalStudents = matchingLayers.reduce((sum, layer) => sum + layer.studentCount, 0);
      const weightedSum = matchingLayers.reduce((sum, layer) => 
        sum + (layer.valueAdded * layer.studentCount), 0);
      
      // 转换为0-100分数范围
      return Math.min(95, Math.max(30, (weightedSum / totalStudents) * 4));
    },
    
    // 按学校组织班级数据
    organizeDataBySchool(teacherData) {
      const schoolMap = {};
      
      // 按学校分组班级数据
      teacherData.forEach(teacher => {
        if (!schoolMap[teacher.schoolName]) {
          schoolMap[teacher.schoolName] = {
            schoolName: teacher.schoolName,
            classes: []
          };
        }
        
        schoolMap[teacher.schoolName].classes.push(teacher);
      });
      
      // 转换为数组并按学校名称排序
      return Object.values(schoolMap).sort((a, b) => 
        a.schoolName.localeCompare(b.schoolName, 'zh-CN')
      );
    },
    
    // 选择班级/教师
    selectTeacher(teacher) {
      this.currentTeacher = teacher;
      this.$nextTick(() => {
        this.initCharts();
      });
    },
    
    // 返回班级选择界面
    backToSelection() {
      this.currentTeacher = null;
    },
    
    // 在methods中添加
    showDebugData() {
      console.log('教师增值原始数据:', this.teacherData);
      console.log('当前选中教师/班级:', this.currentTeacher);
      console.log('按学校组织的数据:', this.schoolsData);
    }
  },
  
  beforeUnmount() {
    /**
     * 组件卸载前清理资源
     */
    if (this.trendChart) {
      window.removeEventListener('resize', this.trendChart.resize)
      this.trendChart.dispose()
    }
    
    if (this.comparisonChart) {
      window.removeEventListener('resize', this.comparisonChart.resize)
      this.comparisonChart.dispose()
    }
    
    if (this.layerChart) {
      window.removeEventListener('resize', this.layerChart.resize)
      this.layerChart.dispose()
    }
    
    if (this.abilityChart) {
      window.removeEventListener('resize', this.abilityChart.resize)
      this.abilityChart.dispose()
    }
    
    console.log('教师增值分析组件已卸载，资源已清理');
  }
}
</script>

<style scoped>
.teacher-value-added {
  padding: 20px;
}

.filter-section {
  background-color: #f5f7fa;
  padding: 20px;
  border-radius: 4px;
  margin-bottom: 20px;
}

/* 添加选择框宽度样式 */
:deep(.filter-select) {
  width: 100px;
}

:deep(.exam-select) {
  width: 240px; /* 考试名称通常较长，给予更多空间 */
}

.loading-container {
  margin: 40px 0;
}

.teacher-overview-card {
  margin-bottom: 20px;
}

.teacher-header {
  display: flex;
  align-items: center;
}

.teacher-avatar {
  margin-right: 20px;
}

.teacher-info {
  flex: 1;
}

.teacher-info h3 {
  margin-top: 0;
  margin-bottom: 10px;
  font-size: 22px;
}

.teacher-stats {
  display: flex;
  margin-top: 15px;
}

.stat-item {
  margin-right: 30px;
  text-align: center;
}

.stat-label {
  display: block;
  font-size: 14px;
  color: #909399;
  margin-bottom: 5px;
}

.stat-value {
  font-size: 20px;
  font-weight: bold;
}

.top-rank, .excellent-value, .excellent-percentile {
  color: #f56c6c;
}

.good-rank, .good-value, .good-percentile {
  color: #e6a23c;
}

.average-value, .average-percentile {
  color: #409eff;
}

.below-value, .below-percentile {
  color: #909399;
}

.chart-section, .analysis-section {
  margin-bottom: 20px;
}

.chart-container {
  height: 300px;
}

.layer-chart {
  height: 350px;
}

.ability-analysis {
  padding: 10px;
}

.ability-item {
  margin-bottom: 20px;
}

.ability-label {
  display: block;
  margin-bottom: 10px;
  font-size: 14px;
  font-weight: bold;
}

.teaching-features {
  margin-bottom: 20px;
}

.feature-tag {
  margin-right: 10px;
  margin-bottom: 10px;
  padding: 8px 12px;
}

.teaching-summary {
  padding: 0 10px;
}

.teaching-summary h4 {
  margin-top: 15px;
  margin-bottom: 10px;
  font-size: 16px;
  color: #303133;
}

.teaching-summary p {
  line-height: 1.6;
  color: #606266;
  text-align: justify;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.pagination-container {
  margin-top: 15px;
  text-align: right;
}

/* 添加按钮区域样式 */
.filter-buttons {
  margin-top: 20px;
  display: flex;
  justify-content: center;
  gap: 20px;
}

/* 从CommonFilterSelector添加的样式 */
.common-filter-selector {
  background-color: #f5f7fa;
  padding: 20px;
  border-radius: 4px;
  margin-bottom: 20px;
}

.form-hint {
  font-size: 12px;
  color: #909399;
  margin-top: 5px;
}

.overview-card {
  margin-bottom: 20px;
}

.metric-box {
  text-align: center;
}

.metric-label {
  font-size: 14px;
  color: #909399;
  margin-bottom: 5px;
}

.metric-value {
  font-size: 20px;
  font-weight: bold;
}

.layer-analysis-card {
  margin-bottom: 20px;
}

.ability-radar-card {
  margin-bottom: 20px;
}

.recommendation-card {
  margin-top: 20px;
}

.recommendation-content {
  padding: 10px;
}

.advice-section {
  margin-bottom: 20px;
}

.advice-section h4 {
  color: #409EFF;
  border-bottom: 1px solid #eee;
  padding-bottom: 8px;
  margin-bottom: 10px;
}

.advice-section ul {
  padding-left: 20px;
}

.advice-section li {
  margin-bottom: 8px;
  line-height: 1.6;
}

.hierarchy-select-card {
  margin-bottom: 20px;
}

.class-list {
  display: flex;
  flex-wrap: wrap;
  gap: 15px;
  margin-top: 10px;
}

.class-card {
  width: 220px;
  cursor: pointer;
  transition: all 0.3s;
}

.class-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.class-info {
  display: flex;
  flex-direction: column;
}

.class-name {
  font-size: 16px;
  font-weight: bold;
  margin-bottom: 10px;
  color: #409EFF;
}

.class-metrics {
  display: flex;
  justify-content: space-between;
}

.metric {
  text-align: center;
}

.metric-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 5px;
}

.metric-value {
  font-size: 16px;
  font-weight: 500;
}

.metric-value.highlight {
  color: #409EFF;
  font-weight: bold;
}

.back-button-container {
  margin-bottom: 15px;
}

.teacher-detail-container {
  margin-top: 20px;
}

/* 在页面底部添加 */
.debug-panel {
  margin-top: 20px;
  text-align: right;
}
</style>