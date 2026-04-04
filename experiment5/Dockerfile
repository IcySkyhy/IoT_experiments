# Dockerfile — 实验五打地鼠 Docker 镜像 (适配 RDK X5 / Ubuntu 22.04 AArch64)
# 构建: sudo docker build -t exp5:latest .
# 运行(单机测试): sudo docker run --rm --privileged --device /dev/i2c-5:/dev/i2c-5 -e BROKER_IP=10.0.0.1 exp5:latest bash entrypoint_single.sh
# 运行(完整版):   sudo docker run --rm --privileged --device /dev/i2c-5:/dev/i2c-5 -e BROKER_IP=10.0.0.1 exp5:latest

# python:3.10-slim 匹配 Ubuntu 22.04 系统 Python 版本，体积更小
FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 设置 pip 清华源加速
RUN pip3 config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# 安装 Python 依赖
# 注意: 不安装 rpi_ws281x（树莓派专用，RDK 上不可用）
#       不安装 RPi.GPIO（k3s 容器内无法使用）
RUN pip3 install --no-cache-dir \
    "paho-mqtt>=1.6.1" \
    smbus2 \
    spidev \
    apds9960

# 安装 QUIC 依赖库 (64-bit AArch64 版本)
# 构建前确保以下两个文件在 Dockerfile 同级目录（从实验四复制）:
#   libmsquic.so.2.3.5  (64-bit AArch64 共享库)
#   nanomq_cli          (64-bit AArch64 可执行文件)
COPY libmsquic.so.2.3.5 /usr/lib/libmsquic.so.2.3.5
RUN ln -sf /usr/lib/libmsquic.so.2.3.5 /usr/lib/libmsquic.so.2 && ldconfig
COPY nanomq_cli /app/nanomq_cli
RUN chmod +x /app/nanomq_cli

# 复制代码
COPY src/ /app/

# 确保入口脚本可执行
RUN chmod +x entrypoint.sh entrypoint_single.sh

# 默认环境变量
ENV BROKER_IP=10.0.0.1
ENV TRANSPORT=mqtt

# 默认入口: 完整版 (K8s 部署用)
CMD ["bash", "entrypoint.sh"]
