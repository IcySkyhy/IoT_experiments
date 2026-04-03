# Dockerfile — 实验五打地鼠 Docker 镜像
# 构建: sudo docker build -t exp5:latest .
# 运行(单机测试): sudo docker run --rm --privileged --device /dev/i2c-1:/dev/i2c-1 -e BROKER_IP=10.0.0.1 exp5:latest bash entrypoint_single.sh
# 运行(完整版):   sudo docker run --rm --privileged --device /dev/i2c-1:/dev/i2c-1 -e BROKER_IP=10.0.0.1 exp5:latest

FROM python:3.7

# 设置工作目录
WORKDIR /app

# 设置 pip 清华源加速
RUN pip3 config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# 安装 Python 依赖 (无 RPi.GPIO，避免 k3s 容器兼容问题)
RUN pip3 install --no-cache-dir \
    paho-mqtt>=1.6.1 \
    smbus2 \
    spidev \
    apds9960 \
    rpi_ws281x

# 安装 QUIC 依赖 (如需 QUIC 通信)
# 构建前确保 libmsquic.so.2 在 Dockerfile 同级目录
COPY libmsquic.so.2 /usr/lib/

# 复制代码
COPY src/ /app/

# 确保入口脚本可执行
RUN chmod +x entrypoint.sh entrypoint_single.sh

# 默认环境变量
ENV BROKER_IP=10.0.0.1
ENV TRANSPORT=mqtt

# 默认入口: 完整版 (K8s 部署用)
CMD ["bash", "entrypoint.sh"]
