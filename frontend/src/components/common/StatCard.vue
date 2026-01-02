<template>
  <div class="stat-card" :style="{ borderTopColor: color }">
    <div class="stat-icon" :style="{ backgroundColor: color }">
      <el-icon><component :is="iconComponent" /></el-icon>
    </div>
    <div class="stat-content">
      <div class="stat-title">{{ title }}</div>
      <div class="stat-value">{{ value }}</div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'StatCard',
  props: {
    title: {
      type: String,
      required: true
    },
    value: {
      type: [String, Number],
      required: true
    },
    icon: {
      type: String,
      default: 'data-analysis'
    },
    color: {
      type: String,
      default: '#409EFF'
    }
  },
  computed: {
    iconComponent() {
      // 将icon字符串转换为Element Plus图标组件名
      return `el-icon-${this.icon}`;
    }
  }
};
</script>

<style scoped>
.stat-card {
  background-color: #fff;
  border-radius: 4px;
  padding: 20px;
  display: flex;
  align-items: center;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
  border-top: 3px solid;
  height: 100px;
  margin-bottom: 20px;
}

.stat-icon {
  width: 50px;
  height: 50px;
  border-radius: 50%;
  display: flex;
  justify-content: center;
  align-items: center;
  margin-right: 15px;
}

.stat-icon :deep(svg) {
  width: 24px;
  height: 24px;
  color: white;
}

.stat-content {
  flex: 1;
}

.stat-title {
  font-size: 14px;
  color: #909399;
  margin-bottom: 8px;
}

.stat-value {
  font-size: 24px;
  font-weight: bold;
  color: #303133;
}
</style> 