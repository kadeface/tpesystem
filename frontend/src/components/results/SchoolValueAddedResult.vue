<template>
  <div class="school-result">
    <el-card class="result-card">
      <template #header>
        <h3>学校增值分析结果</h3>
      </template>
      
      <!-- 增值指数总览 -->
      <div id="value-added-overview" class="chart"></div>
      
      <!-- 详细数据表格 -->
      <h4>学校增值详情</h4>
      <el-table :data="schoolData" stripe style="width: 100%" height="400">
        <el-table-column prop="rank" label="排名" width="80"></el-table-column>
        <el-table-column prop="school_name" label="学校名称"></el-table-column>
        <el-table-column prop="raw_score" label="原始平均分" width="120"></el-table-column>
        <el-table-column prop="value_added" label="增值指数" width="120">
          <template #default="scope">
            <span :class="getValueClass(scope.row.value_added)">{{ scope.row.value_added }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="confidence" label="置信区间" width="150"></el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="scope">
            <el-button type="text" size="small" @click="viewSchoolDetail(scope.row)">查看详情</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script>
import * as echarts from 'echarts'

export default {
  name: 'SchoolValueAddedResult',
  props: {
    result: {
      type: Object,
      required: true
    }
  },
  data() {
    return {
      schoolData: []
    }
  },
  methods: {
    getValueClass(value) {
      if (value > 10) return 'text-success';
      if (value < -10) return 'text-danger';
      return 'text-normal';
    },
    viewSchoolDetail(school) {
      // 显示学校详情
    },
    renderCharts() {
      // 使用ECharts渲染图表
      const chart = echarts.init(document.getElementById('value-added-overview'));
      chart.setOption({
        // 图表配置
      });
    }
  },
  mounted() {
    this.schoolData = this.result.charts_data.schools || [];
    this.$nextTick(this.renderCharts);
  }
}
</script>

<style scoped>
.result-card {
  margin-bottom: 20px;
}
.chart {
  height: 400px;
  margin-bottom: 20px;
}
.text-success {
  color: #67C23A;
  font-weight: bold;
}
.text-danger {
  color: #F56C6C;
  font-weight: bold;
}
.text-normal {
  color: #409EFF;
}
</style> 