<template>
  <div>
    <h2>学校管理</h2>
    
    <!-- 搜索和过滤区域 -->
    <div class="filter-container">
      <el-input
        v-model="searchQuery"
        placeholder="搜索学校名称"
        class="search-input"
        @input="fetchSchools"
      />
      
      <el-select v-model="selectedRegion" placeholder="选择区域" @change="fetchSchools">
        <el-option
          v-for="region in regions"
          :key="region.region_id"
          :label="region.region_name"
          :value="region.region_id"
        />
      </el-select>
      
      <el-select v-model="selectedType" placeholder="学校类型" @change="fetchSchools">
        <el-option label="全部" value="" />
        <el-option label="小学" value="PRIMARY" />
        <el-option label="初中" value="JUNIOR" />
        <el-option label="高中" value="HIGH" />
      </el-select>
    </div>
    
    <!-- 学校列表 -->
    <el-table :data="schools" style="width: 100%">
      <el-table-column prop="school_id" label="学校编号" width="120" />
      <el-table-column prop="school_name" label="学校名称" />
      <el-table-column prop="school_type" label="学校类型">
        <template #default="scope">
          {{ schoolTypeMap[scope.row.school_type] }}
        </template>
      </el-table-column>
      <el-table-column prop="principal" label="校长" />
      <el-table-column label="操作">
        <template #default="scope">
          <el-button size="small" @click="viewDetails(scope.row)">查看</el-button>
          <el-button size="small" type="primary" @click="editSchool(scope.row)">编辑</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, onMounted } from 'vue';
import axios from 'axios';

export default defineComponent({
  name: 'SchoolList',
  setup() {
    const schools = ref([]);
    const regions = ref([]);
    const searchQuery = ref('');
    const selectedRegion = ref('');
    const selectedType = ref('');
    
    const schoolTypeMap = {
      'PRIMARY': '小学',
      'JUNIOR': '初中',
      'HIGH': '高中'
    };

    const fetchSchools = async () => {
      let url = '/api/schools/';
      const params = {};
      
      if (searchQuery.value) {
        params.search = searchQuery.value;
      }
      
      if (selectedRegion.value) {
        params.region = selectedRegion.value;
      }
      
      if (selectedType.value) {
        params.school_type = selectedType.value;
      }
      
      const response = await axios.get(url, { params });
      schools.value = response.data;
    };
    
    const fetchRegions = async () => {
      const response = await axios.get('/api/regions/');
      regions.value = response.data;
    };
    
    const viewDetails = (school) => {
      // 实现查看学校详情的功能
      console.log('查看学校：', school);
    };
    
    const editSchool = (school) => {
      // 实现编辑学校的功能
      console.log('编辑学校：', school);
    };

    onMounted(() => {
      fetchSchools();
      fetchRegions();
    });

    return { 
      schools, 
      regions, 
      searchQuery, 
      selectedRegion, 
      selectedType,
      schoolTypeMap,
      fetchSchools,
      viewDetails,
      editSchool
    };
  },
});
</script>

<style scoped>
.filter-container {
  margin-bottom: 20px;
  display: flex;
  gap: 10px;
}

.search-input {
  width: 200px;
}
</style> 