<template>
  <div>
    <h1>区域列表</h1>
    <ul>
      <li v-for="region in regions" :key="region.region_id">
        {{ region.region_name }}
      </li>
    </ul>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, onMounted } from 'vue';
import axios from 'axios';

export default defineComponent({
  name: 'RegionList',
  setup() {
    const regions = ref([]);

    onMounted(async () => {
      const response = await axios.get('/api/regions/');
      regions.value = response.data;
    });

    return { regions };
  },
});
</script> 