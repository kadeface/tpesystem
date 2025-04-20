const { defineConfig } = require('@vue/cli-service')
module.exports = defineConfig({
  transpileDependencies: true,
  devServer: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',  // 确认Django运行端口是8000
        changeOrigin: true,
        pathRewrite: {
          '^/api': '/api'  // 保持路径不变
        },
        logLevel: 'debug'  // 增加调试日志
      }
    }
  }
})
