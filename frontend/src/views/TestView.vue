<template>
  <div class="test-page">
    <h1>年级选择器测试页面</h1>
    
    <div class="api-test">
      <h2>原始API数据测试</h2>
      <button @click="testGradesAPI">测试年级API</button>
      
      <div v-if="loading" class="loading">加载中...</div>
      
      <div v-if="gradesData" class="data-display">
        <h3>获取到{{ gradesData.length }}条年级数据</h3>
        <pre>{{ JSON.stringify(gradesData, null, 2) }}</pre>
      </div>
      
      <div v-if="error" class="error-display">
        <h3>错误信息</h3>
        <pre>{{ error }}</pre>
      </div>
    </div>
    
    <div class="selector-test">
      <h2>年级选择器组件测试</h2>
      <grade-selector @graduation-year-selected="onGraduationSelected" @grade-selected="onGradeSelected" />
      
      <div v-if="selectedData" class="selection-display">
        <h3>选择结果</h3>
        <pre>{{ JSON.stringify(selectedData, null, 2) }}</pre>
      </div>
    </div>
  </div>
</template>

<script>
import GradeSelector from '@/components/GradeSelector.vue';
import educationDataApi from '@/api/education-data';

export default {
  name: 'TestView',
  components: {
    GradeSelector
  },
  data() {
    return {
      loading: false,
      gradesData: null,
      error: null,
      selectedData: null
    }
  },
  mounted() {
    // 确保组件有访问API的能力
    this.$api = educationDataApi;
  },
  methods: {
    testGradesAPI() {
      this.loading = true;
      this.error = null;
      
      // 直接调用API
      educationDataApi.getGradesWithGraduationInfo()
        .then(response => {
          console.log('API返回数据:', response);
          this.gradesData = response.data;
        })
        .catch(err => {
          console.error('API错误:', err);
          this.error = err.toString();
        })
        .finally(() => {
          this.loading = false;
        });
    },
    
    onGraduationSelected(data) {
      console.log('选择届次:', data);
      this.selectedData = { type: 'graduation', data };
    },
    
    onGradeSelected(data) {
      console.log('选择年级:', data);
      this.selectedData = { type: 'grade', data };
    }
  }
}
</script>

<style scoped>
.test-page {
  padding: 20px;
}
.api-test, .selector-test {
  margin-bottom: 30px;
  padding: 15px;
  border: 1px solid #ddd;
  border-radius: 5px;
}
.loading {
  margin: 10px 0;
  color: #409eff;
}
.data-display, .error-display, .selection-display {
  margin-top: 10px;
  padding: 10px;
  background-color: #f5f7fa;
  border-radius: 4px;
  overflow: auto;
  max-height: 300px;
}
.error-display {
  background-color: #fff5f5;
  color: #f56c6c;
}
button {
  padding: 8px 15px;
  background-color: #409eff;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}
button:hover {
  background-color: #66b1ff;
}
pre {
  white-space: pre-wrap;
  word-break: break-all;
}
</style> 