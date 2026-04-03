#!/bin/bash
# entrypoint.sh — 完整版入口 (任务四: K8s 集群部署)
# K8s 自动注入环境变量: MY_NODE_NAME, MY_POD_NAME, MY_POD_IP
# Agent ID 从 MY_NODE_NAME 自动解析 (pi1->1, pi2->2, pi3->3)

BROKER_IP="${BROKER_IP:-10.0.0.1}"
TRANSPORT="${TRANSPORT:-mqtt}"

echo "=============================="
echo " K8s 打地鼠 Agent"
echo " Broker: ${BROKER_IP}"
echo " Transport: ${TRANSPORT}"
echo " Node: ${MY_NODE_NAME}"
echo " Pod:  ${MY_POD_NAME}"
echo " IP:   ${MY_POD_IP}"
echo "=============================="

python3 qmole_agent.py \
    --broker "${BROKER_IP}" \
    --transport "${TRANSPORT}" \
    --num-agents 3
