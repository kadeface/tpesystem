#!/bin/bash
# Cloud Studio 前端启动脚本
# 设置环境变量禁用 WebSocket 以避免 HTTPS/HTTP 混合内容错误

# 禁用 webpack-dev-server 客户端注入
export WDS_SOCKET_PORT=""
export WDS_SOCKET_HOST=""

PORT=8080 npm run serve -- --host 0.0.0.0 --no-hot
