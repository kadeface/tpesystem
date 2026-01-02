import axios from 'axios';

/**
 * 特征分析API服务
 * 
 * 提供获取各层级特征数据的方法
 */
const featureAnalysisApi = {
  /**
   * 获取可分析的考试列表
   * 
   * Args:
   *   params: 查询参数，如年级、学科等
   * 
   * Returns:
   *   Promise: 考试列表数据
   */
  getAnalyzableExams(params = {}) {
    return axios.get('/api/edu-insights/analyzable-exams/', { params });
  },
  
  /**
   * 获取区级特征数据
   * 
   * Args:
   *   examId: 考试ID
   * 
   * Returns:
   *   Promise: 区级特征数据
   */
  getDistrictFeature(examId) {
    return axios.get(`/api/edu-insights/exams/${examId}/district-feature/`);
  },
  
  /**
   * 获取学校特征数据
   * 
   * Args:
   *   examId: 考试ID
   *   params: 查询参数，如排序方式、筛选条件
   * 
   * Returns:
   *   Promise: 学校特征数据列表
   */
  getSchoolFeatures(examId, params = {}) {
    return axios.get(`/api/edu-insights/exams/${examId}/school-features/`, { params });
  },
  
  /**
   * 获取班级特征数据
   * 
   * Args:
   *   examId: 考试ID
   *   schoolId: 学校ID (可选)
   *   params: 查询参数
   * 
   * Returns:
   *   Promise: 班级特征数据列表
   */
  getClassFeatures(examId, schoolId = null, params = {}) {
    const queryParams = { ...params };
    if (schoolId) {
      queryParams.school_id = schoolId;
    }
    return axios.get(`/api/edu-insights/exams/${examId}/class-features/`, { params: queryParams });
  },
  
  /**
   * 获取学生特征数据
   * 
   * Args:
   *   examId: 考试ID
   *   classId: 班级ID (可选)
   *   params: 查询参数
   * 
   * Returns:
   *   Promise: 学生特征数据列表
   */
  getStudentFeatures(examId, classId = null, params = {}) {
    const queryParams = { ...params };
    if (classId) {
      queryParams.class_id = classId;
    }
    return axios.get(`/api/edu-insights/exams/${examId}/student-features/`, { params: queryParams });
  },
  
  /**
   * 获取考试科目列表
   * 
   * Args:
   *   examId: 考试ID
   * 
   * Returns:
   *   Promise: 考试科目列表
   */
  getExamSubjects(examId) {
    return axios.get(`/api/edu-insights/exams/${examId}/subjects/`);
  },
  
  /**
   * 获取考试详细信息
   * 
   * Args:
   *   examId: 考试ID
   * 
   * Returns:
   *   Promise: 考试详细信息
   */
  getExamInfo(examId) {
    return axios.get(`/api/edu-insights/exams/${examId}/info/`);
  }
};

export default featureAnalysisApi; 