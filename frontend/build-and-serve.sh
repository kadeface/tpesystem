#!/bin/bash
# Cloud Studio 前端启动脚本

cd /workspace/frontend

echo "正在启动前端开发服务器..."
echo "工作目录: $(pwd)"
echo "端口: 8080"
echo "注意: WebSocket 已配置为指向不可达端口，避免 HTTPS/WSS 错误"

# 使用开发模式运行，WebSocket 指向不可达端口以避免 HTTPS 环境下的 WSS 错误
npx vue-cli-service serve --host 0.0.0.0 --port 8080
