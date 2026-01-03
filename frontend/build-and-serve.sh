#!/bin/bash
# Cloud Studio 生产构建+启动脚本

echo "正在构建前端..."
npm run build

echo "启动静态文件服务器..."
cd dist
python3 -m http.server 8080 --bind 0.0.0.0
