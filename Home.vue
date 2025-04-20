export default {
  data() {
    return {
      // 其他数据...
      // 添加取消令牌
      cancelTokenSource: null
    }
  },
  methods: {
    fetchRegions() {
      // 取消之前的请求（如果存在）
      if (this.cancelTokenSource) {
        this.cancelTokenSource.cancel('组件请求被取消');
      }
      
      // 创建新的取消令牌
      this.cancelTokenSource = axios.CancelToken.source();
      
      // 添加取消令牌到请求
      educationData.getRegions({}, this.cancelTokenSource.token)
        .then(response => {
          this.regions = response.data;
        })
        .catch(error => {
          if (!axios.isCancel(error)) {
            console.error('获取区域数据失败:', error);
          }
        });
    }
  },
  // 组件销毁时取消未完成的请求
  beforeDestroy() {
    if (this.cancelTokenSource) {
      this.cancelTokenSource.cancel('组件已卸载');
    }
  }
} 