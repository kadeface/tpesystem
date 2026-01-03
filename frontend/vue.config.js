const { defineConfig } = require('@vue/cli-service')

// 通过环境变量检测是否在 Cloud Studio 中
const isCloudStudio = process.env.CLOUD_STUDIO === '1';

module.exports = defineConfig({
  transpileDependencies: true,
  devServer: {
    host: '0.0.0.0',
    port: 8080,
    allowedHosts: 'all',
    hot: !isCloudStudio,
    liveReload: !isCloudStudio,
    // 使用空字符串来禁用 WebSocket
    client: {
      overlay: false
    },
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        pathRewrite: {
          '^/api': '/api'
        },
        logLevel: 'debug'
      }
    }
  },
  // 通过 chainWebpack 完全移除 WebSocket 客户端代码
  chainWebpack: config => {
    if (isCloudStudio) {
      // 移除 webpack-dev-server 的客户端入口
      config.devServer.set('client', {
        webSocketURL: 'ws://localhost:0'
      });
    }
  }
})
