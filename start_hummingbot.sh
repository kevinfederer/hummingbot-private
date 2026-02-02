#!/bin/bash
# Hummingbot 启动脚本（带代理配置）

# 配置代理（修改为你的代理端口）
PROXY_HOST="127.0.0.1"
PROXY_PORT="7890"

# 设置代理环境变量
export http_proxy="http://${PROXY_HOST}:${PROXY_PORT}"
export https_proxy="http://${PROXY_HOST}:${PROXY_PORT}"
export all_proxy="http://${PROXY_HOST}:${PROXY_PORT}"

echo "========================================="
echo "Hummingbot 启动中..."
echo "代理设置: http://${PROXY_HOST}:${PROXY_PORT}"
echo "========================================="

# 测试网络连接
echo "测试币安API连接..."
if curl -s --connect-timeout 5 https://api.binance.com/api/v3/ping > /dev/null 2>&1; then
    echo "✓ 网络连接正常"
else
    echo "✗ 网络连接失败，请检查代理配置"
    echo "  当前代理: $http_proxy"
    read -p "按回车继续，或 Ctrl+C 取消..."
fi

# 启动 Hummingbot
cd /Users/yanyang/hummingbot-2.11.0
bin/hummingbot
