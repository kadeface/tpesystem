import axios from 'axios';

const api = axios.create({
  baseURL: '/api/v1/',
  timeout: 10000,
});

// 判断是否使用模拟数据
const useMockData = false; // 改为false，使用真实API数据

// 模拟数据
const mockData = {
  regions: [
    { region_id: 'kaipingshi', region_name: '开平市' },
    { region_id: 'enping', region_name: '恩平市' },
    { region_id: 'taishan', region_name: '台山市' },
    { region_id: 'heshan', region_name: '鹤山市' },
    { region_id: 'xinhui', region_name: '新会区' },
    { region_id: 'jianghai', region_name: '江海区' },
    { region_id: 'pengjiang', region_name: '蓬江区' },
    { region_id: 'jiangmen', region_name: '市直' },
  ],
  grades: [
    { grade_id: '1', grade_name: '一年级', grade_level: '1' },
    { grade_id: '2', grade_name: '二年级', grade_level: '2' },
    { grade_id: '3', grade_name: '三年级', grade_level: '3' },
    { grade_id: '4', grade_name: '四年级', grade_level: '4' },
    { grade_id: '5', grade_name: '五年级', grade_level: '5' },
    { grade_id: '6', grade_name: '六年级', grade_level: '6' },
    { grade_id: '7', grade_name: '七年级', grade_level: '7' },
    { grade_id: '8', grade_name: '八年级', grade_level: '8' },
    { grade_id: '9', grade_name: '九年级', grade_level: '9' },
    { grade_id: '10', grade_name: '高一', grade_level: '10' },
    { grade_id: '11', grade_name: '高二', grade_level: '11' },
    { grade_id: '12', grade_name: '高三', grade_level: '12' }
  ],
  subjects: [
    { subject_id: 'MATH', subject_name: '数学', subject_type: 'REQUIRED' },
    { subject_id: 'CHINESE', subject_name: '语文', subject_type: 'REQUIRED' },
    { subject_id: 'ENGLISH', subject_name: '英语', subject_type: 'REQUIRED' },
    { subject_id: 'PHYSICS', subject_name: '物理', subject_type: 'REQUIRED' },
    { subject_id: 'CHEMISTRY', subject_name: '化学', subject_type: 'REQUIRED' },
    { subject_id: 'BIOLOGY', subject_name: '生物', subject_type: 'ELECTIVE' },
    { subject_id: 'HISTORY', subject_name: '历史', subject_type: 'ELECTIVE' },
    { subject_id: 'GEOGRAPHY', subject_name: '地理', subject_type: 'ELECTIVE' },
    { subject_id: 'POLITICS', subject_name: '政治', subject_type: 'ELECTIVE' }
  ],
  exams: [
    { exam_id: '2025-DIST-M-202301', exam_name: '初中2023年1月区统考', grade: { grade_level: '7' } },
    { exam_id: '2025-DIST-M-202307', exam_name: '初中2023年7月区统考', grade: { grade_level: '7' } },
    { exam_id: '2025-DIST-M-202401', exam_name: '初中2024年1月区统考', grade: { grade_level: '8' } },
    { exam_id: '2025-DIST-M-202407', exam_name: '初中2024年7月区统考', grade: { grade_level: '8' } },
    { exam_id: '2025-DIST-M-202501', exam_name: '初中2025年1月区统考', grade: { grade_level: '9' } },
    { exam_id: '2025-JUNIOR-M-202301', exam_name: '2023年1月初中统考', grade: { grade_level: '7' } },
    { exam_id: '2025-JUNIOR-M-202307', exam_name: '2023年7月初中统考', grade: { grade_level: '7' } },
    { exam_id: '2025-JUNIOR-M-202401', exam_name: '2024年1月初中统考', grade: { grade_level: '8' } }
  ]
};

/**
 * 教育数据API服务
 * 
 * 提供获取区域、学段、年级、学科和考试数据的方法
 * 支持在后端API尚未实现时使用模拟数据
 */
export default {
  /**
   * 获取区域列表
   * 
   * @param {Object} params - 查询参数
   * @param {CancelToken} cancelToken - 取消令牌（可选）
   * @returns {Promise} 返回区域数据列表
   */
  getRegions(params = {}) {
    if (useMockData) {
      console.log('使用模拟区域数据');
      return Promise.resolve({ data: mockData.regions });
    }
    
    // 添加额外的错误处理
    return api.get('regions/', { params })
      .then(response => {
        // 处理DRF分页响应
        if (response.data && response.data.results) {
          return {data: response.data.results};
        }
        return {data: response.data || []};
      })
      .catch(error => {
        console.error('区域API请求失败:', error);
        // 返回空数据而不是抛出错误
        return {data: []};
      });
  },

  /**
   * 获取学段列表
   * 
   * @returns {Promise} 返回学段数据列表
   */
  getEducationStages() {
    // 学段是固定的枚举值，可以直接返回
    return Promise.resolve({
      data: [
        { value: 'elementary', label: '小学' },
        { value: 'junior', label: '初中' },
        { value: 'senior', label: '高中' }
      ]
    });
  },

  /**
   * 获取包含毕业年份信息的年级列表
   * 
   * @param {Object} params - 查询参数
   * @returns {Promise} 返回带毕业年份信息的年级数据
   */
  getGradesWithGraduationInfo(params = {}) {
    if (useMockData) {
      console.log('使用模拟年级数据');
      // 处理模拟数据...
      
      let grades = [...mockData.grades];
      
      // 根据当前日期添加毕业年份信息
      const now = new Date();
      const currentYear = now.getFullYear();
      const currentMonth = now.getMonth() + 1; // 月份从0开始
      const academicYear = currentMonth >= 9 ? currentYear : currentYear - 1;
      
      grades = grades.map(grade => {
        const gradeLevel = parseInt(grade.grade_level);
        let yearsToGraduation, educationStage, stageDisplay;
        
        if (gradeLevel <= 6) {
          yearsToGraduation = 6 - gradeLevel;
          educationStage = 'elementary';
          stageDisplay = '小学';
        } else if (gradeLevel <= 9) {
          yearsToGraduation = 9 - gradeLevel;
          educationStage = 'junior';
          stageDisplay = '初中';
        } else {
          yearsToGraduation = 12 - gradeLevel;
          educationStage = 'senior';
          stageDisplay = '高中';
        }
        
        const graduationYear = academicYear + yearsToGraduation;
        
        return {
          ...grade,
          graduation_year: graduationYear,
          education_stage: educationStage,
          stage_display: stageDisplay,
          graduation_info: `${graduationYear}届${stageDisplay}`
        };
      });
      
      // 过滤学段
      if (params.stage) {
        if (params.stage === 'elementary') {
          grades = grades.filter(g => g.education_stage === 'elementary');
        } else if (params.stage === 'junior') {
          grades = grades.filter(g => g.education_stage === 'junior');
        } else if (params.stage === 'senior') {
          grades = grades.filter(g => g.education_stage === 'senior');
        }
      }
      
      return Promise.resolve({ data: grades });
    }
    
    return api.get('grades/with_graduation_info/', { params });
  },

  /**
   * 获取学科列表
   *
   * @param {Object} params - 查询参数，包括grade_id或grade_level
   * @returns {Promise} 返回学科数据列表
   */
  async getSubjects(params = {}) {
    console.log('获取学科数据，参数:', params);
    
    try {
      // 默认使用模拟数据
      const useMockSubjects = true;
      
      if (useMockSubjects) {
        console.log('使用模拟学科数据');
        
        // 根据年级提供不同的学科列表
        let gradeLevel = null;
        
        // 尝试从参数中获取年级信息
        if (params.grade_id) {
          // 从grade_id中提取年级数字
          try {
            const gradeParts = params.grade_id.split('_');
            if (gradeParts.length > 1) {
              gradeLevel = parseInt(gradeParts[1]);
            }
          } catch (e) {
            console.warn('解析grade_id出错:', e);
          }
        } else if (params.grade_level) {
          // 直接使用grade_level
          gradeLevel = parseInt(params.grade_level);
        }
        
        console.log(`确定年级等级: ${gradeLevel}`);
        
        // 定义不同年级的学科列表
        let mockSubjects = [];
        
        // 小学科目 (1-6年级)
        if (gradeLevel >= 1 && gradeLevel <= 6) {
          mockSubjects = [
            { subject_id: 'CHN', subject_name: '语文' },
            { subject_id: 'MATH', subject_name: '数学' },
            { subject_id: 'ENG', subject_name: '英语' },
            { subject_id: 'SCI', subject_name: '科学' },
            { subject_id: 'MOR_P', subject_name: '品德与生活' },
            { subject_id: 'TOTAL', subject_name: '总分' }
          ];
        }
        // 初中7年级科目
        else if (gradeLevel === 7) {
          mockSubjects = [
            { subject_id: 'CHN', subject_name: '语文' },
            { subject_id: 'MATH', subject_name: '数学' },
            { subject_id: 'ENG', subject_name: '英语' },
            { subject_id: 'POL', subject_name: '政治' },
            { subject_id: 'HIS', subject_name: '历史' },
            { subject_id: 'GEO', subject_name: '地理' },
            { subject_id: 'BIO', subject_name: '生物' },
            { subject_id: 'TOTAL', subject_name: '总分' }
          ];
        }
        // 初中8年级科目
        else if (gradeLevel === 8) {
          mockSubjects = [
            { subject_id: 'CHN', subject_name: '语文' },
            { subject_id: 'MATH', subject_name: '数学' },
            { subject_id: 'ENG', subject_name: '英语' },
            { subject_id: 'POL', subject_name: '政治' },
            { subject_id: 'HIS', subject_name: '历史' },
            { subject_id: 'GEO', subject_name: '地理' },
            { subject_id: 'BIO', subject_name: '生物' },
            { subject_id: 'PHY', subject_name: '物理' },
            { subject_id: 'TOTAL', subject_name: '总分' }
          ];
        }
        // 初中9年级科目
        else if (gradeLevel === 9) {
          mockSubjects = [
            { subject_id: 'CHN', subject_name: '语文' },
            { subject_id: 'MATH', subject_name: '数学' },
            { subject_id: 'ENG', subject_name: '英语' },
            { subject_id: 'POL', subject_name: '政治' },
            { subject_id: 'HIS', subject_name: '历史' },
            { subject_id: 'PHY', subject_name: '物理' },
            { subject_id: 'CHEM', subject_name: '化学' },
            { subject_id: 'TOTAL', subject_name: '总分' }
          ];
        }
        // 高中科目 (10-12年级)
        else if (gradeLevel >= 10 && gradeLevel <= 12) {
          mockSubjects = [
            { subject_id: 'CHN', subject_name: '语文' },
            { subject_id: 'MATH', subject_name: '数学' },
            { subject_id: 'MATH_L', subject_name: '数学(文科)' },
            { subject_id: 'MATH_S', subject_name: '数学(理科)' },
            { subject_id: 'ENG', subject_name: '英语' },
            { subject_id: 'PHY', subject_name: '物理' },
            { subject_id: 'PHY_E', subject_name: '物理(选修)' },
            { subject_id: 'CHEM', subject_name: '化学' },
            { subject_id: 'CHEM_E', subject_name: '化学(选修)' },
            { subject_id: 'BIO', subject_name: '生物' },
            { subject_id: 'BIO_E', subject_name: '生物(选修)' },
            { subject_id: 'POL', subject_name: '政治' },
            { subject_id: 'HIS', subject_name: '历史' },
            { subject_id: 'HIS_E', subject_name: '历史(选修)' },
            { subject_id: 'GEO', subject_name: '地理' },
            { subject_id: 'GEO_E', subject_name: '地理(选修)' },
            { subject_id: 'TECH', subject_name: '通用技术' },
            { subject_id: 'TOTAL', subject_name: '总分' }
          ];
        }
        // 未指定年级或无效年级，返回通用学科列表
        else {
          mockSubjects = [
            { subject_id: 'CHN', subject_name: '语文' },
            { subject_id: 'MATH', subject_name: '数学' },
            { subject_id: 'ENG', subject_name: '英语' },
            { subject_id: 'PHY', subject_name: '物理' },
            { subject_id: 'CHEM', subject_name: '化学' },
            { subject_id: 'TOTAL', subject_name: '总分' }
          ];
        }
        
        console.log(`返回${mockSubjects.length}个学科`);
        return { data: mockSubjects };
      }
      
      // 正常API调用
      const response = await api.get('subjects/', { params });
      console.log('学科API响应:', response);
      
      // 处理响应数据格式
      let subjectData = [];
      
      if (response.data && Array.isArray(response.data)) {
        // 直接是数组格式
        subjectData = response.data;
      } else if (response.data && response.data.results && Array.isArray(response.data.results)) {
        // 分页格式
        subjectData = response.data.results;
      } else {
        console.warn('意外的学科API响应格式:', response.data);
        subjectData = [];
      }
      
      return { data: subjectData };
    } catch (error) {
      console.error('获取学科数据出错:', error);
      return { data: [] }; // 返回空数组而非null
    }
  },

  /**
   * 获取考试列表
   *
   * @param {Object} params - 查询参数
   * @returns {Promise} 返回考试数据列表
   */
  async getExams(params = {}) {
    console.log('调用getExams API，参数:', params);
    localStorage.setItem('lastExamParams', JSON.stringify(params));
    
    // 添加时间戳避免缓存
    params._nocache = Date.now();
    
    // 检查是否需要使用模拟数据
    if (useMockData) {
      console.log('使用模拟考试数据');
      return Promise.resolve({ data: mockData.exams });
    }
    
    try {
      const response = await api.get('exams/', { params });
      
      console.log('Exam API原始响应:', response);
      
      // 确保返回的数据始终是数组格式
      let examData = [];
      
      if (response.data) {
        // 处理不同格式的响应
        if (Array.isArray(response.data)) {
          examData = response.data;
        } else if (response.data.results && Array.isArray(response.data.results)) {
          // Django REST Framework 分页格式
          examData = response.data.results;
        } else {
          // 如果是其他格式，记录并返回空数组
          console.warn('意外的考试API响应格式:', response.data);
        }
      }
      
      // 过滤掉无效数据
      examData = examData.filter(item => item != null);
      
      console.log(`处理后的考试数据: ${examData.length}个有效考试`);
      localStorage.setItem('lastExamResponse', JSON.stringify(examData));
      
      return { data: examData };
    } catch (error) {
      console.error('Exam API请求失败:', error);
      // 出错时返回空数组而不是抛出错误
      return { data: [] };
    }
  },

  /**
   * 获取学校列表
   *
   * @param {Object} params - 查询参数
   * @returns {Promise} 返回学校数据列表
   */
  getSchools(params = {}) {
    if (useMockData) {
      console.log('使用模拟学校数据');
      return Promise.resolve({ data: [] }); // 暂无模拟学校数据
    }
    return api.get('schools/', { params });
  },

  // 添加getGrades作为getGradesWithGraduationInfo的别名
  getGrades(params = {}) {
    console.log('getGrades被调用，这是getGradesWithGraduationInfo的别名');
    return this.getGradesWithGraduationInfo(params);
  },

  // 创建分析任务 - 使用v1外部的路径
  createAnalysisTask(params) {
    console.log('调用创建分析任务API, 参数:', params);
    
    // 使用axios直接请求，绕过api实例的baseURL设置
    return axios.post('/api/edu-insights/tasks/', params);
  },

  // 获取任务状态
  getTaskStatus(taskId) {
    return axios.get(`/api/edu-insights/tasks/${taskId}/status/`);
  },

  // 获取任务结果
  getTaskResults(taskId) {
    return axios.get(`/api/edu-insights/tasks/${taskId}/results/`);
  },

  /**
   * 获取分析任务的原始数据
   * 
   * @param {string} taskId 任务ID
   * @param {string} dataType 数据类型（clusters, features等）
   * @returns {Promise} 请求Promise
   */
  getTaskData(taskId, dataType) {
    return axios.get(`/api/edu-insights/tasks/${taskId}/data/${dataType}/`);
  },

  /**
   * 获取学生考试成绩
   * 
   * Args:
   *   studentId: 学生ID
   *   params: 查询参数，包括考试ID和学科ID
   * 
   * Returns:
   *   Promise: 成绩数据Promise
   */
  async getStudentScores(studentId, params = {}) {
    if (useMockData) {
      console.log('使用模拟学生成绩数据');
      return Promise.resolve({ data: [] });
    }
    
    try {
      console.log(`尝试获取学生${studentId}的考试成绩，参数:`, params);
      const response = await axios.get(`/api/edu-insights/students/${studentId}/scores/`, { params });
      console.log(`成功获取学生${studentId}的成绩数据:`, response.data);
      return response;
    } catch (error) {
      // 详细记录错误信息
      console.warn(`获取学生成绩数据失败: ${error.message}`);
      if (error.response) {
        console.error('服务器响应:', error.response.status, error.response.data);
      }
      return { data: [] };
    }
  },

  /**
   * 获取教师增值数据
   * 
   * 根据筛选条件获取教师增值分析数据
   * 
   * Args:
   *   filters: 筛选条件对象
   * 
   * Returns:
   *   Promise: 返回教师增值数据的Promise
   */
  getTeacherValueAddedData(filters) {
    console.log('调用教师增值分析API，参数:', filters)
    
    if (useMockData) {
      console.log('使用模拟教师增值数据')
      
      // 模拟API响应数据
      const mockResponse = {
        overview: {
          regionAvg: 78.5,
          schoolAvg: 82.6,
          subjectAvg: 79.8
        },
        teacherRanking: [
          { teacherId: 'T001', teacherName: '张老师', school: '实验中学', subject: '数学', rank: 1, valueAdded: 93.5, percentile: 95 },
          { teacherId: 'T002', teacherName: '李老师', school: '第一中学', subject: '数学', rank: 2, valueAdded: 87.2, percentile: 85 },
          { teacherId: 'T003', teacherName: '王老师', school: '实验中学', subject: '数学', rank: 3, valueAdded: 82.9, percentile: 75 },
          { teacherId: 'T004', teacherName: '赵老师', school: '第二中学', subject: '数学', rank: 4, valueAdded: 78.4, percentile: 65 },
          { teacherId: 'T005', teacherName: '刘老师', school: '第三中学', subject: '数学', rank: 5, valueAdded: 73.8, percentile: 55 }
        ],
        schoolRanking: [
          { schoolName: '实验中学', valueAdded: 87.2 },
          { schoolName: '第一中学', valueAdded: 82.5 },
          { schoolName: '第二中学', valueAdded: 78.4 },
          { schoolName: '第三中学', valueAdded: 75.8 },
          { schoolName: '第四中学', valueAdded: 72.3 }
        ],
        teacherTrend: {
          teachers: ['张老师', '李老师', '王老师'],
          timePoints: ['考试1', '考试2', '考试3', '考试4'],
          series: [
            {
              name: '张老师',
              type: 'line',
              data: [78, 82, 88, 93]
            },
            {
              name: '李老师',
              type: 'line',
              data: [75, 78, 83, 87]
            },
            {
              name: '王老师',
              type: 'line',
              data: [70, 76, 80, 83]
            }
          ]
        },
        total: 5
      }
      
      return Promise.resolve({ data: mockResponse })
    }
    
    return axios.get('/api/edu-insights/teacher-value-added/', {
      params: {
        region: filters.region,
        subject: filters.subject,
        grade: filters.grade,
        target_exam: filters.targetExam,     // 新参数：目标考试
        baseline_exam: filters.baselineExam, // 新参数：基准考试
        page: filters.page || 1,
        page_size: filters.pageSize || 10
      }
    })
  },

  getTeacherValueAdded(params) {
    return axios.get('/api/teacher-value-added/', { params });
  }
}; 