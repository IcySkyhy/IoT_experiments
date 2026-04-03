#!/bin/bash
# entrypoint_single.sh — 单机简化版入口 (任务二/三: Docker 单机测试)
# 用法: docker run 时使用此脚本
# 需要设置环境变量 BROKER_IP，例如:
#   docker run --rm --privileged --device /dev/i2c-1:/dev/i2c-1 \
#       -e BROKER_IP=10.0.0.1 exp5-single:latest

BROKER_IP="${BROKER_IP:-10.0.0.1}"
TRANSPORT="${TRANSPORT:-mqtt}"
MOCK="${MOCK:-}"

echo "=============================="
echo " 单机打地鼠 Docker 测试"
echo " Broker: ${BROKER_IP}"
echo " Transport: ${TRANSPORT}"
echo "=============================="

EXTRA_ARGS=""
if [ -n "$MOCK" ]; then
    EXTRA_ARGS="--mock"
fi

python3 qmole_single.py \
    --broker "${BROKER_IP}" \
    --transport "${TRANSPORT}" \
    --rounds 20 \
    ${EXTRA_ARGS}
