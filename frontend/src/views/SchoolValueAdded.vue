<template>
  <div class="school-value-added">
    <el-card class="analysis-card">
      <template #header>
        <h2>学校增值分析</h2>
      </template>
      
      <el-form :model="form" label-width="120px" size="medium">
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="区域选择">
              <el-select v-model="form.region" placeholder="请选择区域">
                <el-option label="区域1" value="region1"></el-option>
                <el-option label="区域2" value="region2"></el-option>
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="学校类型">
              <el-select v-model="form.schoolType" placeholder="请选择学校类型">
                <el-option label="小学" value="primary"></el-option>
                <el-option label="初中" value="middle"></el-option>
                <el-option label="高中" value="high"></el-option>
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        
        <el-form-item>
          <el-button type="primary" @click="submitAnalysis" :loading="loading">开始分析</el-button>
          <el-button @click="resetForm">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script>
export default {
  name: 'SchoolValueAddedPage',
  data() {
    return {
      form: {
        region: '',
        schoolType: ''
      },
      loading: false
    }
  },
  methods: {
    submitAnalysis() {
      this.loading = true;
      setTimeout(() => {
        this.loading = false;
        this.$message.success('分析完成');
      }, 2000);
    },
    resetForm() {
      this.form = {
        region: '',
        schoolType: ''
      };
    }
  }
}
</script>

<style scoped>
.school-value-added {
  max-width: 1200px;
  margin: 0 auto;
}
.analysis-card {
  margin-bottom: 20px;
}
</style> 