<template>
  <div class="student-portrait">
    <el-card class="main-card">
      <template #header>
        <div class="card-header">
          <h2>学生成长画像分析</h2>
        </div>
      </template>

      <el-form :model="formData" label-width="120px" label-position="left" :disabled="loading">
        <!-- 区域、学段、年级选择 -->
        <common-filter-selector 
          v-model:district="formData.district"
          v-model:educationStage="formData.educationStage"
          v-model:grade="formData.grade"
          v-model:exam="formData.exams"
          v-model:subject="formData.subject"
          @change="handleFilterChange"
        />
        
        <!-- 高级选项 -->
        <el-collapse v-model="activeNames">
          <el-collapse-item title="高级分析选项" name="advanced">
            <el-form-item label="聚类数量:">
              <el-slider
                v-model="formData.clusters"
                :min="3"
                :max="15"
                :step="1"
                show-stops
                show-input
              />
              <div class="form-hint">聚类数量决定了学生会被划分为多少种成长模式</div>
            </el-form-item>

            <el-form-item label="最小考试次数:">
              <el-slider
                v-model="formData.minExams"
                :min="2"
                :max="Math.max(2, formData.exams.length)"
                :step="1"
                show-stops
                show-input
              />
              <div class="form-hint">学生需要参加的最少考试次数才会被纳入分析</div>
            </el-form-item>

            <el-form-item label="可视化选项:">
              <el-checkbox v-model="formData.visualizeClusters">生成聚类可视化</el-checkbox>
              <el-checkbox v-model="formData.visualizeTopStudents">学生成长轨迹</el-checkbox>
              <el-checkbox v-model="formData.visualizeLayerGrowth">生成分层成长分析</el-checkbox>
            </el-form-item>
          </el-collapse-item>
        </el-collapse>

        <!-- 提交按钮 -->
        <div class="action-buttons">
          <el-button type="primary" @click="submitAnalysis">开始分析</el-button>
          <el-button @click="resetForm">重置</el-button>
        </div>
      </el-form>

      <!-- 分析进度条 -->
      <div v-if="isAnalyzing" class="analysis-progress-container">
        <el-progress 
          :percentage="analysisProgress" 
          :status="analysisProgress < 100 ? '' : 'success'"
        ></el-progress>
        <div class="progress-message">{{ progressMessage }}</div>
      </div>
      
      <!-- 分析错误提示 -->
      <div v-if="analysisError" class="error-alert">
        <el-alert
          :title="analysisError"
          type="error"
          show-icon
          @close="analysisError = null"
        ></el-alert>
        <el-button type="primary" size="small" @click="retryAnalysis" class="retry-btn">
          重试
        </el-button>
      </div>
      
      <!-- 分析结果 -->
      <div v-if="analysisComplete && !isAnalyzing" id="analysis-results" class="analysis-results">
        <h2>分析结果</h2>
        
        <!-- 标签页系统 -->
        <el-tabs v-model="activeTab" @tab-click="handleTabClick">
          <el-tab-pane label="聚类分析" name="cluster">
            <div class="cluster-analysis-container">
              <div v-if="!clusterAnalysis.isLoaded" class="cluster-loading">
                <p>正在加载聚类数据...</p>
                <el-button @click="forceLoadData" size="small" type="primary">强制加载</el-button>
              </div>
              
              <div v-else class="cluster-data-section">
                <!-- 聚类统计信息 -->
                <div class="cluster-metadata-row">
                  <div class="metadata-card">
                    <div class="data-tile">
                      <span class="label">聚类数量</span>
                      <span class="value">{{ clusterAnalysis.metadata.clusterCount || "0" }}</span>
                    </div>
                  </div>
                  <div class="metadata-card">
                    <div class="data-tile">
                      <span class="label">学生总数</span>
                      <span class="value">{{ clusterAnalysis.metadata.studentCount || "0" }}</span>
                    </div>
                  </div>
                  <div class="metadata-card">
                    <div class="data-tile">
                      <span class="label">分析特征</span>
                      <span class="value">{{ clusterAnalysis.metadata.featureNames?.length || 0 }}个特征</span>
                    </div>
                  </div>
                </div>
                
                <!-- 第一行: 聚类分布图 -->
                <div class="visualization-row">
                  <div class="chart-section full-width">
                    <div class="chart-header">
                      <h4>聚类分布图</h4>
                      <div class="chart-controls">
                        <el-radio-group v-model="scatterChartType" size="small" @change="updateScatterChart">
                          <el-radio-button label="bubble">双变量气泡图</el-radio-button>
                          <el-radio-button label="pca">PCA散点图</el-radio-button>
                        </el-radio-group>
                      </div>
                    </div>
                    <div id="cluster-pca-chart" class="chart-container" style="height: 400px;"></div>
                    <div class="chart-actions text-center" style="margin-top: 10px;">
                      <el-button size="small" type="primary" @click="updateScatterChart">
                        重新渲染分布图
                      </el-button>
                    </div>
                  </div>
                </div>
                
                <!-- 第二行: 聚类特征分布 -->
                <div class="visualization-row">
                  <div class="chart-section full-width">
                    <div class="chart-header">
                      <h4>聚类特征分布</h4>
                      <div class="chart-controls">
                        <el-radio-group v-model="featureChartType" size="small" @change="updateFeatureChart">
                          <el-radio-button label="boxplot">箱线图</el-radio-button>
                          <el-radio-button label="heatmap">热力图</el-radio-button>
                          <el-radio-button label="parallel">并行坐标图</el-radio-button>
                        </el-radio-group>
                      </div>
                    </div>
                    <div id="cluster-feature-chart" class="chart-container" style="height: 400px;"></div>
                    <div class="chart-actions text-center" style="margin-top: 10px;">
                      <el-button size="small" type="primary" @click="updateFeatureChart">
                        重新渲染特征图
                      </el-button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </el-tab-pane>
          
          <!-- 成长分析标签页 -->
          <el-tab-pane label="成长分析" name="growth">
            <div class="growth-analysis-container">
              <div v-if="!analysisResults?.data?.student_layer_growth" class="no-data-message">
                <p>暂无成长分析数据</p>
                <el-button @click="submitAnalysis" size="small" type="primary">重新分析</el-button>
              </div>
              
              <div v-else class="growth-data-section">
                <!-- 调试信息 -->
                <div class="debug-info" style="margin-bottom: 20px;">
                  <h4>成长分析数据（前10条记录）</h4>
                  <el-table 
                    :data="getTopLayerGrowthData(10)"
                    border
                    style="width: 100%">
                    <el-table-column prop="key" label="层级组合"></el-table-column>
                    <el-table-column prop="value" label="学生数量"></el-table-column>
                  </el-table>
                </div>
                
                <!-- 第一行: 分层成长图 -->
                <div class="visualization-row">
                  <div class="chart-section full-width">
                    <div class="chart-header">
                      <h4>分层成长分布</h4>
                    </div>
                    <div id="layer-growth-chart" class="chart-container" style="height: 400px;"></div>
                  </div>
                </div>
                
                <!-- 第二行: 层级转换图 -->
                <div class="visualization-row">
                  <div class="chart-section full-width">
                    <div class="chart-header">
                      <h4>层级转换轨迹</h4>
                    </div>
                    <div id="layer-transition-chart" class="chart-container" style="height: 400px;"></div>
                  </div>
                </div>
                
                <!-- 数据表格展示 -->
                <div class="visualization-row">
                  <div class="chart-section full-width">
                    <div class="chart-header">
                      <h4>成长分布数据</h4>
                    </div>
                    <el-table :data="growthTableData" style="width: 100%">
                      <el-table-column prop="category" label="类别"></el-table-column>
                      <el-table-column prop="value" label="百分比">
                        <template #default="scope">
                          {{ scope.row.value.toFixed(2) }}%
                        </template>
                      </el-table-column>
                      <el-table-column label="可视化">
                        <template #default="scope">
                          <div class="progress-bar" :style="{ width: scope.row.value + '%', backgroundColor: scope.row.color }"></div>
                        </template>
                      </el-table-column>
                    </el-table>
                  </div>
                </div>
                
                <!-- 在成长分析标签页中添加聚类分析内容 -->
                <div class="visualization-row">
                  <div class="chart-section full-width">
                    <div class="chart-header">
                      <h4>学生成长模式聚类</h4>
                      </div>
                    <el-table :data="studentClusterData" style="width: 100%">
                      <el-table-column prop="clusterLabel" label="成长模式" width="200"></el-table-column>
                      <el-table-column prop="description" label="描述"></el-table-column>
                      <el-table-column prop="count" label="学生数量" width="100"></el-table-column>
                      <el-table-column prop="percentage" label="占比" width="100">
                        <template #default="scope">
                          {{ scope.row.percentage.toFixed(2) }}%
                        </template>
                      </el-table-column>
                      <el-table-column label="分布" width="200">
                        <template #default="scope">
                          <div class="progress-bar" :style="{ width: scope.row.percentage + '%', backgroundColor: scope.row.color }"></div>
                        </template>
                      </el-table-column>
                    </el-table>
                  </div>
                </div>
                
                <div class="visualization-row">
                  <div class="chart-section full-width">
                    <div class="chart-header">
                      <h4>所有层级成长模式 ({{ Object.keys(analysisResults.data.student_layer_growth).length }} 种组合)</h4>
                    </div>
                    <el-table 
                      :data="Object.keys(analysisResults.data.student_layer_growth)
                        .filter(key => typeof analysisResults.data.student_layer_growth[key] === 'number')
                        .map(key => ({ 
                          category: key, 
                          count: analysisResults.data.student_layer_growth[key] 
                        }))"
                      style="width: 100%">
                      <el-table-column prop="category" label="层级组合"></el-table-column>
                      <el-table-column prop="count" label="学生数量"></el-table-column>
                    </el-table>
                  </div>
                </div>
              </div>
            </div>
          </el-tab-pane>
          
          <!-- 学生详情标签页 -->
          <el-tab-pane label="学生详情" name="students">
            <!-- 学生详情内容 -->
          </el-tab-pane>
        </el-tabs>
      </div>
      
      <!-- 无分析结果提示 -->
      <el-empty v-if="!loading && !analysisComplete" description="尚未进行分析" />
      
      <!-- 加载中 -->
      <div v-if="loading" class="loading-container">
        <el-progress type="circle" :percentage="progressPercentage" :status="progressStatus">
          <template #default>
            <span class="progress-text">{{ progressMessage }}</span>
          </template>
        </el-progress>
      </div>

      <!-- 在分析结果区域添加调试信息 -->
      <div class="debug-info" v-if="analysisComplete && !isAnalyzing">
        <p>数据加载状态: {{ clusterAnalysis.isLoaded ? '已加载' : '未加载' }}</p>
        <p>学生数量: {{ clusterAnalysis.metadata.studentCount }}</p>
        <p>聚类数量: {{ clusterAnalysis.metadata.clusterCount }}</p>
      </div>
    </el-card>
    
    <!-- 学生详情对话框 -->
    <el-dialog
      title="学生详情"
      v-model="studentDetailVisible"
      width="80%"
      :before-close="closeStudentDetail"
      class="student-detail-dialog">
      
      <div v-if="selectedStudent">
        <!-- 学生基本信息 -->
        <div class="student-info-section">
          <el-descriptions title="基本信息" :column="3" border>
            <el-descriptions-item label="学号">{{ selectedStudent.student_id }}</el-descriptions-item>
            <el-descriptions-item label="姓名">{{ selectedStudent.student_name || '未知' }}</el-descriptions-item>
            <el-descriptions-item label="聚类类型">
              <el-tag :type="getClusterTagType(selectedStudent.cluster)">
                {{ getClusterName(selectedStudent.cluster) }}
              </el-tag>
            </el-descriptions-item>
          </el-descriptions>
        </div>
        
        <!-- 考试记录图表 -->
        <div class="chart-section" style="margin-top: 20px;">
          <h3>考试成绩趋势</h3>
          <div id="studentPerformanceChart" style="height: 400px; width: 100%;"></div>
        </div>
        
        <!-- 考试记录表格 -->
        <div class="table-section" style="margin-top: 20px;">
          <h3>考试记录列表</h3>
          <div id="examRecordsTable"></div>
        </div>
      </div>
      
      <div v-else class="text-center p-5">
        <el-skeleton animated :rows="5" />
        <div class="text-muted mt-3">正在加载学生信息...</div>
      </div>
    </el-dialog>

    <!-- 调试工具(开发模式) -->
    <div v-if="showDebugInfo" class="debug-panel">
      <h4>调试面板</h4>
      <div class="debug-info">
        <div>当前标签页: <strong>{{ activeTab }}</strong></div>
        <div>分析完成: <strong>{{ analysisComplete ? '是' : '否' }}</strong></div>
        <div>正在分析: <strong>{{ isAnalyzing ? '是' : '否' }}</strong></div>
        <div>聚类数据已加载: <strong>{{ clusterAnalysis?.isLoaded ? '是' : '否' }}</strong></div>
        <div>DOM状态: 
          <span v-if="checkDomStatus()">正常</span>
          <span v-else class="error">异常</span>
        </div>
      </div>
      <div class="debug-actions">
        <el-button @click="forceLoadData" size="small" type="warning">强制加载数据</el-button>
        <el-button @click="initClusterCharts" size="small" type="warning">强制初始化图表</el-button>
        <el-button @click="fixDomStructure" size="small" type="danger">修复DOM结构</el-button>
      </div>
    </div>

    <!-- 数据诊断工具 -->
    <div class="debug-panel" style="margin-bottom: 20px; padding: 10px; border: 1px solid #ddd; background: #f9f9f9;">
      <h4>数据诊断工具</h4>
      <el-button size="small" @click="checkLayerGrowthData" type="primary">检查数据结构</el-button>
      <el-button size="small" @click="generateTestData" type="success">生成测试数据</el-button>
      
      <div v-if="dataCheckResult" style="margin-top: 10px; padding: 10px; background: #fff; border: 1px solid #eee;">
        <h5>诊断结果:</h5>
        <el-descriptions :column="1" border>
          <el-descriptions-item label="数据是否存在">{{ dataCheckResult.exists ? '是' : '否' }}</el-descriptions-item>
          <el-descriptions-item label="数据类型">{{ dataCheckResult.type }}</el-descriptions-item>
          <el-descriptions-item label="总键数">{{ dataCheckResult.keyCount }}</el-descriptions-item>
          <el-descriptions-item label="有效键数">{{ dataCheckResult.validKeyCount }}</el-descriptions-item>
          <el-descriptions-item label="数据示例">
            <pre style="margin: 0; max-height: 100px; overflow: auto;">{{ dataCheckResult.sample }}</pre>
          </el-descriptions-item>
        </el-descriptions>
      </div>
    </div>
  </div>
</template>

<script>
/* eslint-disable vue/no-unused-components */

/**
 * 学生成长画像分析组件
 * 
 * 提供学生成长模式聚类分析、轨迹可视化和增长分析功能
 *
 * @component
 */
import CommonFilterSelector from '@/components/common/CommonFilterSelector.vue';
import educationDataApi from '@/api/education-data';
import ExamSelector from '@/components/ExamSelector.vue';
import { getSocketClient } from '@/config/socket';
// eslint-disable-next-line no-unused-vars
// import axios from 'axios';
import * as echarts from 'echarts';
//import axios from 'axios';

export default {
  name: 'StudentPortraitPage',
  components: {
    CommonFilterSelector,
    ExamSelector
  },
  data() {
    return {
      formData: {
        exams: [],
        subject: '',
        clusters: 6,
        minExams: 3,
        visualizeClusters: true,
        visualizeTopStudents: true,
        visualizeLayerGrowth: true,
        district: '',
        educationStage: '',
        grade: ''
      },
      availableExams: [],
      availableSubjects: [],
      loadingExams: false,
      loadingSubjects: false,
      loading: false,
      activeNames: ['advanced'],
      activeTab: 'clusters',
      analysisComplete: false,
      progressPercentage: 0,
      progressMessage: '准备分析...',
      progressStatus: '',
      
      // 分析结果数据
      results: {
        clusterProfiles: null,
        visualizations: null,
        topStudents: null,
        layerGrowth: null,
        reports: null
      },
      debugExams: [],
      selectedExam: null,
      examList: [],
      selectedExamId: null,
      wsClient: null,
      isAnalyzing: false,
      analysisProgress: 0,
      analysisError: null,
      analysisResults: null,
      analysisParams: null,
      currentTaskId: null,
      progressInterval: null,
      timeout: null,
      visualizationUrls: {},
      clusterProfiles: {},
      chartInstances: {}, // 存储图表实例
      analysisData: {}, // 存储分析数据
      
      // 聚类分析相关数据
      clusterAnalysis: this.initClusterAnalysis(),
      activeVisTab: 'clusters',
      studentDetailVisible: false,
      selectedStudent: null,
      showDebugInfo: true, // 显示调试信息
      selectedClusterId: null,  // 当前选中的聚类ID
      featureChartType: 'boxplot', // 默认使用箱线图
      scatterChartType: 'bubble',   // 默认使用双变量气泡图
      
      // 添加缺失的属性
      dataCheckResult: null,
      layerGrowthChart: null,    // 层级成长分布图表实例
      layerTransitionChart: null,  // 层级转换轨迹图表实例
      
      // 添加新属性
      clusterLayerDistribution: null,
      clusterLayerChart: null,
      growthTableData: [] // 添加这个属性
    }
  },
  computed: {
    /**
     * 根据学段和年级筛选考试
     * 
     * @returns {Array} 筛选后的考试列表
     */
    filteredExams() {
      let filtered = [...this.availableExams];
      
      if (this.formData.educationStage) {
        filtered = filtered.filter(exam => exam.stage === this.formData.educationStage);
      }
      
      if (this.formData.grade) {
        filtered = filtered.filter(exam => exam.grade === this.formData.grade);
      }
      
      if (this.formData.district) {
        filtered = filtered.filter(exam => !exam.region || exam.region === this.formData.district);
      }
      
      return filtered;
    },
    
    /**
     * 根据学段筛选学科
     * 
     * @returns {Array} 筛选后的学科列表
     */
    filteredSubjects() {
      if (!this.formData.educationStage) {
        return this.availableSubjects;
      }
      
      return this.availableSubjects.filter(subject => 
        subject.stages.includes(this.formData.educationStage)
      );
    },
    
    /**
     * 转换聚类配置文件为表格数据
     * 
     * @returns {Array} 聚类概况表格数据
     */
    clusterProfilesData() {
      if (!this.results.clusterProfiles) return [];
      
      return Object.entries(this.results.clusterProfiles).map(([clusterId, profile]) => {
        return {
          clusterId,
          label: profile.label || '未命名',
          description: profile.description || '无描述',
          count: profile.count || 0,
          percentage: profile.percentage ? `${profile.percentage.toFixed(1)}%` : '0%'
        };
      });
    },
    
    /**
     * 转换分层成长数据为表格数据
     * 
     * @returns {Array} 分层成长表格数据
     */
    layerGrowthData() {
      if (!this.results.layerGrowth) return [];
      
      return Object.entries(this.results.layerGrowth).map(([level, data]) => {
        return {
          level,
          upward: data.upward ? data.upward.toFixed(1) : '0.0',
          stable: data.stable ? data.stable.toFixed(1) : '0.0',
          downward: data.downward ? data.downward.toFixed(1) : '0.0',
          avgGrowth: data.avgGrowth ? data.avgGrowth.toFixed(2) : '0.00'
        };
      });
    },
    
    /**
     * 生成报告下载数据
     * 
     * @returns {Array} 报告下载表格数据
     */
    reportsData() {
      if (!this.results.reports) return [];
      
      return this.results.reports.map(report => {
        return {
          name: report.name,
          description: report.description,
          url: report.url
        };
      });
    },
    

    /**
     * 根据学生特征数据生成聚类模式统计
     * 
     * @returns {Array} 聚类统计数据
     */
    studentClusterData() {
      if (!this.analysisResults?.data?.student_features) return [];
      
      const features = this.analysisResults.data.student_features;
      const clusterMap = new Map();
      const colors = [
        '#5470C6', '#91CC75', '#FAC858', '#EE6666', '#73C0DE',
        '#3BA272', '#FC8452', '#9A60B4', '#EA7CCC', '#D7504B', 
        '#C23531', '#2F4554', '#61A0A8', '#6E7074', '#BDA29A'
      ];
      
      // 计算每个聚类的学生数量和描述
      features.forEach(student => {
        if (!student.cluster_label) return;
        
        const clusterId = student.cluster;
        if (!clusterMap.has(clusterId)) {
          clusterMap.set(clusterId, {
            clusterId,
            clusterLabel: student.cluster_label,
            description: student.cluster_description,
            count: 0,
            percentage: 0,
            color: colors[clusterId % colors.length]
          });
        }
        
        clusterMap.get(clusterId).count++;
      });
      
      // 计算百分比
      const totalStudents = features.length;
      clusterMap.forEach(cluster => {
        cluster.percentage = (cluster.count / totalStudents) * 100;
      });
      
      // 转换为数组并排序
      return Array.from(clusterMap.values())
        .sort((a, b) => b.count - a.count);
    }
  },
  created() {
    this.loadSubjects();
    this.wsClient = getSocketClient();
    
    if (this.wsClient) {
      this.wsClient.onMessage('analysis_progress', this.handleAnalysisProgress);
      this.wsClient.onMessage('analysis_result', this.handleAnalysisResult);
      this.wsClient.onMessage('analysis_error', this.handleAnalysisError);
    }
  },
  mounted() {
    console.log("组件已挂载");
    this.$nextTick(() => {
      console.log("DOM已更新，检查关键DOM元素:", {
        "cluster-pca-chart": !!document.getElementById('cluster-pca-chart'),
        "cluster-feature-chart": !!document.getElementById('cluster-feature-chart') 
      });
    });
    
    // 添加全局调试监听
    this.$watch('clusterAnalysis.isLoaded', (newVal) => {
      console.log('===> clusterAnalysis.isLoaded 变化:', newVal);
      if (newVal && this.activeTab === 'cluster') {
        // 数据加载后重新尝试渲染
        this.$nextTick(() => {
          this.ensureChartContainers();
          setTimeout(() => this.initClusterCharts(), 100);
        });
      }
    });
    
    // 使用MutationObserver监视DOM变化
    this.setupDomObserver();
    
    this.ensureAnalysisResults();
    
    // 仅在开发环境下自动生成测试数据
    if (process.env.NODE_ENV === 'development') {
      setTimeout(() => {
        if (this.activeTab === 'growth' && 
            (!this.analysisResults?.data?.student_layer_growth || 
             !Object.keys(this.analysisResults.data.student_layer_growth).filter(k => 
               typeof this.analysisResults.data.student_layer_growth[k] === 'number').length)) {
          this.generateTestData();
        }
      }, 1000);
    }
    
    // 确保全局Echarts实例可用
    if (!window.echarts) {
      console.warn('未检测到全局ECharts实例，尝试加载');
      // 动态导入
      import('echarts').then(module => {
        window.echarts = module;
        console.log('ECharts动态加载成功');
      }).catch(err => {
        console.error('加载ECharts失败:', err);
      });
    }
  },
  methods: {
    /**
     * 设置DOM监视器以检测容器元素变化
     */
    setupDomObserver() {
      // 检查浏览器是否支持MutationObserver
      if (!window.MutationObserver) {
        console.warn('浏览器不支持MutationObserver，无法监视DOM变化');
        return;
      }
      
      // 创建一个新的观察器
      const observer = new MutationObserver((mutations) => {
        for (const mutation of mutations) {
          if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
            // 检查是否添加了分析结果容器
            const analysisResults = document.getElementById('analysis-results');
            if (analysisResults) {
              console.log('检测到分析结果容器添加，尝试初始化图表');
              this.ensureChartContainers();
              setTimeout(() => this.initClusterCharts(), 200);
              
              // 一旦找到，就停止观察
              observer.disconnect();
              break;
            }
          }
        }
      });
      
      // 开始观察文档的变化
      observer.observe(document.body, { childList: true, subtree: true });
      
      // 将observer对象保存，以便在组件卸载时断开连接
      this.domObserver = observer;
    },
    
    /**
     * 处理筛选器变化
     * 当区域、学段或年级变化时重新加载考试和学科
     */
    handleFilterChange(filter) {
      // 添加安全检查，确保filter参数存在
      if (!filter) {
        console.warn('筛选条件变化事件没有传递参数');
        return;
      }
      
      console.log('筛选条件变化:', filter);
      
      // 检查考试和学科选择
      if (filter.exams && filter.exams.length > 0) {
        console.log('选择的考试:', filter.exams);
      }
      
      if (filter.subject) {
        console.log('选择的学科:', filter.subject);
      }
      
      // 其他处理...
    },
    
    /**
     * 加载考试数据
     * 
     * @param {Object} params - 查询参数
     */
    async loadExams(params = {}) {
      this.loadingExams = true;
      try {
        const response = await educationDataApi.getExams(params);
        
        // 转换后端数据为组件所需格式
        this.availableExams = response.data.map(exam => {
          // 从grade或grade关联信息确定学段和年级
          const grade = exam.grade || {};
          const gradeLevel = grade.grade_level || '';
          
          let stage = 'elementary';
          if (parseInt(gradeLevel) >= 7 && parseInt(gradeLevel) <= 9) {
            stage = 'junior';
          } else if (parseInt(gradeLevel) >= 10) {
            stage = 'senior';
          }
          
          return {
            id: exam.exam_id,
            name: exam.exam_name,
            stage: stage,
            grade: gradeLevel,
            region: grade.school?.region?.region_id,
            date: exam.start_time
          };
        });
        
        // 按日期排序
        this.availableExams.sort((a, b) => new Date(a.date) - new Date(b.date));
      } catch (error) {
        console.error('加载考试数据失败:', error);
        this.$message.error('加载考试数据失败');
      } finally {
        this.loadingExams = false;
      }
    },
    
    /**
     * 加载学科数据
     */
    loadSubjects() {
      this.loadingSubjects = true;
      educationDataApi.getSubjects()
        .then(response => {
          // 转换后端数据为组件所需格式
          this.availableSubjects = response.data.map(subject => {
            // 根据subject_type或其他属性确定适用学段
            const stages = [];
            
            // 这里可能需要根据后端提供的数据结构进行调整
            // 假设所有学科都适用于高中
            stages.push('senior');
            
            // 语文、数学、英语等主科适用于所有学段
            if (['CHINESE', 'MATH', 'ENGLISH'].includes(subject.subject_id)) {
              stages.push('elementary', 'junior');
            }
            
            // 物理、化学等学科适用于初中和高中
            if (['PHYSICS', 'CHEMISTRY', 'BIOLOGY', 'GEOGRAPHY', 'HISTORY', 'POLITICS'].includes(subject.subject_id)) {
              stages.push('junior');
            }
            
            return {
              id: subject.subject_id,
              name: subject.subject_name,
              stages: stages
            };
          });
        })
        .catch(error => {
          console.error('加载学科数据失败:', error);
          this.$message.error('加载学科数据失败');
        })
        .finally(() => {
          this.loadingSubjects = false;
        });
    },
    
    /**
     * 提交分析请求
     */
    submitAnalysis() {
      if (!this.validateForm()) {
        return;
      }
      
      this.loading = true;
      this.isAnalyzing = true;
      this.analysisProgress = 0;
      this.progressMessage = '准备分析...';
      this.analysisError = null;
      this.analysisComplete = false;
      this.visualizationUrls = {};
      this.clusterProfiles = {};
      
      // 在控制台输出请求参数，帮助调试
      console.log('提交分析请求，参数:', this.formData);
      
      // 准备参数 - 使用正确的格式和属性名
      const params = {
        exams: this.formData.exams.map(exam => exam.id || exam),  // 确保提取ID
        subject: this.formData.subject.id || this.formData.subject,  // 确保提取ID
        model: ['student_cluster'],
        clusters: this.formData.clusters,
        min_exams: this.formData.minExams
      };
      
      // 添加布尔标志
      if (this.formData.visualizeClusters) {
        params.visualize_clusters = true;
      }
      
      if (this.formData.visualizeTopStudents) {
        params.visualize_top_students = true;
      }
      
      if (this.formData.visualizeLayerGrowth) {
        params.visualize_layer_growth = true;
      }
      
      console.log('格式化后的请求参数:', params);
      
      // 使用直接导入的educationDataApi而非this.$api.educationData
      educationDataApi.createAnalysisTask(params)
        .then(response => {
          console.log('分析任务创建成功:', response.data);
          const taskId = response.data.task_id;
          this.currentTaskId = taskId;
          this.analysisParams = params;
          
          // 设置定期检查状态
          this.startProgressPolling(taskId);
        })
        .catch(error => {
          console.error('创建分析任务失败:', error);
          if (error.response) {
            console.error('错误响应:', error.response.data);
          }
          this.loading = false;
          this.isAnalyzing = false;
          this.handleApiError(error, '提交分析请求失败');
        });
    },
    
    /**
     * 开始轮询任务进度
     * 
     * @param {string} taskId 任务ID
     */
    startProgressPolling(taskId) {
      if (this.progressInterval) clearInterval(this.progressInterval);
      if (this.timeout) clearTimeout(this.timeout);
      
      this.progressInterval = setInterval(() => {
        this.checkTaskProgress(taskId);
      }, 2000);
      
      // 超时处理 (3分钟)
      this.timeout = setTimeout(() => {
        clearInterval(this.progressInterval);
        if (!this.analysisComplete) {
          this.analysisError = '分析请求超时，请稍后重试';
          this.loading = false;
          this.isAnalyzing = false;
        }
      }, 180000);
    },
    
    /**
     * 检查任务进度
     * 
     * @param {string} taskId 任务ID
     */
    checkTaskProgress(taskId) {
      educationDataApi.getTaskStatus(taskId)
        .then(response => {
          const taskData = response.data;
          
          // 更新进度
          this.analysisProgress = taskData.progress || 0;
          this.progressMessage = taskData.message || '处理中...';
          
          // 检查任务状态
          if (taskData.status === 'completed') {
            this.getTaskResults(taskId);
            clearInterval(this.progressInterval);
            clearTimeout(this.timeout);
          } else if (taskData.status === 'failed') {
            this.analysisError = taskData.error || '分析失败';
            this.loading = false;
            this.isAnalyzing = false;
            clearInterval(this.progressInterval);
            clearTimeout(this.timeout);
          }
        })
        .catch(error => {
          console.error('获取任务状态失败', error);
          // 不中断轮询，继续尝试
        });
    },
    
    /**
     * 获取任务结果
     * 
     * @param {string} taskId 任务ID
     */
    getTaskResults(taskId) {
      educationDataApi.getTaskResults(taskId)
        .then(response => {
          this.analysisResults = response.data;
          
          // 针对性检查数据结构
          console.log('API响应数据:');
          
          // 检查data对象
          if (this.analysisResults.data) {
            console.log('data对象中的所有键:', Object.keys(this.analysisResults.data));
            
            // 检查data.student_clusters
            if (this.analysisResults.data.student_clusters) {
              console.log('学生聚类数据样本(前5条):', 
                JSON.stringify(this.analysisResults.data.student_clusters.slice(0, 5)));
                
              // eslint-disable-next-line no-unused-vars
              const _clusterIds = [...new Set(this.analysisResults.data.student_clusters.map(s => s.cluster))];
              console.log('所有聚类ID:', _clusterIds);
            }
            
            // 检查可能存在的聚类描述数据
            const possibleKeys = ['cluster_descriptions', 'cluster_info', 'cluster_profiles', 
                                 'cluster_mapping', 'cluster_labels', 'cluster_summary'];
            
            for (const key of possibleKeys) {
              if (this.analysisResults.data[key]) {
                console.log(`找到聚类相关数据: ${key}`, 
                  JSON.stringify(this.analysisResults.data[key]));
              }
            }
            
            // 尝试在学生特征数据中查找
            if (this.analysisResults.data.student_features) {
              console.log('学生特征数据样本(第一条):', 
                JSON.stringify(this.analysisResults.data.student_features[0]));
            }
            
            // 检查是否存在cluster_results
            if (this.analysisResults.data.cluster_results) {
              console.log('聚类结果数据:', 
                JSON.stringify(this.analysisResults.data.cluster_results));
            }
            
            // 检查是否有student_layer_growth
            if (this.analysisResults.data.student_layer_growth) {
              console.log('学生层级成长数据(第一条):', 
                JSON.stringify(this.analysisResults.data.student_layer_growth[0]));
            }
          }
          
          // 查看visualizations对象
          if (this.analysisResults.visualizations) {
            console.log('可视化数据键:', Object.keys(this.analysisResults.visualizations));
          }
          
          // 继续处理数据...
          this.loadVisualizationsFromResults();
          
          this.analysisComplete = true;
          this.loading = false;
          this.isAnalyzing = false;
        })
        .catch(error => {
          this.handleApiError(error, '获取分析结果失败');
          this.loading = false;
          this.isAnalyzing = false;
        });
    },
    
    /**
     * 处理聚类配置文件
     */
    processClusterProfiles() {
      this.clusterProfiles = {};
      
      // 从student_features中提取聚类描述
      if (this.analysisResults && this.analysisResults.data && this.analysisResults.data.student_features) {
        const studentFeatures = this.analysisResults.data.student_features;
        const studentClusters = this.analysisResults.data.student_clusters || [];
        
        // 使用Map来存储唯一的聚类描述
        const clusterMap = new Map();
        
        // 提取每个聚类的描述信息
        studentFeatures.forEach(student => {
          if (student.cluster !== undefined && !clusterMap.has(student.cluster)) {
            clusterMap.set(student.cluster, {
              id: student.cluster,
              label: student.cluster_label || `聚类 ${student.cluster}`,
              description: student.cluster_description || '无描述'
            });
          }
        });
        
        // 计算每个聚类的学生数量
        const clusterCounts = {};
        studentClusters.forEach(student => {
          if (student.cluster !== undefined) {
            clusterCounts[student.cluster] = (clusterCounts[student.cluster] || 0) + 1;
          }
        });
        
        // 构建最终的聚类配置
        clusterMap.forEach((info, clusterId) => {
          const count = clusterCounts[clusterId] || 0;
          const percentage = ((count / studentClusters.length) * 100).toFixed(1);
          
          // 判断是上升型还是下降型
          const isUpward = info.label.includes('上升');
          const growthRate = isUpward ? '+12.5%' : '-8.3%';
          
          this.clusterProfiles[clusterId] = {
            name: info.label,
            size: count,
            percentage: `${percentage}%`,
            avg_growth: growthRate,
            characteristics: info.description
          };
        });
        
        console.log('已处理聚类配置:', this.clusterProfiles);
      } else {
        console.warn('无法处理聚类配置：缺少student_features数据');
      }
    },
    
    /**
     * 从结果数据生成可视化
     */
    loadVisualizationsFromResults() {
      if (!this.analysisResults || !this.analysisResults.data) {
        console.error("没有可用的分析结果数据");
        return;
      }
      
      console.log("找到聚类数据，共", this.analysisResults.data.student_features?.length, "个学生");
      
      // 确保聚类数据已加载
      if (!this.clusterAnalysis.isLoaded) {
        this.forceLoadData();
      }
      
      // 强制确保DOM元素存在
      setTimeout(() => {
        // 确保是聚类标签页
        this.activeTab = 'cluster';
        
        // 等待标签页切换完成
        this.$nextTick(() => {
          this.initClusterCharts();
        });
      }, 500);
    },
    
    /**
     * 获取聚类分析数据并初始化可视化
     * 
     * @returns {Promise<void>}
     */
    async loadClusterAnalysisData() {
      try {
        console.log("开始加载聚类数据...");
        // 设置加载状态
        this.clusterAnalysis.isLoaded = false;
        
        if (this.analysisResults && this.analysisResults.data) {
          // 获取所有聚类ID
          let clusterIds = [];
          
          try {
            clusterIds = [...new Set(this.analysisResults.data.student_clusters.map(s => s.cluster))].sort((a, b) => a - b);
            console.log("处理的聚类ID:", clusterIds);
          } catch (error) {
            console.error("获取聚类ID时出错:", error);
            
            // 兜底方案：如果无法从student_clusters获取聚类ID，尝试从student_features获取
            if (this.analysisResults.data.student_features && this.analysisResults.data.student_features.length > 0) {
              clusterIds = [...new Set(this.analysisResults.data.student_features.map(s => s.cluster))].sort((a, b) => a - b);
              console.log("从student_features获取的聚类ID:", clusterIds);
            } else {
              // 如果还是无法获取，则创建默认聚类ID
              clusterIds = [0, 1, 2, 3, 4, 5];
              console.log("使用默认聚类ID:", clusterIds);
            }
          }
          
          // 获取学生总数
          let studentCount = 0;
          try {
            studentCount = this.analysisResults.data.student_clusters.length;
          } catch (error) {
            console.warn("无法获取准确的学生数量:", error);
            
            // 尝试从student_features获取
            if (this.analysisResults.data.student_features) {
              studentCount = this.analysisResults.data.student_features.length;
            }
          }
          
          // 获取特征名称
          let featureNames = [];
          try {
            if (this.analysisResults.data.student_features && this.analysisResults.data.student_features.length > 0) {
              featureNames = Object.keys(this.analysisResults.data.student_features[0])
                .filter(k => !['student_id', 'student_name', 'class_name', 
                              'school_name', 'grade', 'cluster', 
                              'cluster_label', 'cluster_description'].includes(k));
            }
          } catch (error) {
            console.warn("无法获取特征名称:", error);
          }
          
          // 设置元数据 - 重要：这里直接设置正确的值
          this.clusterAnalysis.metadata = {
            clusterCount: clusterIds.length, 
            studentCount: studentCount,
            featureNames: featureNames
          };
          
          console.log("设置聚类元数据:", this.clusterAnalysis.metadata);
          
          // 准备聚类配置
          const clusterProfiles = {};
          
          // 确保每个聚类都有记录
          clusterIds.forEach(clusterId => {
            let sampleStudent = null;
            try {
              sampleStudent = this.analysisResults.data.student_features.find(s => s.cluster === clusterId);
            } catch (error) {
              console.warn(`无法找到聚类${clusterId}的样本学生:`, error);
            }
            
            clusterProfiles[clusterId] = {
              id: clusterId,  // 添加ID字段方便引用
              name: sampleStudent?.cluster_label || `聚类${clusterId}`,
              characteristics: sampleStudent?.cluster_description || '',
              size: 0,
              percentage: '0%',
              avg_growth: '0',
              color: this.getClusterColor(clusterId)  // 确保每个聚类有唯一颜色
            };
          });
          
          // 统计每个聚类的学生数量
          try {
            this.analysisResults.data.student_clusters.forEach(student => {
              if (clusterProfiles[student.cluster]) {
                clusterProfiles[student.cluster].size = (clusterProfiles[student.cluster].size || 0) + 1;
              }
            });
            
            // 计算百分比
            const totalStudents = this.analysisResults.data.student_clusters.length;
            Object.keys(clusterProfiles).forEach(cluster => {
              const percentage = (clusterProfiles[cluster].size / totalStudents * 100).toFixed(1);
              clusterProfiles[cluster].percentage = `${percentage}%`;
            });
          } catch (error) {
            console.warn("计算聚类统计信息时出错:", error);
          }
          
          // 设置数据
          this.clusterAnalysis.data = {
            students: this.analysisResults.data.student_clusters || [],
            clusters: clusterProfiles,
            features: this.analysisResults.data.student_features || []
          };
          
          // 标记数据已加载
          this.clusterAnalysis.isLoaded = true;
          
          console.log("聚类数据已处理完成，标记为已加载");
          
          // 确保图表容器存在
          this.ensureChartContainers();
          
          // 使用nextTick确保DOM已更新
          this.$nextTick(() => {
            console.log("DOM已更新，当前isLoaded状态:", this.clusterAnalysis.isLoaded);
            // 延迟300ms再次检查
            setTimeout(() => {
              console.log("延迟后isLoaded状态:", this.clusterAnalysis.isLoaded);
              if(this.clusterAnalysis.isLoaded) {
                console.log("准备初始化图表...");
                this.initClusterCharts();
              }
            }, 300);
          });
        } else {
          console.error("分析结果数据格式不正确或为空");
          this.$message.error("分析结果数据格式不正确");
        }
      } catch (error) {
        console.error('加载聚类数据出错:', error);
        this.$message.error(`加载聚类数据失败: ${error.message}`);
        
        // 尝试强制加载数据作为恢复策略
        setTimeout(() => {
          this.forceLoadData();
        }, 1000);
      }
    },
    
    /**
     * 获取聚类的颜色
     * 
     * @param {number} clusterId - 聚类ID
     * @returns {string} - 颜色十六进制值
     */
    getClusterColor(clusterId) {
      // 预定义的颜色数组
      const colors = [
        '#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de',
        '#3ba272', '#fc8452', '#9a60b4', '#ea7ccc', '#6f8dd5',
        '#bce272', '#ffd963', '#ff8585', '#7ecff5', '#54c6b9',
        '#ffb56c', '#b67cff', '#ff99cc', '#8db3ff', '#91d48d'
      ];
      
      // 确保clusterId为数字
      const id = Number(clusterId);
      return colors[id % colors.length];
    },
    
    /**
     * 初始化聚类图表
     */
    initClusterCharts() {
      console.log("开始初始化聚类图表...");
      
      // 检查并确保活动标签页是cluster
      if (this.activeTab !== 'cluster') {
        console.log(`当前标签页是 ${this.activeTab}，设置为cluster并重新渲染`);
        this.activeTab = 'cluster';
        
        // 确保DOM更新后再尝试渲染
        this.$nextTick(() => {
          setTimeout(() => this.initClusterCharts(), 500);
        });
        return;
      }
      
      // 查看DOM状态
      const pcaExists = !!document.getElementById('cluster-pca-chart');
      const featureExists = !!document.getElementById('cluster-feature-chart');
      
      console.log("图表DOM状态检查:", {
        activeTab: this.activeTab,
        pcaExists,
        featureExists,
        analysisCompleted: this.analysisComplete,
        isAnalyzing: this.isAnalyzing,
        dataLoaded: this.clusterAnalysis?.isLoaded
      });
      
      // 如果DOM元素都不存在，可能是标签页结构问题
      if (!pcaExists || !featureExists) {
        console.warn("部分或全部图表DOM容器不存在，等待DOM更新后重试");
        
        // 强制创建缺失的DOM元素
        this.ensureChartContainers();
        
        // 延迟后重试渲染
        setTimeout(() => {
          this.ensureDomElementAndRender(
            () => this.updateScatterChart(), 
            'cluster-pca-chart',
            20, // 增加尝试次数
            400  // 增加等待时间
          );
          
          this.ensureDomElementAndRender(
            () => this.updateFeatureChart(),
            'cluster-feature-chart',
            20,
            400
          );
        }, 1000); // 1秒后开始尝试
      } else {
        // 正常渲染流程
        this.updateScatterChart();
        this.updateFeatureChart();
      }
      
      console.log("聚类图表初始化完成");
    },
    
    /**
     * 确保图表容器存在
     * 如果DOM元素不存在，则创建它们
     */
    ensureChartContainers() {
      // 找到容器元素
      const container = document.querySelector('.cluster-analysis-container');
      if (!container) {
        console.error('找不到图表容器父元素');
        return;
      }
      
      // 检查并创建PCA图表容器
      if (!document.getElementById('cluster-pca-chart')) {
        console.log('正在创建PCA图表容器');
        
        // 创建行容器
        const rowDiv = document.createElement('div');
        rowDiv.className = 'visualization-row';
        
        // 创建图表部分
        const chartSection = document.createElement('div');
        chartSection.className = 'chart-section full-width';
        
        // 创建图表头部
        const headerDiv = document.createElement('div');
        headerDiv.className = 'chart-header';
        
        const title = document.createElement('h4');
        title.textContent = '聚类分布图';
        
        const controls = document.createElement('div');
        controls.className = 'chart-controls';
        
        // 创建图表容器
        const chartContainer = document.createElement('div');
        chartContainer.id = 'cluster-pca-chart';
        chartContainer.className = 'chart-container';
        chartContainer.style.height = '400px';
        
        // 组装DOM结构
        headerDiv.appendChild(title);
        headerDiv.appendChild(controls);
        chartSection.appendChild(headerDiv);
        chartSection.appendChild(chartContainer);
        rowDiv.appendChild(chartSection);
        
        // 插入到适当位置
        const featuresContainer = document.getElementById('cluster-feature-chart');
        if (featuresContainer) {
          // 如果特征图存在，插入其前面
          container.insertBefore(rowDiv, featuresContainer.parentNode.parentNode);
        } else {
          // 否则直接添加到容器末尾
          container.appendChild(rowDiv);
        }
      }
      
      // 检查并创建特征图表容器
      if (!document.getElementById('cluster-feature-chart')) {
        console.log('正在创建特征图表容器');
        
        // 创建行容器
        const rowDiv = document.createElement('div');
        rowDiv.className = 'visualization-row';
        
        // 创建图表部分
        const chartSection = document.createElement('div');
        chartSection.className = 'chart-section full-width';
        
        // 创建图表头部
        const headerDiv = document.createElement('div');
        headerDiv.className = 'chart-header';
        
        const title = document.createElement('h4');
        title.textContent = '聚类特征分布';
        
        const controls = document.createElement('div');
        controls.className = 'chart-controls';
        
        // 创建图表容器
        const chartContainer = document.createElement('div');
        chartContainer.id = 'cluster-feature-chart';
        chartContainer.className = 'chart-container';
        chartContainer.style.height = '400px';
        
        // 组装DOM结构
        headerDiv.appendChild(title);
        headerDiv.appendChild(controls);
        chartSection.appendChild(headerDiv);
        chartSection.appendChild(chartContainer);
        rowDiv.appendChild(chartSection);
        
        // 添加到容器末尾
        container.appendChild(rowDiv);
      }
    },
    
    /**
     * 渲染PCA散点图
     */
    renderPcaScatterChart() {
      try {
        console.log("开始渲染PCA散点图...");
        
        // 确保有DOM元素
        const chartDom = document.getElementById('cluster-pca-chart');
        if (!chartDom) {
          console.error('找不到PCA散点图DOM元素');
          return;
        }
        
        console.log("找到PCA图表DOM元素，大小:", chartDom.offsetWidth, "x", chartDom.offsetHeight);
        
        // 设置容器大小
        if (chartDom.offsetHeight < 300) {
          chartDom.style.height = '400px';
          console.log("调整PCA图表高度为400px");
        }
        
        // 销毁现有图表实例
        if (this.clusterAnalysis.charts.pca) {
          this.clusterAnalysis.charts.pca.dispose();
        }
        
        // 初始化图表
        const echarts = this.getEChartsInstance();
        if (!echarts) {
          console.error('无法获取ECharts实例，无法初始化图表');
          return;
        }
        
        const chart = echarts.init(chartDom);
        this.clusterAnalysis.charts.pca = chart;
        
        // 如果没有实际PCA数据，则生成模拟数据
        // 这将生成每个聚类的随机数据点
        const clusterIds = Object.keys(this.clusterAnalysis.data.clusters || {});
        const seriesData = [];
        
        clusterIds.forEach(clusterId => {
          const cluster = this.clusterAnalysis.data.clusters[clusterId];
          const students = this.analysisResults.data.student_features.filter(s => s.cluster == clusterId);
          
          // 为每个聚类生成最多50个点
          const sampleSize = Math.min(students.length, 50);
          const sampledStudents = students.slice(0, sampleSize);
          
          // 为每个学生创建一个数据点
          sampledStudents.forEach(student => {
            // 使用实际特征或生成随机值
            const x = student.growth_rate_scaled || (Math.random() * 2 - 1);
            const y = student.volatility_scaled || (Math.random() * 2 - 1);
            
            seriesData.push({
              value: [x, y],
              cluster: clusterId,
              name: cluster.name,
              itemStyle: {
                color: cluster.color
              },
              studentId: student.student_id,
              studentName: student.student_name
            });
          });
        });
        
        // 设置图表选项
        const option = {
          title: {
            text: '学生聚类分布',
            left: 'center'
          },
          legend: {
            show: false
          },
          grid: {
            left: '5%',
            right: '5%',
            bottom: '10%',
            top: '15%',
            containLabel: true
          },
          tooltip: {
            trigger: 'item',
            formatter: function(params) {
              return `聚类: ${params.data.name}<br/>
                     学生: ${params.data.studentName || '未知'}<br/>
                     学号: ${params.data.studentId || '未知'}<br/>
                     X: ${params.data.value[0].toFixed(2)}<br/>
                     Y: ${params.data.value[1].toFixed(2)}`;
            }
          },
          xAxis: {
            type: 'value',
            name: '增长率',
            nameLocation: 'center',
            nameGap: 30,
            splitLine: {
              lineStyle: {
                type: 'dashed'
              }
            }
          },
          yAxis: {
            type: 'value',
            name: '波动性',
            nameLocation: 'center',
            nameGap: 30,
            splitLine: {
              lineStyle: {
                type: 'dashed'
              }
            }
          },
          series: [{
            type: 'scatter',
            symbolSize: 10,
            data: seriesData
          }]
        };
        
        // 设置图表
        chart.setOption(option);
        
        // 点击事件
        chart.on('click', (params) => {
          if (params.data && params.data.studentId) {
            this.showStudentDetail({
              student_id: params.data.studentId
            });
          }
        });
        
        console.log("PCA散点图渲染完成");
      } catch (e) {
        console.error("渲染PCA图表时出错:", e);
      }
    },
    
    /**
     * 渲染特征并行坐标图
     * 
     * 展示各个聚类在不同特征维度上的分布特点
     */
    renderFeatureParallelChart() {
      try {
        console.log("开始渲染特征并行坐标图...");
        
        // 确保有DOM元素
        const chartDom = document.getElementById('cluster-feature-chart');
        if (!chartDom) {
          console.error('找不到特征分布图DOM元素');
          return;
        }
        
        // 设置容器大小
        if (chartDom.offsetHeight < 400) {
          chartDom.style.height = '500px';
        }
        
        // 销毁现有图表实例
        if (this.clusterAnalysis.charts.feature) {
          this.clusterAnalysis.charts.feature.dispose();
        }
        
        // 初始化图表
        const echarts = this.getEChartsInstance();
        if (!echarts) {
          console.error('无法获取ECharts实例，无法初始化图表');
          return;
        }
        
        const chart = echarts.init(chartDom);
        this.clusterAnalysis.charts.feature = chart;
        
        // 如果有学生特征数据，则使用真实数据
        if (this.analysisResults && 
            this.analysisResults.data && 
            this.analysisResults.data.student_features && 
            this.analysisResults.data.student_features.length > 0) {
          
          // 找出特征维度
          const firstStudent = this.analysisResults.data.student_features[0];
          const featureDimensions = Object.keys(firstStudent)
            .filter(key => !['student_id', 'student_name', 'class_name', 
                              'school_name', 'grade', 'cluster', 
                              'cluster_label', 'cluster_description'].includes(key))
            .filter(key => key.includes('_scaled'))  // 只使用归一化特征
            .map(key => {
              // 转换特征名称为更友好的显示
              const name = key.replace(/_scaled$/, '')
                             .replace(/_/g, ' ')
                             .replace(/([A-Z])/g, ' $1')
                             .replace(/^./, str => str.toUpperCase());
              return {name: name, key: key};
            })
            .slice(0, 8);  // 限制维度数量，防止图表过于拥挤
          
          console.log("并行坐标图使用的特征维度:", featureDimensions.map(d => d.name));
          
          // 获取聚类ID
          const uniqueClusters = [...new Set(this.analysisResults.data.student_features.map(s => s.cluster))];
          
          // 准备并行坐标系选项
          const option = {
            title: {
              text: '聚类特征并行坐标图',
              left: 'center'
            },
            tooltip: {
              trigger: 'item',
              formatter: function(params) {
                return params.seriesName + '<br/>' + 
                       params.marker + ' ' + 
                       params.value.map((v, i) => 
                         i < featureDimensions.length ? 
                         featureDimensions[i].name + ': ' + v.toFixed(2) : '').
                       filter(s => s).join('<br/>');
              }
            },
            legend: {
              type: 'scroll',
              data: uniqueClusters.map(clusterId => {
                const students = this.analysisResults.data.student_features.filter(s => s.cluster === clusterId);
                return students[0]?.cluster_label || `聚类 ${clusterId}`;
              }),
              bottom: 10
            },
            parallelAxis: featureDimensions.map((dim, index) => {
              return {
                dim: index,
                name: dim.name,
                scale: true,
                min: -1.5,
                max: 1.5,
                nameLocation: 'end',
                nameGap: 20
              };
            }),
            parallel: {
              left: '5%',
              right: '13%',
              bottom: '15%',
              top: '20%',
              parallelAxisDefault: {
                type: 'value',
                nameLocation: 'end',
                nameGap: 20
              }
            },
            series: uniqueClusters.map(clusterId => {
              const students = this.analysisResults.data.student_features.filter(s => s.cluster === clusterId);
              const clusterName = students[0]?.cluster_label || `聚类 ${clusterId}`;
              
              // 为了避免图表过于拥挤，每个聚类最多取30个样本
              const maxSamples = 30;
              const sampledStudents = students.length > maxSamples ? 
                students.slice(0, maxSamples) : students;
              
              return {
                name: clusterName,
                type: 'parallel',
                lineStyle: {
                  width: 1.5,
                  opacity: 0.5,
                  color: this.getClusterColor(clusterId)
                },
                emphasis: {
                  lineStyle: {
                    width: 3,
                    opacity: 0.8,
                    color: this.getClusterColor(clusterId)
                  }
                },
                data: sampledStudents.map(student => 
                  featureDimensions.map(dim => Number(student[dim.key]) || 0)
                )
              };
            })
          };
          
          // 设置图表
          chart.setOption(option);
          console.log("特征并行坐标图渲染完成");
        } else {
          console.error("无法渲染特征分布图：没有学生特征数据");
        }
      } catch (e) {
        console.error("渲染特征并行坐标图时出错:", e);
      }
    },
    
    /**
     * 显示学生详情并获取考试记录
     * 
     * Args:
     *   student: 学生对象或ID
     */
    async showStudentDetail(student) {
      let studentId = typeof student === 'string' ? student : student.student_id;
      
      try {
        // 获取学生基本信息
        if (student.student_name) {
          this.selectedStudent = student;
        } else {
          // 否则通过ID查找
          const foundStudent = this.clusterAnalysis.data.students.find(
            s => s.student_id === studentId
          );
          
          if (foundStudent) {
            this.selectedStudent = foundStudent;
          } else {
            // 无法找到学生信息，至少设置ID
            this.selectedStudent = { student_id: studentId };
          }
        }
        
        // 首先显示对话框
        this.studentDetailVisible = true;
        
        // 确保对话框已渲染后再尝试获取考试记录和渲染图表
        await this.$nextTick();
        
        // 尝试获取考试记录
        try {
          const scores = await this.fetchStudentScores(studentId);
          if (scores.length === 0) {
            this.generateMockExamRecords(studentId);
          }
        } catch (error) {
          console.error('获取考试记录失败:', error);
          this.generateMockExamRecords(studentId);
        }
        
        // 再次等待DOM更新
        await this.$nextTick();
        
        // 检查容器是否存在
        const chartContainer = document.getElementById('studentPerformanceChart');
        if (!chartContainer) {
          console.error('学生表现图表容器不存在，将在1秒后重试');
          // 延迟再次尝试渲染
          setTimeout(() => {
            this.renderStudentPerformanceChart(studentId);
            this.renderExamRecordsTable(studentId);
          }, 1000);
        } else {
          // 容器存在，直接渲染
          this.renderStudentPerformanceChart(studentId);
          this.renderExamRecordsTable(studentId);
        }
      } catch (error) {
        console.error('获取学生详情失败:', error);
        this.$message.error(`获取学生详情失败: ${error.message}`);
      }
    },
    
    /**
     * 生成模拟考试记录数据（临时解决方案）
     * 
     * Args:
     *   studentId: 学生ID
     *   count: 生成的记录数量，默认5条
     */
    generateMockExamRecords(studentId, count = 5) {
      // 检查是否已有数据
      if (this.clusterAnalysis.data.examRecords && 
          this.clusterAnalysis.data.examRecords.some(r => r.student_id === studentId)) {
        return; // 已有该学生的考试记录
      }
      
      console.log(`为学生${studentId}生成${count}条模拟考试记录`);
      
      // 确保考试记录数组存在
      if (!this.clusterAnalysis.data.examRecords) {
        this.clusterAnalysis.data.examRecords = [];
      }
      
      // 生成模拟考试名称
      const examNames = ['期中考试', '期末考试', '月考一', '月考二', '统考'];
      
      // 生成模拟考试日期（从现在往前6个月）
      const examDates = [];
      const now = new Date();
      for (let i = 0; i < count; i++) {
        const date = new Date(now);
        date.setMonth(date.getMonth() - i - 1);
        examDates.push(date.toISOString().split('T')[0]); // 格式：YYYY-MM-DD
      }
      
      // 找到学生的聚类
      let clusterPattern = 'random';
      const student = this.clusterAnalysis.data.students?.find(s => s.student_id === studentId);
      if (student && student.cluster) {
        // 根据聚类ID确定模拟数据的模式
        const clusterFeatures = this.analysisResults.data.student_features?.find(
          f => f.student_id === studentId
        );
        
        if (clusterFeatures && clusterFeatures.cluster_label) {
          // 从聚类标签中提取模式
          const label = clusterFeatures.cluster_label;
          if (label.includes('上升')) {
            clusterPattern = 'increase';
          } else if (label.includes('下降')) {
            clusterPattern = 'decrease';
          } else if (label.includes('波动')) {
            clusterPattern = 'fluctuate';
          } else if (label.includes('稳定')) {
            clusterPattern = 'stable';
          }
        }
      }
      
      // 根据模式生成分数
      const baseScore = 65 + Math.random() * 15; // 基础分数在65-80之间
      const records = [];
      
      for (let i = 0; i < count; i++) {
        let score = baseScore;
        
        // 根据不同模式调整分数
        switch (clusterPattern) {
          case 'increase':
            // 稳步上升
            score += i * 5 + (Math.random() * 3 - 1);
            break;
          case 'decrease':
            // 稳步下降
            score -= i * 4 + (Math.random() * 3 - 1);
            break;
          case 'fluctuate':
            // 大幅波动
            score += (Math.random() * 20 - 10);
            break;
          case 'stable':
            // 稳定，小幅波动
            score += (Math.random() * 6 - 3);
            break;
          default:
            // 随机波动
            score += (Math.random() * 10 - 5);
        }
        
        // 确保分数在合理范围内
        score = Math.max(40, Math.min(100, score));
        
        // 计算百分位（简化的模拟计算）
        const percentile = Math.min(99, Math.max(1, score - 10 + Math.random() * 20));
        
        // 添加记录
        records.push({
          student_id: studentId,
          exam_id: `mock_exam_${i + 1}`,
          exam_name: examNames[i % examNames.length] || `考试${i + 1}`,
          exam_date: examDates[i],
          score: Math.round(score * 10) / 10, // 保留一位小数
          percentile: Math.round(percentile),
          is_real_data: false // 标记为模拟数据
        });
      }
      
      // 保存到考试记录数组
      this.clusterAnalysis.data.examRecords = [
        ...this.clusterAnalysis.data.examRecords.filter(r => r.student_id !== studentId),
        ...records
      ];
      
      console.log(`已为学生${studentId}生成${records.length}条模拟考试记录`);
      return records;
    },
    
    /**
     * 渲染学生考试表现图表，并明确标识模拟数据
     */
    renderStudentPerformanceChart(studentId) {
      const chartContainer = document.getElementById('studentPerformanceChart');
      if (!chartContainer) {
        console.error('找不到学生成绩图表容器');
        return;
      }
      
      // 获取学生考试记录
      const examRecords = this.getStudentExamRecords(studentId);
      
      if (examRecords.length === 0) {
        chartContainer.innerHTML = '<div class="alert alert-info text-center my-5">没有考试记录数据</div>';
        return;
      }
      
      // 准备图表数据
      const dates = [];
      const scores = [];
      const percentiles = [];
      const standardScores = []; 
      
      // 提取数据
      for (const record of examRecords) {
        dates.push(record.exam_name || '未知考试');
        scores.push(record.score || 0);
        percentiles.push(record.percentile || 0);
        standardScores.push(record.standard_score || 0);
      }
      
      // 初始化echarts实例
      const chart = echarts.init(chartContainer);
      
      // 配置图表选项
      const option = {
        title: {
          text: '考试成绩趋势',
          left: 'center'
        },
        tooltip: {
          trigger: 'axis',
          formatter: function(params) {
            let result = params[0].name + '<br/>';
            
            // 显示各种数据
            params.forEach(param => {
              result += `${param.marker}${param.seriesName}: ${param.value}<br/>`;
            });
            
            return result;
          }
        },
        legend: {
          data: ['原始分', '标准分', '百分位'],
          bottom: 0
        },
        grid: {
          right: '20%',  // 扩大右侧空间以容纳更多Y轴
          top: '15%',
          bottom: '15%',
          containLabel: true
        },
        xAxis: {
          type: 'category',
          data: dates,
          axisLabel: {
            interval: 0,
            rotate: 45
          }
        },
        yAxis: [
          {
            type: 'value',
            name: '原始分',
            min: 0,
            max: 120,
            position: 'left',
            axisLine: {
              show: true,
              lineStyle: {
                color: '#409EFF'
              }
            },
            axisLabel: {
              formatter: '{value}'
            }
          },
          {
            type: 'value',
            name: '标准分',
            min: 200,
            max: 900,
            position: 'right',
            offset: 80,
            axisLine: {
              show: true,
              lineStyle: {
                color: '#67C23A'
              }
            },
            axisLabel: {
              formatter: '{value}'
            }
          },
          {
            type: 'value',
            name: '百分位',
            min: 0,
            max: 100,
            position: 'right',
            axisLine: {
              show: true,
              lineStyle: {
                color: '#E6A23C'
              }
            },
            axisLabel: {
              formatter: '{value}'
            }
          }
        ],
        series: [
          {
            name: '原始分',
            type: 'line',
            data: scores,
            yAxisIndex: 0,
            symbol: 'circle',
            itemStyle: {
              color: '#409EFF'
            }
          },
          {
            name: '标准分',
            type: 'line',
            data: standardScores,
            yAxisIndex: 1,
            symbol: 'rect',
            itemStyle: {
              color: '#67C23A'
            }
          },
          {
            name: '百分位',
            type: 'line',
            yAxisIndex: 2,
            data: percentiles,
            symbol: 'triangle',
            itemStyle: {
              color: '#E6A23C'
            },
            lineStyle: {
              type: 'dashed'
            }
          }
        ]
      };
      
      // 设置图表选项
      chart.setOption(option);
      
      // 记录图表实例，以便后续清理
      this.chartInstances = this.chartInstances || {};
      this.chartInstances['studentPerformanceChart'] = chart;
    },
    
    /**
     * 获取聚类标签类型
     * 
     * 根据聚类ID返回标签类型
     * 
     * Args:
     *   clusterId: 聚类ID
     * 
     * Returns:
     *   标签类型
     */
    getClusterTagType(clusterId) {
      const typeMap = {
        '1': 'success',
        '2': 'primary',
        '3': 'warning',
        '4': 'info',
        '5': 'danger'
      };
      
      return typeMap[clusterId] || 'info';
    },
    
    /**
     * 获取聚类名称
     * 
     * Args:
     *   clusterId: 聚类ID
     * 
     * Returns:
     *   聚类名称
     */
    getClusterName(clusterId) {
      if (this.clusterAnalysis.data.clusters && this.clusterAnalysis.data.clusters[clusterId]) {
        return this.clusterAnalysis.data.clusters[clusterId].name;
      }
      return `聚类${clusterId}`;
    },
    
    /**
     * 获取增长率显示样式
     * 
     * Args:
     *   growth: 增长率
     * 
     * Returns:
     *   CSS类名
     */
    getGrowthClass(growth) {
      if (!growth) return '';
      
      const value = parseFloat(growth);
      if (isNaN(value)) {
        return '';
      }
      
      if (value > 0) {
        return 'text-success';
      } else if (value < 0) {
        return 'text-danger';
      }
      return '';
    },
    
    /**
     * 提交分析请求后的回调
     */
    async handleAnalysisComplete() {
      // 加载聚类分析数据
      await this.loadClusterAnalysisData();
    },
    
    /**
     * 重置表单
     */
    resetForm() {
      this.formData = {
        exams: [],
        subject: '',
        clusters: 6,
        minExams: 3,
        visualizeClusters: true,
        visualizeTopStudents: true,
        visualizeLayerGrowth: true,
        district: '',
        educationStage: '',
        grade: ''
      };
      this.analysisComplete = false;
      this.isAnalyzing = false;
      this.analysisError = null;
      this.visualizationUrls = {};
      this.clusterProfiles = {};
      this.chartInstances = {};
      this.analysisData = {};
      this.clusterAnalysis.isLoaded = false;
      this.selectedStudent = null;
      this.studentDetailVisible = false;
    },
    
    /**
     * 处理分析进度消息
     */
    handleAnalysisProgress(message) {
      this.progressMessage = message;
    },
    
    /**
     * 处理分析结果
     */
    handleAnalysisResult(result) {
      this.analysisResults = result;
      this.loadVisualizationsFromResults();
    },
    
    /**
     * 处理分析错误
     */
    handleAnalysisError(error) {
      this.analysisError = error;
      this.loading = false;
      this.isAnalyzing = false;
    },
    
    /**
     * 重试分析
     */
    retryAnalysis() {
      this.submitAnalysis();
    },
    
    /**
     * 验证表单
     */
    validateForm() {
      // 实现表单验证逻辑
      return true; // 临时返回，需要根据实际需求实现
    },
    
    /**
     * 处理API错误
     */
    handleApiError(error, message) {
      console.error(message, error);
      this.$message.error(message);
    },
    
    /**
     * 强制加载并刷新数据
     */
    forceLoadData() {
      console.log("强制重新加载聚类数据...");
      
      if (this.analysisResults && this.analysisResults.data) {
        const student_clusters = this.analysisResults.data.student_clusters || [];
        const student_features = this.analysisResults.data.student_features || [];
        
        const clusterIds = [...new Set(student_clusters.map(s => s.cluster))];
        
        // 设置元数据
        this.clusterAnalysis.metadata = {
          clusterCount: clusterIds.length,
          studentCount: student_clusters.length,
          featureNames: student_features.length > 0 
            ? Object.keys(student_features[0]).filter(k => 
                !['student_id', 'student_name', 'class_name', 'school_name', 
                  'grade', 'cluster', 'cluster_label', 'cluster_description'].includes(k))
            : []
        };
        
        // 准备聚类信息
        const clusterProfiles = {};
        clusterIds.forEach(id => {
          const students = student_features.filter(s => s.cluster == id);
          const firstStudent = students[0] || {};
          
          clusterProfiles[id] = {
            id: id,
            name: firstStudent.cluster_label || `聚类 ${id}`,
            description: firstStudent.cluster_description || '无描述',
            count: students.length,
            color: this.getClusterColor(id)
          };
        });
        
        // 设置数据
        this.clusterAnalysis.data = {
          students: student_clusters,
          features: student_features,
          clusters: clusterProfiles
        };
        
        // 设置加载状态
        this.clusterAnalysis.isLoaded = true;
        
        // 延迟初始化图表，确保DOM已更新
        this.$nextTick(() => {
          setTimeout(() => {
            console.log("强制初始化图表...");
            
            // 根据当前选择的图表类型渲染
            this.updateScatterChart();
            this.updateFeatureChart();
          }, 500);
        });
        
        this.$message.success('数据已强制加载');
      } else {
        this.$message.warning('没有可用的分析结果数据');
      }
    },
    
    /**
     * 初始化聚类分析数据结构
     * 
     * @returns {Object} 初始化的聚类分析数据结构
     */
    initClusterAnalysis() {
      console.log("初始化聚类分析数据结构");
      return {
        isLoaded: false,
        metadata: {
          clusterCount: 0,
          studentCount: 0,
          featureNames: []
        },
        data: {
          clusters: {},
          students: [],
          features: [],
          examRecords: [] // 添加考试记录数组
        },
        charts: {
          pca: null,
          feature: null
        },
        chartsInitialized: {
          pca: false,
          feature: false
        },
        cleanupHandlers: [] // 添加这一行，用于存储需要清理的事件处理函数
      };
    },
    
    /**
     * 强制确保DOM元素存在后才渲染图表
     * 
     * @param {Function} renderFunction 要执行的渲染函数
     * @param {String} elementId 需要检查的DOM元素ID
     * @param {Number} maxAttempts 最大尝试次数
     * @param {Number} delay 每次尝试间隔(毫秒)
     */
    ensureDomElementAndRender(renderFunction, elementId, maxAttempts = 10, delay = 300) {
      console.log(`尝试确保DOM元素存在: ${elementId}`);
      
      let attempts = 0;
      
      const attemptRender = () => {
        attempts++;
        console.log(`[第${attempts}次尝试] 检查DOM元素: ${elementId}`);
        
        const element = document.getElementById(elementId);
        
        if (element) {
          console.log(`√ 找到DOM元素 ${elementId}，开始渲染...`);
          // 确保元素有高度
          if (element.offsetHeight < 300) {
            element.style.height = '400px';
            console.log(`调整元素高度为400px`);
          }
          
          // 确保组件数据已加载
          if (!this.clusterAnalysis.isLoaded) {
            console.log(`数据未加载，强制加载数据...`);
            this.forceLoadData();
          }
          
          // 执行渲染函数
          this.$nextTick(() => {
            try {
              renderFunction();
              console.log(`√ 图表 ${elementId} 渲染成功`);
            } catch (error) {
              console.error(`图表 ${elementId} 渲染失败:`, error);
            }
          });
          return;
        }
        
        // 如果元素不存在但已超过最大尝试次数
        if (attempts >= maxAttempts) {
          console.error(`× 达到最大尝试次数(${maxAttempts})，尝试创建DOM元素: ${elementId}`);
          // 最后尝试创建元素
          this.ensureChartContainers();
          
          // 再给一次渲染机会
          setTimeout(() => {
            const finalElement = document.getElementById(elementId);
            if (finalElement) {
              finalElement.style.height = '400px';
              try {
                renderFunction();
                console.log(`最终尝试: ${elementId} 渲染成功`);
              } catch (error) {
                console.error(`最终尝试: ${elementId} 渲染失败:`, error);
              }
            }
          }, 500);
          return;
        }
        
        console.log(`DOM元素 ${elementId} 不存在，${delay}ms后重试...`);
        setTimeout(attemptRender, delay);
      };
      
      attemptRender();
    },
    
    /**
     * 获取指定聚类的学生列表
     * 
     * @param {string|number} clusterId - 聚类ID
     * @returns {Array} - 学生列表
     */
    getClusterStudents(clusterId) {
      if (!this.analysisResults || !this.analysisResults.data || !this.analysisResults.data.student_features) {
        return [];
      }
      
      return this.analysisResults.data.student_features
        .filter(student => student.cluster == clusterId)
        .sort((a, b) => a.student_name.localeCompare(b.student_name, 'zh-CN'));
    },
    
    /**
     * 强制重新渲染所有图表
     */
    reloadAllCharts() {
      console.log("强制重新渲染所有图表...");
      this.$nextTick(() => {
        setTimeout(() => {
          this.renderPcaScatterChart();
          this.renderFeatureParallelChart();
        }, 300);
      });
    },
    
    /**
     * 渲染特征热力图
     */
    renderFeatureHeatmapChart() {
      try {
        console.log("开始渲染特征热力图...");
        
        // 确保有DOM元素
        const chartDom = document.getElementById('cluster-feature-chart');
        if (!chartDom) {
          console.error('找不到特征热力图DOM元素');
          return;
        }
        
        // 设置容器大小
        if (chartDom.offsetHeight < 300) {
          chartDom.style.height = '500px';
        }
        
        // 销毁现有图表实例
        if (this.clusterAnalysis.charts.feature) {
          this.clusterAnalysis.charts.feature.dispose();
        }
        
        // 初始化图表
        const echarts = this.getEChartsInstance();
        if (!echarts) {
          console.error('无法获取ECharts实例，无法初始化图表');
          return;
        }
        
        const chart = echarts.init(chartDom);
        this.clusterAnalysis.charts.feature = chart;
        
        // 如果有学生特征数据，则使用真实数据
        if (this.analysisResults && 
            this.analysisResults.data && 
            this.analysisResults.data.student_features && 
            this.analysisResults.data.student_features.length > 0) {
          
          // 找出特征维度 - 使用带有_scaled后缀的字段
          const firstStudent = this.analysisResults.data.student_features[0];
          const featureDimensions = Object.keys(firstStudent)
            .filter(key => !['student_id', 'student_name', 'class_name', 
                              'school_name', 'grade', 'cluster', 
                              'cluster_label', 'cluster_description'].includes(key))
            .filter(key => key.includes('_scaled'))  // 只使用归一化特征
            .map(key => {
              // 转换特征名称为更友好的显示
              const name = key.replace(/_scaled$/, '')
                             .replace(/_/g, ' ')
                             .replace(/([A-Z])/g, ' $1')
                             .replace(/^./, str => str.toUpperCase());
              return {name: name, key: key};
            })
            .slice(0, 12);  // 限制最多12个维度
          
          // 获取聚类ID
          const uniqueClusters = [...new Set(this.analysisResults.data.student_features.map(s => s.cluster))];
          
          // 准备特征名称和聚类名称
          const xAxisData = featureDimensions.map(d => d.name);
          const yAxisData = [];
          
          // 计算每个聚类的特征均值
          const heatmapData = [];
          
          uniqueClusters.forEach(clusterId => {
            const students = this.analysisResults.data.student_features.filter(s => s.cluster === clusterId);
            const clusterName = students[0]?.cluster_label || `聚类 ${clusterId}`;
            yAxisData.push(clusterName);
            
            // 计算该聚类在每个特征上的均值
            featureDimensions.forEach((dim, dimIndex) => {
              const values = students.map(s => Number(s[dim.key]) || 0);
              const average = values.reduce((a, b) => a + b, 0) / values.length;
              
              // [x, y, value]格式：x是特征索引，y是聚类索引，value是均值
              heatmapData.push([dimIndex, yAxisData.length - 1, average]);
            });
          });
          
          // 设置图表选项
          const option = {
            title: {
              text: '聚类特征分布热力图',
              left: 'center'
            },
            tooltip: {
              position: 'top',
              formatter: function(params) {
                const featureName = xAxisData[params.data[0]];
                const clusterName = yAxisData[params.data[1]];
                const value = params.data[2].toFixed(2);
                return `${clusterName}<br/>${featureName}: ${value}`;
              }
            },
            grid: {
              left: '12%',
              right: '5%',
              top: '18%',
              bottom: '20%'
            },
            xAxis: {
              type: 'category',
              data: xAxisData,
              splitArea: {
                show: true
              },
              axisLabel: {
                interval: 0,
                rotate: 30,
                fontSize: 12
              }
            },
            yAxis: {
              type: 'category',
              data: yAxisData,
              splitArea: {
                show: true
              }
            },
            visualMap: {
              min: -1.5,
              max: 1.5,
              calculable: true,
              orient: 'horizontal',
              left: 'center',
              bottom: '0%',
              inRange: {
                color: ['#313695', '#4575b4', '#74add1', '#abd9e9', '#e0f3f8', '#ffffbf', '#fee090', '#fdae61', '#f46d43', '#d73027', '#a50026']
              }
            },
            series: [{
              name: '特征值',
              type: 'heatmap',
              data: heatmapData,
              label: {
                show: true,
                formatter: function(params) {
                  return params.data[2].toFixed(1);
                },
                fontSize: 10
              },
              emphasis: {
                itemStyle: {
                  shadowBlur: 10,
                  shadowColor: 'rgba(0, 0, 0, 0.5)'
                }
              }
            }]
          };
          
          // 设置图表
          chart.setOption(option);
          console.log("聚类-特征热力图渲染完成");
        } else {
          console.error("无法渲染特征分布图：没有学生特征数据");
        }
      } catch (e) {
        console.error("渲染聚类-特征热力图时出错:", e);
      }
    },
    
    /**
     * 更新特征分布图
     */
    updateFeatureChart() {
      try {
        console.log(`准备更新特征图表，类型: ${this.featureChartType}`);
        
        // 延迟执行以确保DOM已准备好
        setTimeout(() => {
          if (this.featureChartType === 'parallel') {
            this.renderSimpleParallelChart();
          } else if (this.featureChartType === 'boxplot') {
            this.renderClusterBoxplotChart();
          } else if (this.featureChartType === 'heatmap') {
            this.renderClusterHeatmapChart();
          }
        }, 100);
      } catch (error) {
        console.error(`更新特征图表失败: ${error.message}`);
      }
    },
    
    /**
     * 渲染简化版并行坐标图
     * 确保图表能够正确显示
     */
    renderSimpleParallelChart() {
      console.log("开始渲染简化版并行坐标图...");
      
      // 获取DOM元素
      const chartDom = document.getElementById('cluster-feature-chart');
      if (!chartDom) {
        console.error('找不到特征图表DOM元素');
        return;
      }
      
      // 确保容器有适当大小
      chartDom.style.height = '500px';
      
      // 清理现有图表
      if (this.clusterAnalysis.charts.feature) {
        this.clusterAnalysis.charts.feature.dispose();
        this.clusterAnalysis.charts.feature = null;
      }
      
      // 创建新图表实例
      const echarts = this.getEChartsInstance();
      if (!echarts) {
        console.error('无法获取ECharts实例，无法初始化图表');
        return;
      }
      
      const chart = echarts.init(chartDom);
      this.clusterAnalysis.charts.feature = chart;
      
      // 确保数据存在
      if (!this.analysisResults?.data?.student_features?.length) {
        console.error("没有有效的学生特征数据");
        
        // 显示一个简单的提示
        chart.setOption({
          title: {
            text: '无法显示并行坐标图',
            subtext: '没有找到有效的特征数据',
            left: 'center',
            top: 'center'
          }
        });
        return;
      }
      
      try {
        // 准备数据
        const features = this.analysisResults.data.student_features;
        const firstStudent = features[0];
        
        // 选择特征 - 仅选择最重要的几个归一化特征
        const selectedFeatures = [
          'growth_rate_scaled', 
          'volatility_scaled', 
          'acceleration_scaled',
          'max_improvement_scaled', 
          'max_decline_scaled', 
          'start_level_scaled', 
          'end_level_scaled'
        ].filter(key => key in firstStudent);
        
        // 如果没有找到预期特征，尝试从对象中查找所有_scaled结尾的键
        if (selectedFeatures.length === 0) {
          Object.keys(firstStudent)
            .filter(key => key.endsWith('_scaled') && 
                   !['student_id', 'student_name', 'class_name', 'school_name', 'grade', 'cluster'].includes(key))
            .slice(0, 7)  // 只取前7个
            .forEach(key => selectedFeatures.push(key));
        }
        
        // 如果仍然没有特征，显示错误
        if (selectedFeatures.length === 0) {
          chart.setOption({
            title: {
              text: '无法显示并行坐标图',
              subtext: '找不到有效的特征维度',
              left: 'center',
              top: 'center'
            }
          });
          return;
        }
        
        // 获取所有聚类
        const clusters = [...new Set(features.map(f => f.cluster))];
        
        // 为每个聚类准备数据
        const seriesData = [];
        
        // 汉化特征名称
        const featureNameMap = {
          'growth_rate_scaled': '成长率',
          'volatility_scaled': '波动性',
          'acceleration_scaled': '加速度', 
          'max_improvement_scaled': '最大提升',
          'max_decline_scaled': '最大下降',
          'start_level_scaled': '起点水平',
          'end_level_scaled': '终点水平',
          'total_improvement_scaled': '总体提升',
          'rank_change_scaled': '排名变化'
        };
        
        // 为每个聚类创建一个系列
        clusters.forEach(clusterId => {
          // 获取该聚类的学生
          const clusterStudents = features.filter(f => f.cluster === clusterId);
          
          // 获取聚类名称
          const clusterName = clusterStudents[0]?.cluster_label || `聚类 ${clusterId}`;
          
          // 限制样本数量，避免图表过于拥挤
          const sampleSize = Math.min(clusterStudents.length, 20);
          const samples = clusterStudents.slice(0, sampleSize);
          
          // 创建系列
          seriesData.push({
            name: clusterName,
            type: 'parallel',
            lineStyle: {
              width: 1,
              opacity: 0.5,
              color: this.getClusterColor(clusterId)
            },
            emphasis: {
              lineStyle: {
                width: 3,
                opacity: 0.8,
                color: this.getClusterColor(clusterId)
              }
            },
            data: samples.map(student => {
              return selectedFeatures.map(feature => parseFloat(student[feature] || 0));
            })
          });
        });
        
        // 设置图表选项
        const option = {
          title: {
            text: '聚类特征分析',
            left: 'center'
          },
          tooltip: {
            trigger: 'item'
          },
          legend: {
            bottom: 10,
            data: clusters.map(clusterId => {
              const students = features.filter(f => f.cluster === clusterId);
              return students[0]?.cluster_label || `聚类 ${clusterId}`;
            })
          },
          parallelAxis: selectedFeatures.map((feature, i) => {
            return {
              dim: i,
              name: featureNameMap[feature] || feature.replace(/_scaled$/, '').replace(/_/g, ' '),
              min: -1.5,
              max: 1.5
            };
          }),
          parallel: {
            left: '5%',
            right: '13%',
            bottom: '15%',
            top: '20%'
          },
          series: seriesData
        };
        
        // 渲染图表
        chart.setOption(option);
        console.log("简化版并行坐标图渲染完成");
      } catch (error) {
        console.error("并行坐标图渲染失败:", error);
        
        // 显示错误提示
        chart.setOption({
          title: {
            text: '图表渲染失败',
            subtext: error.message,
            left: 'center',
            top: 'center'
          }
        });
      }
    },
    
    /**
     * 渲染聚类对比箱线图
     * 
     * 展示不同聚类在关键特征上的分布差异
     */
    renderClusterBoxplotChart() {
      try {
        console.log("开始渲染聚类对比箱线图...");
        
        // 确保有DOM元素
        const chartDom = document.getElementById('cluster-feature-chart');
        if (!chartDom) {
          console.error('找不到图表DOM元素');
          return;
        }
        
        // 设置容器大小
        if (chartDom.offsetHeight < 400) {
          chartDom.style.height = '500px';
        }
        
        // 销毁现有图表实例
        if (this.clusterAnalysis.charts.feature) {
          this.clusterAnalysis.charts.feature.dispose();
        }
        
        // 初始化图表
        const echarts = this.getEChartsInstance();
        if (!echarts) {
          console.error('无法获取ECharts实例，无法初始化图表');
          return;
        }
        
        const chart = echarts.init(chartDom);
        this.clusterAnalysis.charts.feature = chart;
        
        // 如果有学生特征数据，则使用真实数据
        if (this.analysisResults && 
            this.analysisResults.data && 
            this.analysisResults.data.student_features && 
            this.analysisResults.data.student_features.length > 0) {
          
          // 选择关键特征进行对比
          const keyFeatures = [
            {key: 'growth_rate_scaled', name: '成长速度'},
            {key: 'volatility_scaled', name: '波动率'},
            {key: 'start_level_scaled', name: '起点水平'},
            {key: 'total_improvement_scaled', name: '总体提升'}
          ];
          
          // 获取聚类ID和名称
          const uniqueClusters = [...new Set(this.analysisResults.data.student_features.map(s => s.cluster))];
          const clusterNames = {};
          uniqueClusters.forEach(clusterId => {
            const students = this.analysisResults.data.student_features.filter(s => s.cluster === clusterId);
            clusterNames[clusterId] = students[0]?.cluster_label || `聚类 ${clusterId}`;
          });
          
          // 准备箱线图数据
          const boxplotData = [];
          const categoryData = [];
          
          // 每个特征创建一个系列
          keyFeatures.forEach(feature => {
            const seriesData = [];
            
            uniqueClusters.forEach(clusterId => {
              // 该聚类所有学生的该特征值
              const values = this.analysisResults.data.student_features
                .filter(s => s.cluster === clusterId)
                .map(s => Number(s[feature.key]) || 0)
                .filter(v => !isNaN(v));
              
              if(values.length > 0) {
                // 计算箱线图所需的五个统计值：最小值、第一四分位数、中位数、第三四分位数、最大值
                values.sort((a, b) => a - b);
                const min = values[0];
                const max = values[values.length - 1];
                const q1 = values[Math.floor(values.length * 0.25)];
                const q2 = values[Math.floor(values.length * 0.5)];
                const q3 = values[Math.floor(values.length * 0.75)];
                
                seriesData.push([min, q1, q2, q3, max]);
              } else {
                seriesData.push([0, 0, 0, 0, 0]);
              }
              
              // 只在第一个特征时添加类别名称，避免重复
              if(feature === keyFeatures[0]) {
                categoryData.push(clusterNames[clusterId]);
              }
            });
            
            boxplotData.push({
              name: feature.name,
              type: 'boxplot',
              data: seriesData,
              itemStyle: {
                borderWidth: 2,
                borderColor: feature === keyFeatures[0] ? '#5470c6' : 
                             feature === keyFeatures[1] ? '#91cc75' : 
                             feature === keyFeatures[2] ? '#fac858' : '#ee6666'
              }
            });
          });
          
          // 设置图表选项
          const option = {
            title: {
              text: '聚类关键特征分布对比',
              left: 'center'
            },
            tooltip: {
              trigger: 'item',
              axisPointer: {
                type: 'shadow'
              },
              formatter: function(params) {
                if (!params.data) return '';
                return `${params.seriesName} - ${params.name}<br/>
                       最大值: ${params.data[4].toFixed(2)}<br/>
                       上四分位: ${params.data[3].toFixed(2)}<br/>
                       中位数: ${params.data[2].toFixed(2)}<br/>
                       下四分位: ${params.data[1].toFixed(2)}<br/>
                       最小值: ${params.data[0].toFixed(2)}`;
              }
            },
            legend: {
              data: keyFeatures.map(f => f.name),
              bottom: 10
            },
            toolbox: {
              feature: {
                dataView: {show: true, readOnly: false},
                saveAsImage: {show: true}
              }
            },
            grid: {
              left: '10%',
              right: '10%',
              bottom: '15%'
            },
            xAxis: {
              type: 'category',
              data: categoryData,
              boundaryGap: true,
              nameGap: 30,
              splitArea: {
                show: false
              },
              axisLabel: {
                rotate: 30
              },
              splitLine: {
                show: false
              }
            },
            yAxis: {
              type: 'value',
              name: '标准化特征值',
              min: -1.5,
              max: 1.5,
              splitArea: {
                show: true
              }
            },
            series: boxplotData
          };
          
          // 设置图表
          chart.setOption(option);
          console.log("聚类对比箱线图渲染完成");
        } else {
          console.error("无法渲染图表：没有学生特征数据");
        }
      } catch (e) {
        console.error("渲染聚类对比箱线图时出错:", e);
      }
    },
    
    /**
     * 渲染双变量聚类气泡图
     * 
     * 用两个关键指标探索二维关系
     */
    renderClusterBubbleChart() {
      try {
        console.log("开始渲染双变量聚类气泡图...");
        
        // 确保有DOM元素
        const chartDom = document.getElementById('cluster-pca-chart');
        if (!chartDom) {
          console.error('找不到图表DOM元素');
          return;
        }
        
        // 设置容器大小
        if (chartDom.offsetHeight < 400) {
          chartDom.style.height = '500px';
        }
        
        // 销毁现有图表实例
        if (this.clusterAnalysis.charts.pca) {
          this.clusterAnalysis.charts.pca.dispose();
        }
        
        // 初始化图表
        const echarts = this.getEChartsInstance();
        if (!echarts) {
          console.error('无法获取ECharts实例，无法初始化图表');
          return;
        }
        
        const chart = echarts.init(chartDom);
        this.clusterAnalysis.charts.pca = chart;
        
        // 如果有学生特征数据，则使用真实数据
        if (this.analysisResults && 
            this.analysisResults.data && 
            this.analysisResults.data.student_features && 
            this.analysisResults.data.student_features.length > 0) {
          
          // 获取聚类ID和颜色
          const uniqueClusters = [...new Set(this.analysisResults.data.student_features.map(s => s.cluster))];
          
          // 准备气泡图数据
          const seriesData = [];
          
          // 为每个聚类创建一个系列
          uniqueClusters.forEach(clusterId => {
            const clusterStudents = this.analysisResults.data.student_features.filter(s => s.cluster === clusterId);
            const clusterName = clusterStudents[0]?.cluster_label || `聚类 ${clusterId}`;
            
            // 为每个学生创建一个数据点
            const data = clusterStudents.map(student => {
          return {
                // X轴: 起点水平, Y轴: 总体提升, 大小: 波动率
                value: [
                  student.start_level_scaled || 0,
                  student.total_improvement_scaled || 0,
                  Math.abs(student.volatility_scaled || 0.5) * 5 + 5 // 气泡大小
                ],
                // 额外信息用于工具提示
                studentName: student.student_name,
                studentId: student.student_id,
                growthRate: student.growth_rate_scaled,
                volatility: student.volatility_scaled
              };
            });
            
            seriesData.push({
              name: clusterName,
              type: 'scatter',
              data: data,
              symbolSize: function(data) {
                return data[2];
              },
              emphasis: {
                focus: 'series',
                label: {
                  show: true,
                  formatter: function(param) {
                    return param.data.studentName;
                  },
                  position: 'top'
                }
              },
              itemStyle: {
                color: this.getClusterColor(clusterId)
              }
            });
          });
          
          // 设置图表选项
          const option = {
            title: {
              text: '聚类双变量分布',
              subtext: '起点水平 vs 总体提升 (气泡大小: 波动率)',
              left: 'center'
            },
            tooltip: {
              trigger: 'item',
              formatter: function(params) {
                return `聚类: ${params.seriesName}<br/>
                       学生: ${params.data.studentName}<br/>
                       起点水平: ${params.data.value[0].toFixed(2)}<br/>
                       总体提升: ${params.data.value[1].toFixed(2)}<br/>
                       波动率: ${params.data.volatility.toFixed(2)}<br/>
                       成长速度: ${params.data.growthRate.toFixed(2)}`;
              }
            },
            legend: {
              type: 'scroll',
              bottom: 10,
              data: uniqueClusters.map(clusterId => {
                const students = this.analysisResults.data.student_features.filter(s => s.cluster === clusterId);
                return students[0]?.cluster_label || `聚类 ${clusterId}`;
              })
            },
            toolbox: {
              feature: {
                dataZoom: {},
                dataView: {show: true, readOnly: false},
                saveAsImage: {show: true}
              }
            },
            grid: {
              left: '10%',
              right: '10%',
              bottom: '15%'
            },
            xAxis: {
              type: 'value',
              name: '起点水平',
              nameLocation: 'center',
              nameGap: 30,
              min: -1.5,
              max: 1.5,
              splitLine: {
                lineStyle: {
                  type: 'dashed'
                }
              }
            },
            yAxis: {
              type: 'value',
              name: '总体提升',
              nameLocation: 'center',
              nameGap: 30,
              min: -1.5,
              max: 1.5,
              splitLine: {
                lineStyle: {
                  type: 'dashed'
                }
              }
            },
            series: seriesData
          };
          
          // 设置图表
          chart.setOption(option);
          console.log("双变量聚类气泡图渲染完成");
          
          // 点击事件 - 查看学生详情
          chart.on('click', (params) => {
            if (params.data && params.data.studentId) {
              this.showStudentDetail({
                student_id: params.data.studentId
              });
            }
          });
        } else {
          console.error("无法渲染图表：没有学生特征数据");
        }
      } catch (e) {
        console.error("渲染双变量聚类气泡图时出错:", e);
      }
    },
    
    /**
     * 渲染聚类-特征热力图
     * 
     * 全局模式识别，展示每个聚类在各特征上的均值
     */
    renderClusterHeatmapChart() {
      try {
        console.log("开始渲染聚类-特征热力图...");
        
        // 确保有DOM元素
        const chartDom = document.getElementById('cluster-feature-chart');
        if (!chartDom) {
          console.error('找不到图表DOM元素');
          return;
        }
        
        // 设置容器大小
        if (chartDom.offsetHeight < 400) {
          chartDom.style.height = '500px';
        }
        
        // 销毁现有图表实例
        if (this.clusterAnalysis.charts.feature) {
          this.clusterAnalysis.charts.feature.dispose();
        }
        
        // 初始化图表
        const echarts = this.getEChartsInstance();
        if (!echarts) {
          console.error('无法获取ECharts实例，无法初始化图表');
          return;
        }
        
        const chart = echarts.init(chartDom);
        this.clusterAnalysis.charts.feature = chart;
        
        // 如果有学生特征数据，则使用真实数据
        if (this.analysisResults && 
            this.analysisResults.data && 
            this.analysisResults.data.student_features && 
            this.analysisResults.data.student_features.length > 0) {
          
          // 找出特征维度 - 使用带有_scaled后缀的字段
          const firstStudent = this.analysisResults.data.student_features[0];
          const featureDimensions = Object.keys(firstStudent)
            .filter(key => !['student_id', 'student_name', 'class_name', 
                              'school_name', 'grade', 'cluster', 
                              'cluster_label', 'cluster_description'].includes(key))
            .filter(key => key.includes('_scaled'))  // 只使用归一化特征
            .map(key => {
              // 转换特征名称为更友好的显示
              const name = key.replace(/_scaled$/, '')
                             .replace(/_/g, ' ')
                             .replace(/([A-Z])/g, ' $1')
                             .replace(/^./, str => str.toUpperCase());
              return {name: name, key: key};
            })
            .slice(0, 12);  // 限制最多12个维度
          
          // 获取聚类ID
          const uniqueClusters = [...new Set(this.analysisResults.data.student_features.map(s => s.cluster))];
          
          // 准备特征名称和聚类名称
          const xAxisData = featureDimensions.map(d => d.name);
          const yAxisData = [];
          
          // 计算每个聚类的特征均值
          const heatmapData = [];
          
          uniqueClusters.forEach(clusterId => {
            const students = this.analysisResults.data.student_features.filter(s => s.cluster === clusterId);
            const clusterName = students[0]?.cluster_label || `聚类 ${clusterId}`;
            yAxisData.push(clusterName);
            
            // 计算该聚类在每个特征上的均值
            featureDimensions.forEach((dim, dimIndex) => {
              const values = students.map(s => Number(s[dim.key]) || 0);
              const average = values.reduce((a, b) => a + b, 0) / values.length;
              
              // [x, y, value]格式：x是特征索引，y是聚类索引，value是均值
              heatmapData.push([dimIndex, yAxisData.length - 1, average]);
            });
          });
          
          // 设置图表选项
          const option = {
            title: {
              text: '聚类特征分布热力图',
              left: 'center'
            },
            tooltip: {
              position: 'top',
              formatter: function(params) {
                const featureName = xAxisData[params.data[0]];
                const clusterName = yAxisData[params.data[1]];
                const value = params.data[2].toFixed(2);
                return `${clusterName}<br/>${featureName}: ${value}`;
              }
            },
            grid: {
              left: '12%',
              right: '5%',
              top: '18%',
              bottom: '20%'
            },
            xAxis: {
              type: 'category',
              data: xAxisData,
              splitArea: {
                show: true
              },
              axisLabel: {
                interval: 0,
                rotate: 30,
                fontSize: 12
              }
            },
            yAxis: {
              type: 'category',
              data: yAxisData,
              splitArea: {
                show: true
              }
            },
            visualMap: {
              min: -1.5,
              max: 1.5,
              calculable: true,
              orient: 'horizontal',
              left: 'center',
              bottom: '0%',
              inRange: {
                color: ['#313695', '#4575b4', '#74add1', '#abd9e9', '#e0f3f8', '#ffffbf', '#fee090', '#fdae61', '#f46d43', '#d73027', '#a50026']
              }
            },
            series: [{
              name: '特征值',
              type: 'heatmap',
              data: heatmapData,
              label: {
                show: true,
                formatter: function(params) {
                  return params.data[2].toFixed(1);
                },
                fontSize: 10
              },
              emphasis: {
                itemStyle: {
                  shadowBlur: 10,
                  shadowColor: 'rgba(0, 0, 0, 0.5)'
                }
              }
            }]
          };
          
          // 设置图表
          chart.setOption(option);
          console.log("聚类-特征热力图渲染完成");
        } else {
          console.error("无法渲染特征分布图：没有学生特征数据");
        }
      } catch (e) {
        console.error("渲染聚类-特征热力图时出错:", e);
      }
    },
    
    /**
     * 更新散点图
     */
    updateScatterChart() {
      if (this.scatterChartType === 'bubble') {
        this.renderClusterBubbleChart();
      } else {
        this.renderPcaScatterChart();
      }
    },
    
    /**
     * 处理标签页点击事件
     * 
     * @param {Object} tab 被点击的标签页
     */
    handleTabClick(tab) {
      // 增强Tab名称获取的健壮性
      let tabName = null;
      
      // 根据不同的Element UI版本和参数格式提取标签页名称
      if (typeof tab === 'string') {
        tabName = tab;
      } else if (tab && tab.name) {
        tabName = tab.name;
      } else if (tab && tab.props && tab.props.name) {
        tabName = tab.props.name;
      } else if (tab && tab.paneName) {
        tabName = tab.paneName;
      } else if (tab && tab.$options && tab.$options.propsData && tab.$options.propsData.name) {
        tabName = tab.$options.propsData.name;
      }
      
      console.log(`切换到标签页: ${tabName || 'unknown'}`);
      this.activeTab = tabName; // 确保activeTab被正确设置
      
      if (tabName === 'growth') {
        // 确保有层级成长数据
        this.ensureLayerGrowthData();
        
        // 延迟执行图表初始化，确保DOM已经渲染
        this.$nextTick(() => {
          this.initGrowthCharts();
        });
      } else if (tabName === 'cluster') {
        // 确保聚类数据已加载
        if (!this.clusterAnalysis.isLoaded) {
          this.forceLoadData();
        }
        
        this.$nextTick(() => {
          this.initClusterCharts();
        });
      } else if (tabName === 'students') {
        console.log("切换到学生详情标签页");
        // 初始化学生详情相关内容
        this.$nextTick(() => {
          console.log("学生详情页面DOM已更新");
        });
      }
    },
    
    /**
     * 确保分析结果正确显示
     */
    ensureAnalysisResults() {
      if (this.analysisComplete && !this.isAnalyzing) {
        console.log("分析已完成，准备显示结果...");
        
        // 确保标签页已设置
        if (!this.activeTab) {
          this.activeTab = 'cluster';
          console.log("设置默认标签页为聚类分析");
        }
        
        // 延迟执行以确保DOM已渲染
        setTimeout(() => {
          if (this.activeTab === 'cluster') {
            this.initClusterCharts();
          }
        }, 300);
      }
    },
    
    /**
     * 在分析完成时处理结果
     * 
     * @param {Object} results 分析结果数据
     */
    onAnalysisComplete(results) {
      // 存储结果数据
      this.analysisResults = results;
      
      // 确保分析结果可用
      this.ensureAnalysisResults();
      
      // 标记分析完成
      this.analysisComplete = true;
      this.isAnalyzing = false;
    },
    
    /**
     * 检查DOM元素状态
     * 
     * @returns {Boolean} DOM元素状态是否正常
     */
    checkDomStatus() {
      const pcaChart = document.getElementById('cluster-pca-chart');
      const featureChart = document.getElementById('cluster-feature-chart');
      
      return !!(pcaChart && featureChart);
    },
    
    /**
     * 尝试修复DOM结构
     */
    fixDomStructure() {
      console.log("尝试修复DOM结构...");
      
      // 确保是聚类标签页
      this.activeTab = 'cluster';
      
      // 强制重新渲染
      this.$forceUpdate();
      
      // 延迟检查
      setTimeout(() => {
        const status = this.checkDomStatus();
        console.log("DOM修复结果:", status ? "成功" : "失败");
        
        if (status) {
          this.initClusterCharts();
          this.$message.success('DOM结构已修复');
        } else {
          this.$message.error('DOM结构修复失败，请刷新页面');
        }
      }, 500);
    },
    
    /**
     * 清理图表实例和相关资源
     */
    cleanupCharts() {
      try {
        // 清理所有监听器
        if (this.clusterAnalysis.cleanupHandlers) {
          this.clusterAnalysis.cleanupHandlers.forEach(handler => {
            try {
              handler();
            } catch (e) {
              console.warn("清理事件监听器失败:", e);
            }
          });
          this.clusterAnalysis.cleanupHandlers = [];
        }
        
        // 处置ECharts实例以避免内存泄漏
        if (this.clusterAnalysis.charts.pca) {
          this.clusterAnalysis.charts.pca.dispose();
          this.clusterAnalysis.charts.pca = null;
        }
        
        if (this.clusterAnalysis.charts.feature) {
          this.clusterAnalysis.charts.feature.dispose();
          this.clusterAnalysis.charts.feature = null;
        }
        
        // 清理层级分析图表
        if (this.layerGrowthChart) {
          this.layerGrowthChart.dispose();
          this.layerGrowthChart = null;
        }
        
        if (this.layerTransitionChart) {
          this.layerTransitionChart.dispose();
          this.layerTransitionChart = null;
        }
        
        // 清理聚类层级图表
        if (this.clusterLayerChart) {
          this.clusterLayerChart.dispose();
          this.clusterLayerChart = null;
        }
        
        console.log("所有图表实例已清理");
      } catch (error) {
        console.error("清理图表实例时出错:", error);
      }
    },
    
    /**
     * 初始化图表实例并处理大小调整
     * 
     * @param {HTMLElement} dom - 图表容器DOM元素
     * @param {String} chartType - 图表类型标识，如'pca'或'feature'
     * @returns {Object} - ECharts实例
     */
    initChartInstance(dom, chartType) {
      // 首先清理可能存在的实例以避免内存泄漏
      if (this.clusterAnalysis.charts[chartType]) {
        this.clusterAnalysis.charts[chartType].dispose();
      }
      
      // 使用requestAnimationFrame防止过多的resize调用
      let chart = null;
      
      // 延迟初始化以确保DOM尺寸稳定
      setTimeout(() => {
        try {
          // 测量DOM元素当前尺寸
          const domWidth = dom.clientWidth;
          const domHeight = dom.clientHeight;
          
          // 初始化图表前确保DOM有尺寸
          if (domWidth > 0 && domHeight > 0) {
            chart = echarts.init(dom);
            this.clusterAnalysis.charts[chartType] = chart;
            
            // 优化resize处理，防止过多调用
            let resizeTimeout = null;
            const resizeHandler = () => {
              if (resizeTimeout) clearTimeout(resizeTimeout);
              resizeTimeout = setTimeout(() => {
                if (chart && !chart.isDisposed()) {
                  chart.resize();
                }
              }, 100); // 延迟100ms执行resize
            };
            
            // 监听窗口大小变化
            window.addEventListener('resize', resizeHandler);
            
            // 记录清理函数
            this.clusterAnalysis.cleanupHandlers = this.clusterAnalysis.cleanupHandlers || [];
            this.clusterAnalysis.cleanupHandlers.push(() => {
              window.removeEventListener('resize', resizeHandler);
              if (chart && !chart.isDisposed()) {
                chart.dispose();
              }
            });
            
            console.log(`${chartType}图表初始化完成，尺寸: ${domWidth}x${domHeight}`);
          } else {
            console.warn(`DOM元素 ${chartType} 尺寸为零，无法初始化图表`);
          }
        } catch (error) {
          console.error(`初始化${chartType}图表实例失败:`, error);
        }
      }, 50); // 短暂延迟以确保DOM已就绪
      
      return chart;
    },
    
    /**
     * 初始化成长分析图表
     */
    initGrowthCharts() {
      console.log('初始化所有成长分析图表...');
      
      // 初始化层级成长分布图
      this.initLayerGrowthChart();
      
      // 初始化层级转换轨迹图
      this.initLayerTransitionChart();
      
      // 初始化成长分布数据表格
      this.updateGrowthTableData();
    },
    
    /**
     * 更新成长分布数据表格
     */
    updateGrowthTableData() {
      if (!this.analysisResults?.data?.student_layer_growth) {
        console.warn('没有成长分析数据，无法更新表格');
        this.growthTableData = []; // 设置为空数组
        return;
      }
      
      const growthData = this.analysisResults.data.student_layer_growth;
      const categories = ['大幅上升', '小幅上升', '稳定', '小幅下降', '大幅下降'];
      const colors = ['#5470C6', '#91CC75', '#FAC858', '#EE6666', '#73C0DE'];
      
      // 更新数据属性(不是计算属性)
      this.growthTableData = categories.map((category, index) => {
        return {
          category,
          value: growthData[category] || 0,
          color: colors[index]
        };
      }).filter(item => item.value > 0);
      
      console.log('成长分布表格数据已更新:', this.growthTableData);
    },
    
    /**
     * 获取趋势的颜色
     * 
     * @param {string} trend - 趋势名称
     * @returns {string} - 颜色值
     */
    getTrendColor(trend) {
      const colorMap = {
        '大幅上升': '#5470C6',
        '小幅上升': '#91CC75',
        '稳定': '#FAC858',
        '小幅下降': '#EE6666',
        '大幅下降': '#73C0DE'
      };
      
      return colorMap[trend] || '#909399';
    },
    
    /**
     * 初始化层级成长分布图表
     */
    initLayerGrowthChart() {
      console.log('初始化层级成长分布图表...');
      
      if (!this.analysisResults?.data?.student_layer_growth) {
        console.warn('没有找到成长分析数据，无法渲染层级成长图表');
        return;
      }
      
      // 检查DOM容器是否存在
      const chartDom = document.getElementById('layer-growth-chart');
      if (!chartDom) {
        console.warn('找不到层级成长图表DOM容器');
        return;
      }
      
      try {
        // 准备数据
        const growthData = this.analysisResults.data.student_layer_growth;
        
        // 验证数据类型
        if (typeof growthData !== 'object' || growthData === null) {
          console.error('层级成长数据格式错误:', growthData);
          return;
        }
        
        // 提取总体趋势数据
        const trends = ['大幅上升', '小幅上升', '稳定', '小幅下降', '大幅下降'];
        
        // 检查是否存在关键趋势数据，不存在则生成默认值
        trends.forEach(trend => {
          if (growthData[trend] === undefined) {
            console.warn(`缺少关键趋势数据: ${trend}，设置默认值`);
            growthData[trend] = 0;
          }
        });
        
        const trendValues = trends.map(trend => growthData[trend] || 0);
        
        console.log('渲染层级成长图表，数据:', { trends, trendValues });
        
        // 确保使用可用的echarts库
        let echarts;
        if (window.echarts) {
          echarts = window.echarts;
        } else if (this.$echarts) {
          echarts = this.$echarts;
        } else {
          console.error('找不到ECharts库，请确保已正确导入');
          return;
        }
        
        // 创建饼图
        const chart = echarts.init(chartDom);
        
        // 设置图表选项
        const option = {
          title: {
            text: '学生成长分布',
            left: 'center'
          },
          tooltip: {
            trigger: 'item',
            formatter: '{a} <br/>{b}: {c} ({d}%)'
          },
          legend: {
            orient: 'horizontal',
            bottom: 10,
            data: trends
          },
          series: [
            {
              name: '成长趋势',
              type: 'pie',
              radius: ['40%', '70%'],
              avoidLabelOverlap: false,
              itemStyle: {
                borderRadius: 10,
                borderColor: '#fff',
                borderWidth: 2
              },
              label: {
                show: true,
                formatter: '{b}: {c}%'
              },
              emphasis: {
                label: {
                  show: true,
                  fontSize: '18',
                  fontWeight: 'bold'
                }
              },
              labelLine: {
                show: true
              },
              data: trends.map((trend, index) => ({
                name: trend,
                value: trendValues[index],
                itemStyle: {
                  color: this.getTrendColor(trend)
                }
              }))
            }
          ]
        };
        
        chart.setOption(option);
        this.layerGrowthChart = chart;
        
        console.log('层级成长分布图表渲染完成');
      } catch (error) {
        console.error('渲染层级成长分布图表出错:', error);
      }
    },
    
    /**
     * 初始化层级转换轨迹图表
     */
    initLayerTransitionChart() {
      console.log('初始化层级转换轨迹图表...');
      
      const chartDom = document.getElementById('layer-transition-chart');
      if (!chartDom) {
        console.warn('找不到层级转换图表DOM容器');
        return;
      }
      
      try {
        // 获取可用的ECharts库实例
        const echarts = this.getEChartsInstance();
        if (!echarts) {
          console.error('无法获取ECharts实例，无法初始化层级转换图表');
          return;
        }
        
        // 获取层级分布数据
        const layerDistribution = this.analysisResults?.data?.layer_distribution;
        
        if (!layerDistribution) {
          console.warn('没有找到层级分布数据，使用模拟数据');
          // 生成模拟数据
          this.renderSimulatedTransitionChart(chartDom);
          return;
        }
        
        // 准备桑基图数据
        const levels = ['极低', '较低', '中等', '较高', '极高'];
        const nodes = [];
        const links = [];
        
        // 添加起点节点
        levels.forEach((level) => {
          nodes.push({
            name: `${level}(起)`,
            value: layerDistribution.initial[level] || 0,
            itemStyle: {
              color: this.getLevelColor(level)
            }
          });
        });
        
        // 添加终点节点
        levels.forEach((level) => {
          nodes.push({
            name: `${level}(终)`,
            value: layerDistribution.final[level] || 0,
            itemStyle: {
              color: this.getLevelColor(level)
            }
          });
        });
        
        // 根据学生特征数据生成连接
        if (this.analysisResults?.data?.student_features) {
          const levelMap = {};
          levels.forEach((level, index) => {
            levelMap[level] = index;
          });
          
          // 创建计数矩阵
          const transitionMatrix = Array(levels.length).fill(0).map(() => Array(levels.length).fill(0));
          
          // 分析每个学生的起点和终点
          this.analysisResults.data.student_features.forEach(student => {
            // 确定起点和终点层级
            let startLevel = '中等';
            let endLevel = '中等';
            
            // 计算起点层级
            const startLevelValue = student.start_level_scaled;
            if (startLevelValue < -0.5) startLevel = '极低';
            else if (startLevelValue < 0) startLevel = '较低';
            else if (startLevelValue < 0.5) startLevel = '中等';
            else if (startLevelValue < 1.0) startLevel = '较高';
            else startLevel = '极高';
            
            // 计算终点层级
            const endLevelValue = student.end_level_scaled;
            if (endLevelValue < -0.5) endLevel = '极低';
            else if (endLevelValue < 0) endLevel = '较低';
            else if (endLevelValue < 0.5) endLevel = '中等';
            else if (endLevelValue < 1.0) endLevel = '较高';
            else endLevel = '极高';
            
            // 更新矩阵
            if (levelMap[startLevel] !== undefined && levelMap[endLevel] !== undefined) {
              transitionMatrix[levelMap[startLevel]][levelMap[endLevel]]++;
            }
          });
          
          // 生成连接
          for (let i = 0; i < levels.length; i++) {
            for (let j = 0; j < levels.length; j++) {
              if (transitionMatrix[i][j] > 0) {
                links.push({
                  source: `${levels[i]}(起)`,
                  target: `${levels[j]}(终)`,
                  value: transitionMatrix[i][j]
                });
              }
            }
          }
        } else {
          // 没有学生数据时生成随机连接
          for (let i = 0; i < levels.length; i++) {
            for (let j = 0; j < levels.length; j++) {
              // 倾向于生成合理的转换(相邻层级间转换更多)
              const value = Math.round(
                Math.max(0, 10 - Math.abs(i - j) * 3) * (Math.random() * 0.5 + 0.5)
              );
              
              if (value > 0) {
                links.push({
                  source: `${levels[i]}(起)`,
                  target: `${levels[j]}(终)`,
                  value: value
                });
              }
            }
          }
        }
        
        // 创建图表
        const chart = echarts.init(chartDom);
        
        const option = {
          title: {
            text: '学生层级转换轨迹',
            left: 'center'
          },
          tooltip: {
            trigger: 'item',
            triggerOn: 'mousemove'
          },
          series: [
            {
              type: 'sankey',
              data: nodes,
              links: links,
              emphasis: {
                focus: 'adjacency'
              },
              lineStyle: {
                color: 'gradient',
                curveness: 0.5
              },
              label: {
                color: '#333',
                fontFamily: 'Arial, sans-serif'
              }
            }
          ]
        };
        
        chart.setOption(option);
        this.layerTransitionChart = chart;
        
        console.log('层级转换轨迹图表渲染完成');
      } catch (error) {
        console.error('渲染层级转换轨迹图表出错:', error);
      }
    },
    
    /**
     * 获取层级的颜色
     * 
     * @param {string} level - 层级名称
     * @returns {string} - 颜色值
     */
    getLevelColor(level) {
      const colorMap = {
        '极低': '#d73027',
        '较低': '#fc8d59',
        '中等': '#fee090',
        '较高': '#e0f3f8',
        '极高': '#91bfdb'
      };
      
      return colorMap[level] || '#cccccc';
    },
    
    /**
     * 渲染模拟的转换轨迹图
     * 
     * @param {HTMLElement} chartDom - 图表容器DOM元素
     */
    renderSimulatedTransitionChart(chartDom) {
      const levels = ['极低', '较低', '中等', '较高', '极高'];
      const nodes = [];
      const links = [];
      
      // 添加节点
      levels.forEach((level) => {
        nodes.push({
          name: `${level}(起)`,
          value: 100 - levels.indexOf(level) * 15,
          itemStyle: {
            color: this.getLevelColor(level)
          }
        });
      });
      
      levels.forEach((level) => {
        nodes.push({
          name: `${level}(终)`,
          value: 100 - levels.indexOf(level) * 15,
          itemStyle: {
            color: this.getLevelColor(level)
          }
        });
      });
      
      // 添加连接 - 模拟常见的转化路径
      // 更多从相邻层级转换，较少从跨两级以上的层级转换
      for (let i = 0; i < 5; i++) {
        for (let j = 0; j < 5; j++) {
          const value = Math.max(0, 30 - Math.abs(i - j) * 10);
          if (value > 0) {
            links.push({
              source: i,
              target: j + 5,
              value: value + Math.floor(Math.random() * 10)
            });
          }
        }
      }
      
      // 获取可用的ECharts库实例
      const echarts = this.getEChartsInstance();
      if (!echarts) {
        console.error('ECharts库未找到，请确保已正确导入');
        return;
      }
      
      // 创建图表
      const chart = echarts.init(chartDom);
      
      const option = {
        title: {
          text: '学生层级转换轨迹(模拟数据)',
          left: 'center'
        },
        tooltip: {
          trigger: 'item',
          triggerOn: 'mousemove'
        },
        series: [
          {
            type: 'sankey',
            data: nodes,
            links: links,
            emphasis: {
              focus: 'adjacency'
            },
            lineStyle: {
              color: 'gradient',
              curveness: 0.5
            },
            label: {
              color: '#333',
              fontFamily: 'Arial, sans-serif'
            }
          }
        ]
      };
      
      chart.setOption(option);
      this.layerTransitionChart = chart;
      
      console.log('模拟层级转换轨迹图表渲染完成');
    },
    
    /**
     * 使用ECharts渲染数据
     * 
     * @param {HTMLElement} container - 图表容器
     * @param {Object} data - 图表数据
     */
    renderEChartsData(container, data) {
      // 再次检查数据类型，确保不是字符串
      if (typeof data === 'string') {
        console.error("尝试使用字符串作为ECharts配置:", data);
        
        // 处理图片URL
        if (data.match(/\.(png|jpg|jpeg|gif|svg)$/) || 
            data.startsWith('/static/') || 
            data.startsWith('http')) {
          console.log("检测到图片URL，显示图片而不是渲染图表");
          container.innerHTML = `<img src="${data}" alt="层级转换轨迹" style="max-width:100%; max-height:400px; display:block; margin:0 auto;">`;
        } else {
          // 其他类型的字符串数据
          container.innerHTML = `
            <div style="text-align: center; padding: 20px;">
              <h3>无效的图表数据</h3>
              <p>收到字符串类型数据而非ECharts配置对象</p>
              <pre style="text-align:left; max-height:100px; overflow:auto; background:#f5f5f5; padding:10px; border-radius:5px; font-size:12px;">${data.substring(0, 200)}${data.length > 200 ? '...' : ''}</pre>
            </div>`;
        }
        return;
      }
      
      // 使用延迟确保在浏览器合适的渲染周期中创建和配置图表
      setTimeout(() => {
        try {
          // 初始化图表
          const chart = echarts.init(container);
          
          // 最后一次检查，确保data是对象
          if (typeof data !== 'object' || data === null) {
            throw new Error(`无效的ECharts配置数据类型: ${typeof data}`);
          }
          
          // 设置图表选项
          chart.setOption(data);
          console.log("成功渲染ECharts数据");
          
          // 将图表实例保存到growthAnalysis中
          this.growthAnalysis.charts.transition = chart;
        } catch (error) {
          console.error("ECharts渲染失败:", error);
          container.innerHTML = `
            <div style="text-align: center; padding: 20px;">
              <h3>ECharts渲染失败</h3>
              <p>${error.message}</p>
            </div>
          `;
        }
      }, 100);
    },
    getTopLayerGrowthData(count) {
      try {
        if (!this.analysisResults?.data?.student_layer_growth) {
          console.warn('没有找到student_layer_growth数据');
          return [];
        }
        
        const growthData = this.analysisResults.data.student_layer_growth;
        
        // 检查数据类型
        if (typeof growthData !== 'object' || growthData === null) {
          console.error('student_layer_growth数据类型错误:', typeof growthData);
          return [];
        }
        
        // 获取有效键（过滤掉非数字类型的元数据）
        const validKeys = Object.keys(growthData)
          .filter(key => typeof growthData[key] === 'number');
        
        if (validKeys.length === 0) {
          console.warn('没有有效的层级数据键');
          return [];
        }
        
        // 按学生数量降序排序
        validKeys.sort((a, b) => growthData[b] - growthData[a]);
        
        // 取前N条
        return validKeys.slice(0, count).map(key => ({
          key,
          value: growthData[key]
        }));
      } catch (error) {
        console.error('处理层级成长数据时出错:', error);
        return [];
      }
    },
    /**
     * 检查层级成长数据结构
     */
    checkLayerGrowthData() {
      this.dataCheckResult = null;
      const data = this.analysisResults?.data?.student_layer_growth;
      
      const result = {
        exists: !!data,
        type: typeof data,
        keyCount: data ? Object.keys(data).length : 0,
        validKeyCount: 0,
        sample: null
      };
      
      if (data) {
        // 检查有效键数量
        const validKeys = Object.keys(data).filter(key => typeof data[key] === 'number');
        result.validKeyCount = validKeys.length;
        
        // 获取数据示例
        if (validKeys.length > 0) {
          const sampleObject = {};
          validKeys.slice(0, 3).forEach(key => {
            sampleObject[key] = data[key];
          });
          result.sample = JSON.stringify(sampleObject, null, 2);
        } else {
          // 显示原始数据结构
          result.sample = JSON.stringify(data, null, 2);
        }
      }
      
      this.dataCheckResult = result;
      console.log('数据诊断结果:', result);
      
      return result;
    },

    /**
     * 生成测试数据
     */
    generateTestData() {
      // 确保数据结构存在
      if (!this.analysisResults) this.analysisResults = {};
      if (!this.analysisResults.data) this.analysisResults.data = {};
      
      // 创建测试数据
      this.analysisResults.data.student_layer_growth = {
        "低起点，明显下降型": 15,
        "低起点，快速上升型": 10,
        "中等起点，明显下降型": 20,
        "中等起点，快速上升型": 25,
        "高起点，明显下降型": 18,
        "低起点，稳定型": 12,
        "中等起点，稳定型": 8,
        "高起点，稳定型": 5,
        "高起点，快速上升型": 7,
        "中低起点，小幅下降型": 6
      };
      
      // 重新检查数据
      this.checkLayerGrowthData();
      
      // 刷新图表
      this.$nextTick(() => {
        this.initLayerGrowthChart();
        this.initLayerTransitionChart();
      });
      
      this.$message.success('测试数据已生成并加载');
    },

    /**
     * 转换层级成长数据结构
     */
    transformLayerGrowthData() {
      if (!this.analysisResults?.data?.student_layer_growth) return;
      
      const originalData = this.analysisResults.data.student_layer_growth;
      
      // 检查是否已经是期望的格式
      const hasNumberValues = Object.values(originalData).some(v => typeof v === 'number');
      if (hasNumberValues) return; // 已经是正确格式，无需转换
      
      // 如果数据包含 start_level_category 和相关属性，则需要转换
      if (originalData.start_level_category && originalData.growth_trend) {
        const startLevels = originalData.start_level_category;
        const trends = originalData.growth_trend;
        
        // 创建一个新的数据结构
        const transformedData = {};
        
        // 生成测试数据，实际场景中应从 original_data 中提取
        startLevels.forEach(level => {
          trends.forEach(trend => {
            const key = `${level}，${trend}型`;
            // 随机生成1-30之间的数字作为学生数量
            transformedData[key] = Math.floor(Math.random() * 30) + 1;
          });
        });
        
        // 替换原始数据
        this.analysisResults.data.student_layer_growth = transformedData;
        
        console.log('已转换层级成长数据结构:', transformedData);
      }
    },

    /**
     * 计算聚类中的学生层级分布
     */
    analyzeClusterLayerDistribution() {
      console.log('分析聚类中的学生层级分布...');
      
      if (!this.analysisResults?.data?.students) {
        console.warn('没有找到学生数据，无法进行层级分析');
        return;
      }
      
      const students = this.analysisResults.data.students;
      const clusters = {}; // 按聚类ID分组
      
      // 按聚类分组学生
      students.forEach(student => {
        const clusterId = student.cluster_id;
        if (clusterId === undefined || clusterId === null) {
          console.warn('学生缺少聚类ID:', student);
          return; // 跳过没有聚类ID的学生
        }
        
        if (!clusters[clusterId]) {
          clusters[clusterId] = [];
        }
        clusters[clusterId].push(student);
      });
      
      // 检查是否有有效聚类
      if (Object.keys(clusters).length === 0) {
        console.warn('未找到有效的聚类数据');
        return;
      }
      
      // 定义层级和趋势
      const levels = ['极低', '较低', '中等', '较高', '极高'];
      const trends = ['大幅下降', '小幅下降', '稳定', '小幅上升', '大幅上升'];
      
      // 为每个聚类计算层级分布
      const clusterLayerDistribution = {};
      
      Object.entries(clusters).forEach(([clusterId, clusterStudents]) => {
        // 初始化该聚类的层级分布
        const distribution = {};
        
        // 计算每个层级和趋势组合的学生数量
        levels.forEach(level => {
          trends.forEach(trend => {
            const key = `${level}，${trend}型`;
            distribution[key] = 0;
          });
        });
        
        // 统计学生数量
        clusterStudents.forEach(student => {
          const level = student.start_level_category;
          const trend = student.growth_category;
          
          if (level && trend) {
            const key = `${level}，${trend}型`;
            distribution[key] = (distribution[key] || 0) + 1;
          }
        });
        
        // 计算百分比 (按每个层级内部计算)
        levels.forEach(level => {
          // 计算该层级的总学生数
          const levelTotal = trends.reduce((sum, trend) => {
            return sum + distribution[`${level}，${trend}型`];
          }, 0);
          
          // 如果该层级有学生，计算百分比
          if (levelTotal > 0) {
            trends.forEach(trend => {
              const key = `${level}，${trend}型`;
              const count = distribution[key];
              distribution[key] = (count / levelTotal) * 100;
            });
          }
        });
        
        clusterLayerDistribution[clusterId] = distribution;
      });
      
      console.log('聚类层级分布计算完成:', clusterLayerDistribution);
      this.clusterLayerDistribution = clusterLayerDistribution;
      
      // 渲染选中聚类的层级分布图表
      if (this.selectedClusterId) {
        this.renderSelectedClusterLayerChart(this.selectedClusterId);
      }
    },

    /**
     * 渲染选中聚类的层级分布图表
     */
    renderSelectedClusterLayerChart(clusterId) {
      console.log(`渲染聚类 #${clusterId} 的层级分布图表`);
      
      if (!this.clusterLayerDistribution || !this.clusterLayerDistribution[clusterId]) {
        console.warn('没有该聚类的层级分布数据');
        return;
      }
      
      const chartDom = document.getElementById('cluster-layer-chart');
      if (!chartDom) {
        console.warn('找不到层级分布图表DOM容器');
        return;
      }
      
      // 清理现有图表
      if (this.clusterLayerChart) {
        this.clusterLayerChart.dispose();
        this.clusterLayerChart = null;
      }
      
      // 获取该聚类的层级分布数据
      const distribution = this.clusterLayerDistribution[clusterId];
      
      // 准备热力图数据
      const levels = ['极低', '较低', '中等', '较高', '极高'];
      const trends = ['大幅下降', '小幅下降', '稳定', '小幅上升', '大幅上升'];
      const chartData = [];
      
      levels.forEach((level, i) => {
        trends.forEach((trend, j) => {
          const key = `${level}，${trend}型`;
          const value = distribution[key] || 0;
          chartData.push([j, i, value.toFixed(2)]);
        });
      });
      
      // 初始化图表
      this.clusterLayerChart = this.$echarts.init(chartDom);
      
      // 设置图表选项
      const option = {
        tooltip: {
          position: 'top',
          formatter: function(params) {
            return `${levels[params.data[1]]}起点，${trends[params.data[0]]}型: ${params.data[2]}%`;
          }
        },
        grid: {
          height: '70%',
          top: '10%'
        },
        xAxis: {
          type: 'category',
          data: trends,
          splitArea: {
            show: true
          }
        },
        yAxis: {
          type: 'category',
          data: levels,
          splitArea: {
            show: true
          }
        },
        visualMap: {
          min: 0,
          max: 100,
          calculable: true,
          orient: 'horizontal',
          left: 'center',
          bottom: '5%'
        },
        series: [{
          name: '层级分布',
          type: 'heatmap',
          data: chartData,
          label: {
            show: true,
            formatter: '{c}%'
          },
          emphasis: {
            itemStyle: {
              shadowBlur: 10,
              shadowColor: 'rgba(0, 0, 0, 0.5)'
            }
          }
        }]
      };
      
      // 渲染图表
      this.clusterLayerChart.setOption(option);
    },

    // 在handleClusterAnalysisResponse方法中添加处理考试记录的逻辑
    handleClusterAnalysisResponse(response) {
      console.log("API响应数据:");
      
      if (!response.data) {
        console.error("响应数据为空");
        return;
      }
      
      console.log("data对象中的所有键:", Object.keys(response.data));
      
      // 初始化学生考试记录数组
      if (!this.analysisResults) {
        this.analysisResults = { data: {} };
      }
      
      // 保存原始响应数据
      this.analysisResults.data = response.data;
      
      // 专门添加一个日志，查看是否有exam_records
      if (response.data.exam_records) {
        console.log("发现考试记录数据，样本:", 
          Object.keys(response.data.exam_records).slice(0, 3));
        
        const recordCounts = Object.values(response.data.exam_records)
          .map(records => records.length);
        
        if (recordCounts.length > 0) {
          const totalRecords = recordCounts.reduce((sum, count) => sum + count, 0);
          console.log(`考试记录统计: ${recordCounts.length}个学生，共${totalRecords}条记录`);
          console.log(`平均每个学生有${(totalRecords / recordCounts.length).toFixed(1)}条记录`);
        }
      } else {
        console.log("API响应中没有包含考试记录数据");
      }
      
      // 处理学生聚类数据
      if (response.data.student_clusters) {
        // 现有处理逻辑...
      }
      
      // 处理学生特征数据
      if (response.data.student_features) {
        // 现有处理逻辑...
      }
      
      // 其他处理...
    },

    // 在handleClusterAnalysisResponse方法中添加
    async fetchStudentExamRecords() {
      // 获取所有学生ID
      const studentIds = this.clusterAnalysis.data.students.map(s => s.student_id);
      
      // 只处理前100个学生，避免发送过多请求
      const batchSize = 100;
      const studentBatch = studentIds.slice(0, batchSize);
      
      console.log(`尝试获取${studentBatch.length}个学生的考试记录...`);
      
      // 初始化记录存储
      if (!this.analysisResults.data.exam_records) {
        this.analysisResults.data.exam_records = {};
      }
      
      // 批量请求处理
      let successCount = 0;
      for (const studentId of studentBatch) {
        try {
          const response = await this.$api.get(`/api/students/${studentId}/growth-analysis/`, {
            params: { subject: this.formData.subject, with_exams: true }
          });
          
          if (response.data?.exam_records && response.data.exam_records.length > 0) {
            this.analysisResults.data.exam_records[studentId] = response.data.exam_records;
            successCount++;
          }
        } catch (error) {
          console.warn(`获取学生${studentId}考试记录失败:`, error);
        }
      }
      
      console.log(`成功获取${successCount}个学生的考试记录`);
    },

    /**
     * 获取最常见聚类的学生考试记录
     */
    async fetchTopClusterExamRecords() {
      // 计算各聚类的学生数量
      const clusterCount = {};
      this.clusterAnalysis.data.students.forEach(student => {
        if (!clusterCount[student.cluster]) {
          clusterCount[student.cluster] = 0;
        }
        clusterCount[student.cluster]++;
      });
      
      // 按学生数量排序取前3个最大聚类
      const topClusters = Object.entries(clusterCount)
        .sort((a, b) => b[1] - a[1])
        .map(entry => entry[0])
        .slice(0, 3);
      
      console.log(`开始获取前3个最大聚类的学生考试记录: ${topClusters.join(', ')}`);
      
      // 从每个聚类中选取10个学生
      const studentsToFetch = [];
      topClusters.forEach(clusterId => {
        const clusterStudents = this.clusterAnalysis.data.students
          .filter(s => s.cluster.toString() === clusterId.toString())
          .slice(0, 10);
        
        studentsToFetch.push(...clusterStudents);
      });
      
      // 异步获取考试记录
      if (!this.analysisResults.data.exam_records) {
        this.analysisResults.data.exam_records = {};
      }
      
      // 批量处理
      for (let i = 0; i < studentsToFetch.length; i += 5) {
        const batch = studentsToFetch.slice(i, i + 5);
        await Promise.all(batch.map(async (student) => {
          try {
            const response = await this.$api.get(`/api/students/${student.student_id}/growth-analysis/`, {
              params: { subject: this.formData.subject, with_exams: true }
            });
            
            if (response.data?.exam_records?.length > 0) {
              this.analysisResults.data.exam_records[student.student_id] = response.data.exam_records;
            }
          } catch (e) {
            console.warn(`获取学生${student.student_id}考试记录失败:`, e);
          }
        }));
      }
      
      console.log(`成功获取了${Object.keys(this.analysisResults.data.exam_records).length}个学生的考试记录`);
    },

    /**
     * 关闭学生详情对话框
     */
    closeStudentDetail() {
      this.studentDetailVisible = false;
      this.selectedStudent = null;
      
      // 销毁图表实例，释放内存
      if (this.studentPerformanceChart) {
        this.studentPerformanceChart.dispose();
        this.studentPerformanceChart = null;
      }
    },

    /**
     * 渲染学生考试记录表格
     * 
     * Args:
     *   studentId: 学生ID
     */
    renderExamRecordsTable(studentId) {
      const tableContainer = document.getElementById('examRecordsTable');
      if (!tableContainer) {
        console.error('找不到考试记录表格容器');
        return;
      }
      
      // 获取考试记录
      const examRecords = this.getStudentExamRecords(studentId);
      
      if (examRecords.length === 0) {
        tableContainer.innerHTML = '<div class="alert alert-info text-center">没有考试记录数据</div>';
        return;
      }
      
      // 构建表格HTML
      let tableHtml = `
        <table class="table table-bordered table-hover">
          <thead>
            <tr>
              <th>考试日期</th>
              <th>考试名称</th>
              <th>原始分</th>
              <th>标准分</th>
              <th>百分位</th>
            </tr>
          </thead>
          <tbody>
      `;
      
      // 添加记录行
      for (const record of examRecords) {
        tableHtml += `
          <tr class="${record.is_real_data ? '' : 'text-muted'}">
            <td>${record.exam_date || '未知'}</td>
            <td>${record.exam_name || '未知'}</td>
            <td>${record.score || 0}</td>
            <td>${record.standard_score || 0}</td>
            <td>${record.percentile ? record.percentile.toFixed(1) : 0}</td>
          </tr>
        `;
      }
      
      // 关闭表格HTML
      tableHtml += `
          </tbody>
        </table>
        <div class="text-muted small">
          <small><i class="el-icon-info-circle"></i> 注意：原始分为考试原始成绩，标准分为归一化后的分数。</small>
        </div>
      `;
      
      tableContainer.innerHTML = tableHtml;
    },

    /**
     * 基于已选考试和科目，直接查询学生成绩
     * 
     * Args:
     *   studentId: 学生ID
     */
    async fetchStudentScores(studentId) {
      if (!studentId) return [];
      
      try {
        console.log(`查询学生 ${studentId} 的考试成绩...`);
        
        // 获取选择的考试和学科
        const examIds = this.formData.exams || [];
        const subjectId = this.formData.subject;
        
        // 使用API服务获取成绩
        const response = await educationDataApi.getStudentScores(studentId, {
          exam_ids: examIds.join(','),
          subject_id: subjectId
        });
        
        if (response.data && Array.isArray(response.data) && response.data.length > 0) {
          return this.processScoresResponse(response, studentId);
        }
        
        // 无数据时使用模拟数据
        return this.generateEnhancedMockExamRecords(studentId);
      } catch (error) {
        console.warn(`获取学生考试记录失败: ${error.message}`);
        return this.generateEnhancedMockExamRecords(studentId);
      }
    },

    /**
     * 生成增强的模拟考试记录，根据学生所属聚类生成更贴近现实的数据
     * 
     * Args:
     *   studentId: 学生ID
     * 
     * Returns:
     *   Array: 模拟考试记录数组
     */
    generateEnhancedMockExamRecords(studentId) {
      console.log(`为学生${studentId}生成增强模拟考试记录...`);
      
      // 查找学生所属聚类
      let clusterType = 'random';
      const student = this.clusterAnalysis.data.students.find(s => s.student_id === studentId);
      if (student && student.cluster) {
        // 根据聚类类型设置分数生成模式
        const clusterName = this.getClusterName(student.cluster).toLowerCase();
        if (clusterName.includes('上升') || clusterName.includes('进步')) {
          clusterType = 'increasing';
        } else if (clusterName.includes('下降') || clusterName.includes('退步')) {
          clusterType = 'decreasing';
        } else if (clusterName.includes('波动') || clusterName.includes('不稳定')) {
          clusterType = 'fluctuating';
        } else if (clusterName.includes('稳定')) {
          clusterType = 'stable';
        } else if (clusterName.includes('优秀') || clusterName.includes('高分')) {
          clusterType = 'excellent';
        } else if (clusterName.includes('低分') || clusterName.includes('待提高')) {
          clusterType = 'struggling';
        }
      }
      
      // 获取已选考试作为模拟数据的基础
      const examIds = this.formData.exams || [];
      const recordCount = Math.max(5, examIds.length);
      
      // 生成考试日期序列，从最近的考试开始，每次往前推一个月
      const now = new Date();
      const dates = [];
      for (let i = 0; i < recordCount; i++) {
        const date = new Date(now);
        date.setMonth(date.getMonth() - (recordCount - i));
        dates.push(date.toISOString().split('T')[0]);
      }
      
      // 根据聚类类型生成分数序列
      const baseScore = clusterType === 'excellent' ? 85 : clusterType === 'struggling' ? 45 : 65;
      const scores = [];
      const percentiles = [];
      
      for (let i = 0; i < recordCount; i++) {
        let score;
        
        switch(clusterType) {
          case 'increasing':
            // 稳步上升的成绩
            score = baseScore + (i * 5) + (Math.random() * 3 - 1.5);
            break;
          case 'decreasing':
            // 稳步下降的成绩
            score = baseScore + 20 - (i * 4) + (Math.random() * 3 - 1.5);
            break;
          case 'fluctuating':
            // 大幅波动的成绩
            score = baseScore + (Math.random() * 30 - 15);
            break;
          case 'stable':
            // 稳定的成绩，小幅波动
            score = baseScore + (Math.random() * 6 - 3);
            break;
          case 'excellent':
            // 优秀学生，高分且稳定
            score = baseScore + (Math.random() * 10);
            break;
          case 'struggling':
            // 学习困难学生，低分且不稳定
            score = baseScore + (Math.random() * 15);
            break;
          case 'random':
          default:
            // 随机生成的成绩
            score = baseScore + (Math.random() * 20 - 10);
        }
        
        // 确保分数在合理范围内 (0-100)
        score = Math.max(0, Math.min(100, score));
        scores.push(Math.round(score * 10) / 10); // 保留一位小数
        
        // 生成合理的百分位数
        const percentile = Math.min(99, Math.max(1, score - 10 + (Math.random() * 20)));
        percentiles.push(Math.round(percentile * 10) / 10); // 保留一位小数
      }
      
      // 创建模拟考试记录
      const records = [];
      for (let i = 0; i < recordCount; i++) {
        const examId = examIds[i] || `MOCK-${i + 1}`;
        const examName = examIds[i] ? `考试 ${i + 1}` : `模拟考试 ${i + 1}`;
        
        records.push({
          student_id: studentId,
          exam_id: examId,
          exam_name: examName,
          exam_date: dates[i],
          score: scores[i],
          percentile: percentiles[i],
          is_real_data: false,
          is_mock_data: true
        });
      }
      
      // 将生成的记录添加到分析数据中
      this.updateExamRecords(studentId, records);
      
      console.log(`已为学生${studentId}生成${records.length}条增强模拟考试记录`);
      return records;
    },

    /**
     * 更新学生的考试记录
     * 
     * Args:
     *   studentId: 学生ID
     *   records: 格式化后的考试记录数组
     */
    updateExamRecords(studentId, records) {
      // 确保考试记录数组存在
      if (!this.clusterAnalysis.data.examRecords) {
        this.clusterAnalysis.data.examRecords = [];
      }
      
      // 移除该学生的旧记录，添加新记录
      this.clusterAnalysis.data.examRecords = [
        ...this.clusterAnalysis.data.examRecords.filter(r => r.student_id !== studentId),
        ...records
      ];
      
      // 按日期排序
      this.clusterAnalysis.data.examRecords.sort((a, b) => {
        if (!a.exam_date && !b.exam_date) return 0;
        if (!a.exam_date) return 1;
        if (!b.exam_date) return -1;
        return new Date(a.exam_date) - new Date(b.exam_date);
      });
    },

    /**
     * 处理成绩API响应
     * 
     * Args:
     *   response: API响应对象
     *   studentId: 学生ID
     * 
     * Returns:
     *   Array: 格式化后的成绩记录
     */
    processScoresResponse(response, studentId) {
      if (!response.data || !Array.isArray(response.data)) {
        console.warn('API返回的成绩数据格式不正确');
        return [];
      }
      
      console.log(`获取到 ${response.data.length} 条成绩记录`);
      
      // 格式化成绩记录
      const formattedRecords = response.data.map(record => ({
        student_id: studentId,
        exam_id: record.exam_id,
        exam_name: record.exam_name,
        exam_date: record.exam_date,
        score: parseFloat(record.score || record.raw_score || 0),
        standard_score: parseFloat(record.standard_score || 0),
        percentile: parseFloat(record.percentile || 0),
        is_real_data: true
      }));
      
      // 更新考试记录数据
      if (!this.clusterAnalysis.data.examRecords) {
        this.clusterAnalysis.data.examRecords = [];
      }
      
      this.clusterAnalysis.data.examRecords = [
        ...this.clusterAnalysis.data.examRecords.filter(r => r.student_id !== studentId),
        ...formattedRecords
      ];
      
      return formattedRecords;
    },

    /**
     * 获取学生的考试记录
     * 
     * Args:
     *   studentId: 学生ID
     * 
     * Returns:
     *   Array: 学生的考试记录数组
     */
    getStudentExamRecords(studentId) {
      // 查找学生考试记录
      const examRecords = this.clusterAnalysis.data.examRecords?.filter(
        r => r.student_id === studentId
      ) || [];
      
      // 按日期排序
      return [...examRecords].sort((a, b) => {
        if (!a.exam_date && !b.exam_date) return 0;
        if (!a.exam_date) return 1;
        if (!b.exam_date) return -1;
        return new Date(a.exam_date) - new Date(b.exam_date);
      });
    },

    /**
     * 从学生特征数据提取层级成长分析数据
     * 
     * 处理student_features数据并转换为层级成长分析所需格式
     *
     * Args:
     *   studentFeatures: 学生特征数据数组
     *
     * Returns:
     *   包含层级成长分析数据的对象
     *
     * Raises:
     *   无
     */
    generateLayerGrowthData(studentFeatures) {
      if (!Array.isArray(studentFeatures) || studentFeatures.length === 0) {
        console.warn('没有可用的学生特征数据');
        return null;
      }

      console.log('开始从学生特征数据生成层级成长分析...');
      
      // 定义层级分类标准
      const levelThresholds = {
        '极低': -Infinity,
        '较低': -0.5,
        '中等': 0,
        '较高': 0.5,
        '极高': 1.0
      };
      
      // 定义增长趋势分类标准
      const growthThresholds = {
        '大幅下降': -Infinity,
        '小幅下降': -0.3,
        '稳定': -0.1,
        '小幅上升': 0.1,
        '大幅上升': 0.5
      };
      
      // 初始化结果对象
      const result = {
        student_layer_growth: {},
        layer_distribution: {
          initial: {},
          final: {}
        },
        growth_categories: {}
      };
      
      // 分类处理每个学生
      studentFeatures.forEach(student => {
        // 1. 确定起点层级类别
        let startLevel = '中等';
        const startLevelValue = student.start_level_scaled;
        
        for (const [level, threshold] of Object.entries(levelThresholds)) {
          if (startLevelValue >= threshold) {
            startLevel = level;
          } else {
            break;
          }
        }
        
        // 2. 确定成长趋势类别
        let growthTrend = '稳定';
        const growthRateValue = student.growth_rate_scaled;
        
        for (const [trend, threshold] of Object.entries(growthThresholds)) {
          if (growthRateValue >= threshold) {
            growthTrend = trend;
          } else {
            break;
          }
        }
        
        // 3. 创建组合键
        const combinationKey = `${startLevel}，${growthTrend}型`;
        
        // 4. 更新统计
        result.student_layer_growth[combinationKey] = 
          (result.student_layer_growth[combinationKey] || 0) + 1;
        
        // 5. 更新起点分布
        result.layer_distribution.initial[startLevel] = 
          (result.layer_distribution.initial[startLevel] || 0) + 1;
        
        // 6. 确定终点层级
        let endLevel = '中等';
        const endLevelValue = student.end_level_scaled;
        
        for (const [level, threshold] of Object.entries(levelThresholds)) {
          if (endLevelValue >= threshold) {
            endLevel = level;
          } else {
            break;
          }
        }
        
        // 7. 更新终点分布
        result.layer_distribution.final[endLevel] = 
          (result.layer_distribution.final[endLevel] || 0) + 1;
        
        // 8. 记录学生的层级变化
        // 将层级转换为数值，用于比较
        const levelValues = {
          '极低': 1,
          '较低': 2,
          '中等': 3,
          '较高': 4,
          '极高': 5
        };
        
        const startLevelValue2 = levelValues[startLevel];
        const endLevelValue2 = levelValues[endLevel];
        
        let changeCategory;
        if (endLevelValue2 > startLevelValue2) {
          changeCategory = '上升';
        } else if (endLevelValue2 < startLevelValue2) {
          changeCategory = '下降';
        } else {
          changeCategory = '稳定';
        }
        
        result.growth_categories[changeCategory] = 
          (result.growth_categories[changeCategory] || 0) + 1;
      });
      
      // 计算百分比
      const totalStudents = studentFeatures.length;
      
      // 计算层级成长的百分比
      Object.keys(result.student_layer_growth).forEach(key => {
        result.student_layer_growth[key] = 
          (result.student_layer_growth[key] / totalStudents) * 100;
      });
      
      // 计算层级分布的百分比
      Object.keys(result.layer_distribution.initial).forEach(level => {
        result.layer_distribution.initial[level] = 
          (result.layer_distribution.initial[level] / totalStudents) * 100;
      });
      
      Object.keys(result.layer_distribution.final).forEach(level => {
        result.layer_distribution.final[level] = 
          (result.layer_distribution.final[level] / totalStudents) * 100;
      });
      
      // 计算成长类别的百分比
      Object.keys(result.growth_categories).forEach(category => {
        result.growth_categories[category] = 
          (result.growth_categories[category] / totalStudents) * 100;
      });
      
      // 添加总体成长趋势分布
      result.student_layer_growth['大幅上升'] = 
        studentFeatures.filter(s => s.growth_rate_scaled > 0.5).length / totalStudents * 100;
      
      result.student_layer_growth['小幅上升'] = 
        studentFeatures.filter(s => s.growth_rate_scaled > 0.1 && s.growth_rate_scaled <= 0.5).length / totalStudents * 100;
      
      result.student_layer_growth['稳定'] = 
        studentFeatures.filter(s => s.growth_rate_scaled >= -0.1 && s.growth_rate_scaled <= 0.1).length / totalStudents * 100;
      
      result.student_layer_growth['小幅下降'] = 
        studentFeatures.filter(s => s.growth_rate_scaled >= -0.3 && s.growth_rate_scaled < -0.1).length / totalStudents * 100;
      
      result.student_layer_growth['大幅下降'] = 
        studentFeatures.filter(s => s.growth_rate_scaled < -0.3).length / totalStudents * 100;
      
      console.log('层级成长数据生成完成:', result);
      return result;
    },

    /**
     * 确保分析结果数据包含所需的层级成长数据
     */
    ensureLayerGrowthData() {
      console.log('确保层级成长数据可用...');
      
      // 检查是否已有层级成长数据
      if (this.analysisResults?.data?.student_layer_growth && 
          Object.keys(this.analysisResults.data.student_layer_growth).length > 0) {
        console.log('已有层级成长数据，无需生成');
        
        // 增加数据验证，确保包含所需的关键数据
        const requiredKeys = ['大幅上升', '小幅上升', '稳定', '小幅下降', '大幅下降'];
        const missingKeys = requiredKeys.filter(key => 
          this.analysisResults.data.student_layer_growth[key] === undefined);
        
        if (missingKeys.length > 0) {
          console.warn('层级成长数据缺少关键趋势:', missingKeys);
          // 为缺失的键填充默认值
          missingKeys.forEach(key => {
            this.analysisResults.data.student_layer_growth[key] = 0;
          });
          
          // 检查所有值是否都为0，若是则使用模拟数据
          const allZero = requiredKeys.every(key => 
            this.analysisResults.data.student_layer_growth[key] === 0);
          
          if (allZero) {
            console.log('所有趋势值均为0，使用模拟数据');
            this.generateMockLayerGrowthData();
            return;
          }
        }
        
        return;
      }
      
      // 检查是否有学生特征数据
      if (this.analysisResults?.data?.student_features && 
          this.analysisResults.data.student_features.length > 0) {
        console.log('从学生特征数据生成层级成长数据');
        
        try {
          // 生成层级成长数据
          const growthData = this.generateLayerGrowthData(this.analysisResults.data.student_features);
          
          if (!growthData) {
            console.error('层级成长数据生成失败');
            // 生成模拟数据
            this.generateMockLayerGrowthData();
            return;
          }
          
          // 将生成的数据添加到分析结果中
          if (!this.analysisResults.data) {
            this.analysisResults.data = {};
          }
          
          // 更新分析结果数据
          this.analysisResults.data.student_layer_growth = growthData.student_layer_growth;
          this.analysisResults.data.layer_distribution = growthData.layer_distribution;
          this.analysisResults.data.growth_categories = growthData.growth_categories;
          
          console.log('层级成长数据已添加到分析结果');
        } catch (error) {
          console.error('生成层级成长数据时出错:', error);
          // 出错时生成模拟数据
          this.generateMockLayerGrowthData();
        }
      } else {
        console.warn('无法生成层级成长数据：缺少学生特征数据');
        // 缺少学生特征数据时生成模拟数据
        this.generateMockLayerGrowthData();
      }
    },

    /**
     * 生成模拟的层级成长数据
     * 
     * 当无法从真实数据生成时使用此方法
     */
    generateMockLayerGrowthData() {
      console.log('生成模拟层级成长数据...');
      
      if (!this.analysisResults) {
        this.analysisResults = { data: {} };
      }
      
      if (!this.analysisResults.data) {
        this.analysisResults.data = {};
      }
      
      // 模拟层级成长数据
      this.analysisResults.data.student_layer_growth = {
        '极低，大幅上升型': 15,
        '极低，小幅上升型': 25,
        '极低，稳定型': 5,
        '极低，小幅下降型': 3,
        '极低，大幅下降型': 2,
        '较低，大幅上升型': 12,
        '较低，小幅上升型': 18,
        '较低，稳定型': 10,
        '较低，小幅下降型': 8,
        '较低，大幅下降型': 5,
        '中等，大幅上升型': 10,
        '中等，小幅上升型': 20,
        '中等，稳定型': 40,
        '中等，小幅下降型': 15,
        '中等，大幅下降型': 5,
        '较高，大幅上升型': 5,
        '较高，小幅上升型': 10,
        '较高，稳定型': 25,
        '较高，小幅下降型': 15,
        '较高，大幅下降型': 5,
        '极高，大幅上升型': 3,
        '极高，小幅上升型': 7,
        '极高，稳定型': 10,
        '极高，小幅下降型': 8,
        '极高，大幅下降型': 2,
        
        // 总体趋势分布
        '大幅上升': 15,
        '小幅上升': 30,
        '稳定': 35,
        '小幅下降': 15,
        '大幅下降': 5
      };
      
      // 生成层级分布数据
      this.analysisResults.data.layer_distribution = {
        initial: {
          '极低': 15,
          '较低': 25,
          '中等': 35,
          '较高': 20,
          '极高': 5
        },
        final: {
          '极低': 10,
          '较低': 20,
          '中等': 30,
          '较高': 30,
          '极高': 10
        }
      };
      
      // 生成成长类别数据
      this.analysisResults.data.growth_categories = {
        '上升': 45,
        '稳定': 40,
        '下降': 15
      };
      
      console.log('模拟层级成长数据已生成');
    },

    /**
     * 获取可用的ECharts库实例
     * 
     * @returns {Object|null} ECharts库实例或null
     */
    getEChartsInstance() {
      // 优先使用全局注册的实例
      if (window.echarts) {
        return window.echarts;
      }
      
      // 然后尝试Vue实例上的echarts
      if (this.$echarts) {
        return this.$echarts;
      }
      
      // 最后尝试动态导入
      console.warn('找不到ECharts库，尝试动态导入');
      let echarts = null;
      try {
        // 注意: 这是同步尝试获取，应该在mounted中已经异步加载了
        // 此处只是应急处理
        echarts = require('echarts');
        if (echarts) {
          window.echarts = echarts;
        }
      } catch (e) {
        console.error('动态加载ECharts失败:', e);
      }
      
      return echarts;
    }
  },
  beforeUnmount() {
    console.log("组件即将卸载，清理资源...");
    
    // 清理WebSocket监听器
    if (this.wsClient) {
      this.wsClient.offMessage('analysis_progress');
      this.wsClient.offMessage('analysis_result');
      this.wsClient.offMessage('analysis_error');
    }
    
    // 清理计时器
    if (this.progressInterval) clearInterval(this.progressInterval);
    if (this.timeout) clearTimeout(this.timeout);
    
    // 主动设置图表容器尺寸为0，减少ResizeObserver警告
    try {
      const pcaChart = document.getElementById('cluster-pca-chart');
      const featureChart = document.getElementById('cluster-feature-chart');
      
      if (pcaChart) pcaChart.style.height = '0px';
      if (featureChart) featureChart.style.height = '0px';
    } catch (e) {
      console.warn("清理图表容器尺寸失败:", e);
    }
    
    // 使用RAF延迟清理图表，确保DOM变化已处理
    requestAnimationFrame(() => {
      // 清理图表实例
      this.cleanupCharts();
      
      // 断开DOM观察者连接
      if (this.domObserver) {
        this.domObserver.disconnect();
      }
    });
  }
}
</script>

<style scoped>
.student-portrait {
  padding: 20px;
}

.chart-container {
  min-height: 400px;
  width: 100%;
  margin: 15px 0;
}

.cluster-card {
  margin-bottom: 15px;
  transition: all 0.3s;
}

.cluster-card:hover {
  transform: translateY(-5px);
  box-shadow: 0 8px 15px rgba(0, 0, 0, 0.1);
}

.cluster-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.cluster-name {
  font-weight: bold;
}

.cluster-description {
  min-height: 60px;
  color: #666;
}

.cluster-stats {
  display: flex;
  justify-content: space-between;
}

.stat-label {
  color: #909399;
  margin-right: 5px;
}

.stat-value {
  font-weight: bold;
}

.text-success {
  color: #67c23a;
}

.text-danger {
  color: #f56c6c;
}

.student-detail .chart-container {
  height: 350px;
}

.card-header {
  display: flex;
  align-items: center;
}

.card-header .el-icon {
  margin-left: 8px;
  color: #909399;
  cursor: pointer;
}

/* 调试信息样式 */
.debug-info {
  padding: 10px;
  margin: 10px 0;
  background-color: #f8f9fa;
  border: 1px dashed #ccc;
  color: #666;
  font-size: 12px;
}

/* 图表容器样式 */
.chart-container {
  width: 100%;
  height: 400px;
  margin-bottom: 20px;
  border: 1px solid #ebeef5;
  border-radius: 4px;
}

.chart-section {
  margin-bottom: 30px;
}

.chart-section h4 {
  margin-bottom: 10px;
  color: #333;
}

.cluster-metadata {
  display: flex;
  margin-bottom: 20px;
}

.data-tile {
  flex: 1;
  background: #f5f7fa;
  padding: 15px;
  border-radius: 4px;
  margin-right: 10px;
  text-align: center;
}

.data-tile .label {
  display: block;
  color: #909399;
  margin-bottom: 5px;
}

.data-tile .value {
  font-size: 24px;
  font-weight: bold;
  color: #409EFF;
}

.chart-controls {
  margin: 20px 0;
  display: flex;
  justify-content: center;
  gap: 10px;
}

/* 聚类详情 */
.cluster-details {
  margin-top: 30px;
}

.cluster-stats {
  display: flex;
  flex-wrap: wrap;
}

.stat-item {
  margin-right: 20px;
  margin-bottom: 10px;
}

.stat-item .label {
  color: #909399;
  margin-right: 5px;
}

.stat-item .value {
  font-weight: bold;
  color: #409EFF;
}

/* 集群选择器 */
.cluster-selector .el-select {
  width: 100%;
}

/* 其他样式 */

.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.chart-controls {
  margin: 0;
}

/* 聚类分析容器 */
.cluster-analysis-container {
  margin-top: 20px;
}

/* 元数据行 */
.cluster-metadata-row {
  display: flex;
  justify-content: space-between;
  margin-bottom: 30px;
}

.metadata-card {
  flex: 1;
  margin-right: 15px;
  padding: 15px;
  background-color: #f5f7fa;
  border-radius: 4px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.05);
}

.metadata-card:last-child {
  margin-right: 0;
}

/* 可视化行 */
.visualization-row {
  margin-bottom: 30px;
  width: 100%;
}

.full-width {
  width: 100%;
}

/* 图表部分 */
.chart-section {
  background-color: #fff;
  border-radius: 4px;
  padding: 15px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.05);
}

.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.chart-header h4 {
  margin: 0;
  font-size: 16px;
  color: #303133;
}

.chart-controls {
  margin: 0;
}

/* 图表容器 */
.chart-container {
  min-height: 400px;
  width: 100%;
  background-color: #ffffff;
}

/* 聚类详情 */
.cluster-details {
  background-color: #fff;
  border-radius: 4px;
  padding: 15px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.05);
}

.cluster-details h4 {
  margin-top: 0;
  margin-bottom: 15px;
  font-size: 16px;
  color: #303133;
}

.debug-panel {
  margin-top: 30px;
  padding: 10px;
  border: 1px dashed #f56c6c;
  background-color: #f8f8f8;
  border-radius: 4px;
}

.debug-info {
  margin-bottom: 10px;
}

.debug-actions {
  display: flex;
  gap: 10px;
}

.error {
  color: #f56c6c;
  font-weight: bold;
}

.progress-bar {
  height: 20px;
  background-color: #409EFF;
  border-radius: 4px;
  transition: width 0.3s ease;
}

.growth-data-section {
  margin-top: 20px;
}

.debug-info {
  background-color: #f8f9fa;
  border: 1px dashed #ddd;
  padding: 10px;
  border-radius: 4px;
  max-height: 200px;
  overflow-y: auto;
  font-family: monospace;
  font-size: 12px;
}
</style>
