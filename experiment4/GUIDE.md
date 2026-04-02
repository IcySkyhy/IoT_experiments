# 实验四完整操作指南

> 环境：云服务器（Ubuntu 22.04）+ RDK（Linux ARM）  
> IP 约定：云服务器 VPN 地址 `10.0.0.1`，RDK VPN 地址 `10.0.0.x`

---

## 目录

1. [WireGuard VPN 开机自启](#1-wireguard-vpn-开机自启)
2. [云服务器：安装 Docker 并启动 EMQX](#2-云服务器安装-docker-并启动-emqx)
3. [RDK：准备 NanoMQ 客户端](#3-rdk准备-nanomq-客户端)
4. [验证 QUIC 连通性](#4-验证-quic-连通性)
5. [运行打地鼠程序](#5-运行打地鼠程序)
6. [延迟对比测试（TCP vs QUIC）](#6-延迟对比测试tcp-vs-quic)
7. [绘图与查看结果](#7-绘图与查看结果)

---

## 1. WireGuard VPN 开机自启

WireGuard 的 systemd 服务模板名为 `wg-quick@<接口名>`，接口名对应 `/etc/wireguard/<接口名>.conf`。

**在云服务器和每台 RDK 上分别执行：**

```bash
# 若未安装 wireguard-tools 先安装
sudo apt install -y wireguard-tools

# 启用开机自启（wg0 对应 /etc/wireguard/wg0.conf）
sudo systemctl enable wg-quick@wg0

# 立即启动（当前会话生效，无需重启）
sudo systemctl start wg-quick@wg0

# 查看运行状态（应显示 active (exited) 或 active (running)）
sudo systemctl status wg-quick@wg0
```

验证 VPN 连通：

```bash
# 从 RDK ping 云服务器 VPN 地址
ping 10.0.0.1

# 从云服务器 ping RDK VPN 地址
ping 10.0.0.2
```

> **常见问题**：若 `systemctl status` 报 `Unit not found`，检查 `/etc/wireguard/wg0.conf` 是否存在；  
> 若报 `Permission denied`，检查文件权限：`sudo chmod 600 /etc/wireguard/wg0.conf`。

---

## 2. 云服务器：安装 Docker 并启动 EMQX

### 2.1 安装 Docker

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
     -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
     docker-buildx-plugin docker-compose-plugin
```

如果是非 root 用户，将自己加入 docker 组（**之后需重新登录生效**）：

```bash
sudo groupadd docker 2>/dev/null || true
sudo usermod -aG docker $USER
# 退出并重新登录，或 newgrp docker 使当前 shell 生效
newgrp docker
```

验证：

```bash
docker run hello-world
```

> **拉取失败时配置镜像加速：**
> ```bash
> sudo tee /etc/docker/daemon.json <<'EOF'
> {
>   "registry-mirrors": [
>     "https://docker.mirrors.ustc.edu.cn",
>     "https://docker.nju.edu.cn",
>     "https://docker.m.daocloud.io"
>   ]
> }
> EOF
> sudo systemctl daemon-reload
> sudo systemctl restart docker
> ```

### 2.2 启动 EMQX（含 QUIC 支持）

```bash
docker run -d --name emqx \
  -p 1883:1883 \
  -p 8083:8083 \
  -p 8084:8084 \
  -p 8883:8883 \
  -p 18083:18083 \
  -p 14567:14567/udp \
  -e EMQX_LISTENERS__QUIC__DEFAULT__keyfile="etc/certs/key.pem" \
  -e EMQX_LISTENERS__QUIC__DEFAULT__certfile="etc/certs/cert.pem" \
  -e EMQX_LISTENERS__QUIC__DEFAULT__ENABLED=true \
  emqx/emqx:5.5.0
```

查看是否正常运行：

```bash
docker ps
# 应看到 emqx 容器，Status 为 Up
```

+++++++++++++++++++++++++++++++++++++++++++++++++++++

EMQX 5.8.9 本地安装，QUIC 未启用。需要在配置文件中加入 QUIC 监听器。

**第一步：确认默认证书存在**

```bash
ls /etc/emqx/certs/
```

应该看到 `cert.pem` 和 `key.pem`（EMQX 自带自签名证书）。

**第二步：在配置文件末尾追加 QUIC 监听器**

```bash
sudo tee -a /etc/emqx/emqx.conf <<'EOF'

listeners.quic.default {
  enabled = true
  bind = "0.0.0.0:14567"
  ssl_options {
    keyfile  = "/etc/emqx/certs/key.pem"
    certfile = "/etc/emqx/certs/cert.pem"
  }
}
EOF
```

**第三步：重启 EMQX 使配置生效**

```bash
sudo systemctl restart emqx
# 等待约 10 秒
sudo systemctl status emqx
```

**第四步：验证 QUIC 端口已监听**

```bash
sudo ss -ulnp | grep 14567
```

应看到类似 `UNCONN 0 0 0.0.0.0:14567` 的输出。


++++++++++++++++++++++++++++++++++++++++++++++++++++++++

## 3. RDK：准备 NanoMQ 客户端

> **背景**：`nanomq_cli` 是 **32-bit ARM (armhf)** 编译的二进制，运行在 AArch64 Ubuntu 上需要额外安装 32-bit 兼容库。

在每台 RDK 上按顺序执行：

```bash
# 1. 进入实验目录
cd ~/hajicar/experiment/experiment4   # 按实际路径调整

# 2. 赋予执行权限
chmod +x nanomq_cli

# 3. 启用 armhf 多架构支持（32-bit ARM 兼容层）
sudo dpkg --add-architecture armhf
sudo apt update

# 4. 安装 32-bit ARM 运行时库
sudo apt install -y libc6:armhf libstdc++6:armhf libatomic1:armhf

# 5. 将 libmsquic.so.2 复制到 armhf 库目录（不是 /usr/lib/）
sudo cp libmsquic.so.2 /lib/arm-linux-gnueabihf/

# 6. 刷新动态链接库缓存
sudo ldconfig

# 7. 验证 nanomq_cli 可以运行
./nanomq_cli --help
```

看到帮助输出即表示准备完成。

```bash
# 8. 安装 Python 依赖（TCP 通信和绘图所需）
pip install -r requirements.txt
```

---

## 4. 验证 QUIC 连通性

在两台 RDK 上分别测试发布和订阅，确认 QUIC 链路正常。

**RDK A（订阅）：**

```bash
./nanomq_cli sub -h 10.0.0.1 -p 14567 -t test -q 2 -l --quic
```

**RDK B（发布）：**

```bash
# 运行后在终端输入 hello 并回车，RDK A 应收到该消息
./nanomq_cli pub -h 10.0.0.1 -p 14567 -t test -q 2 -l --quic
```

看到 RDK A 收到 `hello` 即表示 QUIC 链路正常。按 `Ctrl+C` 退出。

---

## 5. 运行打地鼠程序

### 5.1 有实体硬件（LED + APDS9960 传感器）

在 3 台 RDK 上分别打开终端，**依次**运行：

```bash
# RDK 1
python3 qmole_agent.py --transport quic --broker 10.0.0.1 \
  --quic-port 14567 --id 1 --num-agents 3

# RDK 2
python3 qmole_agent.py --transport quic --broker 10.0.0.1 \
  --quic-port 14567 --id 2 --num-agents 3

# RDK 3
python3 qmole_agent.py --transport quic --broker 10.0.0.1 \
  --quic-port 14567 --id 3 --num-agents 3
```

等所有 Agent 启动后，在**任意一台 RDK** 上触发第一个地鼠：

```bash
python3 qmole_trigger.py --transport quic --broker 10.0.0.1 \
  --quic-port 14567 --target 1 --mole-type 1
```

### 5.2 无硬件（纯软件仿真，加 `--mock`）

```bash
# 终端 1
python3 qmole_agent.py --transport quic --broker 10.0.0.1 \
  --id 1 --num-agents 3 --mock

# 终端 2
python3 qmole_agent.py --transport quic --broker 10.0.0.1 \
  --id 2 --num-agents 3 --mock

# 终端 3（触发）
python3 qmole_trigger.py --transport quic --broker 10.0.0.1 \
  --quic-port 14567 --target 1
```

### 5.3 TCP 模式对照（experiment2 ZMQ broker 替换为 EMQX TCP）

```bash
python3 qmole_agent.py --transport mqtt --broker 10.0.0.1 \
  --tcp-port 1883 --id 1 --num-agents 3 --mock
```

---

## 6. 延迟对比测试（TCP vs QUIC）

### 方法 A：使用 test_timing.py（与实验手册完全一致）

**前提**：云服务器 EMQX 已运行（QUIC 用），experiment2 broker.py 已在云端运行（TCP/ZMQ 用）。

测试 TCP（ZMQ）延迟，在 RDK 上运行：

```bash
python3 test_timing.py 100000 zmq-tcp
# 将每秒发一条 payload=100000 字节的包，输出往返时间均值/中位数/标准差
```

测试 QUIC 延迟，在 RDK 上运行（**一条命令，三段 pipe**）：

```bash
./nanomq_cli sub -h 10.0.0.1 -p 14567 -t test -q 2 -l --quic \
  | python3 test_timing.py 100000 quic \
  | ./nanomq_cli pub -h 10.0.0.1 -p 14567 -t test -q 2 -l --quic
```

> `test_timing.py` 会在 stderr 输出统计结果，stdout 为待发送消息（pipe 给 pub）。  
> 可将 `100000` 改为 `1000`、`10000`、`1000000` 等多个值，分别测试和记录。

### 方法 B：使用 latency_probe.py（支持多维度批量测试）

**云服务器**上启动 echo 端（每个协议各一个，保持运行）：

```bash
# 终端 1：QUIC echo
python3 latency_probe.py --role echo --protocol mqtt-quic \
  --broker 10.0.0.1 --quic-port 14567 --active-id rdk1

# 终端 2：TCP echo
python3 latency_probe.py --role echo --protocol mqtt-tcp \
  --broker 10.0.0.1 --tcp-port 1883 --active-id rdk1
```

**RDK** 上批量主动测试：

```bash
python3 latency_dual_runner.py \
  --broker 10.0.0.1 \
  --tcp-port 1883 --quic-port 14567 \
  --protocols mqtt-tcp,mqtt-quic \
  --payloads 64,512,1024,100000 \
  --qos-levels 0,1,2 \
  --seconds 8 \
  --tag exp4 \
  --out latency_results.csv
```

---

## 7. 绘图与查看结果

```bash
python3 plot_latency.py --csv latency_results.csv --out-dir charts
```

生成文件：

| 文件 | 内容 |
|---|---|
| `charts/summary.csv` | 各组合的 mean/median/std/p95 汇总 |
| `charts/box_payload.png` | 不同 payload 下各协议的延迟箱线图 |
| `charts/line_payload.png` | 延迟 vs payload 折线图 |

查看 summary（SSH 无桌面时直接打印）：

```bash
python3 -c "import pandas as pd; print(pd.read_csv('charts/summary.csv').to_string())"
```

---

## 常见问题

| 现象 | 原因 | 解决 |
|---|---|---|
| `./nanomq_cli: error while loading shared libraries: libmsquic.so.2` | 库文件未复制 | `sudo cp libmsquic.so.2 /usr/lib/` |
| `Permission denied: ./nanomq_cli` | 无执行权限 | `chmod +x ./nanomq_cli` |
| QUIC 发布消息后对端无反应 | JSON 含空格被截断（旧版 bug，已修复） | 确认 `qmole_common.py` 已更新 |
| `docker: cannot connect to daemon` | 未加入 docker 组 | `newgrp docker` 或重新登录 |
| `wg-quick@wg0: Unit not found` | wireguard-tools 未安装 | `sudo apt install wireguard-tools` |
| VPN ping 不通但 wg0 已 up | 对端 AllowedIPs 或防火墙未放行 | 检查 wg0.conf 的 AllowedIPs 和云端安全组 UDP 51820 |
