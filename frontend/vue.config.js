const { defineConfig } = require('@vue/cli-service')
const webpack = require('webpack')
const { NormalModuleReplacementPlugin } = require('webpack')

// 环境变量：完全禁用 webpack-dev-server 客户端
process.env.WDS_SOCKET_HOST = 'localhost'
process.env.WDS_SOCKET_PORT = '9999'
process.env.WDS_SOCKET_PATH = '/no-socket'

module.exports = defineConfig({
  transpileDependencies: true,
  devServer: {
    host: '0.0.0.0',
    port: 8080,
    allowedHosts: 'all',
    hot: false,  // 禁用热模块替换
    liveReload: false,  // 禁用实时重载
    webSocketServer: false,  // 禁用 WebSocket 服务器
    client: false,  // 完全禁用客户端
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
  configureWebpack: {
    plugins: [
      new webpack.DefinePlugin({
        __VUE_PROD_DEVTOOLS__: false,
        __VUE_OPTIONS_API__: true,
        __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: false,
        // 定义环境变量禁用 WebSocket
        WDS_SOCKET_HOST: JSON.stringify('localhost'),
        WDS_SOCKET_PORT: JSON.stringify('9999')
      }),
      // 替换 webpack-dev-server 客户端模块为空模块
      new NormalModuleReplacementPlugin(
        /webpack-dev-server\/client/,
        require.resolve('./dev-server-empty.js')
      )
    ],
    resolve: {
      alias: {
        // 完全禁用 webpack-dev-server 客户端
        'webpack-dev-server/client': false
      }
    }
  }
})
