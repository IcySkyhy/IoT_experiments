# 实验五 · Docker & Kubernetes 部署打地鼠游戏

> **完整实验指南** — 本文档覆盖任务一至任务四，以及两个选做任务的全部操作步骤。
> 每一步均注明了 **在哪台设备上执行**、**执行什么命令**、**预期看到什么输出**。

---

## 目录

- [一、代码文件说明](#一代码文件说明)
- [二、任务一至四的执行步骤](#二任务一至四的执行步骤)
  - [任务一：在 RDK 上安装 Docker](#任务一在-rdk-上安装-docker)
  - [任务二：编写 Dockerfile 并构建 Docker 镜像](#任务二编写-dockerfile-并构建-docker-镜像)
  - [任务三：使用 Docker 运行打地鼠代码](#任务三使用-docker-运行打地鼠代码)
  - [任务四：设置 Kubernetes 集群并部署完整版打地鼠](#任务四设置-kubernetes-集群并部署完整版打地鼠)
- [三、验收要求的执行步骤](#三验收要求的执行步骤)
  - [验收 1：通过 docker run 运行单机简化打地鼠程序](#验收-1通过-docker-run-运行单机简化打地鼠程序)
  - [验收 2：搭建 k3s 集群，kubectl get pods 查看状态](#验收-2搭建-k3s-集群kubectl-get-pods-查看状态)
  - [验收 3：在 k3s 集群中运行打地鼠游戏](#验收-3在-k3s-集群中运行打地鼠游戏)
  - [验收 4：Docker 内存占用对比](#验收-4docker-内存占用对比)
  - [选做 1：分数收集程序，封装为镜像，Pod 在云服务器运行](#选做-1分数收集程序封装为镜像pod-在云服务器运行)
  - [选做 2：Kubernetes Service 公网访问 Web 页面](#选做-2kubernetes-service-公网访问-web-页面)
- [四、常用命令速查](#四常用命令速查)

---

## 一、代码文件说明

### 目录结构

```text
experiment5/
├── Dockerfile                  # [A] 主镜像构建文件 (agent 打地鼠)
├── Dockerfile.collector        # [B] 选做任务镜像构建文件 (分数收集器)
├── exp5.yaml                   # [C] K8s 部署文件 (3 个 agent Pod 分配到 3 个 RDK)
├── exp5-collector.yaml         # [D] 选做任务 K8s 部署文件 (Deployment + Service)
├── libmsquic.so.2              # [E] QUIC 通信库 (从实验四复制而来)
├── README.md                   # [F] 本文档
└── src/
    ├── qmole_common.py         # [1] 通信与硬件抽象层
    ├── qmole_agent.py          # [2] 完整版打地鼠 Agent (支持 K8s 自动 ID)
    ├── qmole_trigger.py        # [3] 游戏触发器 (发送首条 activate 消息)
    ├── qmole_single.py         # [4] 单机简化版打地鼠 (任务二/三验证用)
    ├── score_collector.py      # [5] 选做: 分数收集 + Web 展示服务
    ├── entrypoint.sh           # [6] 完整版入口脚本 (K8s 部署时使用)
    ├── entrypoint_single.sh    # [7] 单机简化版入口脚本 (Docker 测试时使用)
    └── requirements.txt        # [8] Python 依赖列表
```

### 各文件详细说明

#### [1] src/qmole_common.py — 通信与硬件抽象层

提供所有打地鼠程序共用的底层功能：

- **TransportConfig**: 数据类，保存 broker 地址、端口、传输模式 (mqtt/quic)、QoS 等配置。
- **MqttClient**: 基于 paho-mqtt 的 MQTT TCP 客户端封装，提供 connect/subscribe/publish/close 方法。
- **QuicClient / NanoMQCliSub**: 基于 nanomq_cli 外部命令的 MQTT QUIC 客户端封装（通过子进程调用 nanomq_cli 进行 QUIC 通信）。
- **Transport**: 工厂类，根据 TransportConfig.mode 自动选择使用 MqttClient 或 QuicClient。
- **Heartbeat**: 后台线程，每 2 秒向 `mole/heartbeat/<agent_id>` 主题发送 "alive" 心跳。
- **MockLED / MockSensor**: 模拟硬件，在没有实际 LED 灯带/传感器时使用（在终端打印代替真实操作）。
- **Debounce**: 简单的去抖计时器，防止传感器短时间内重复触发。

> **注意**: 本文件相比实验四版本，已移除对 RPi.GPIO 的依赖，因为 RPi.GPIO 在 k3s 创建的容器中运行时会报错。

#### [2] src/qmole_agent.py — 完整版打地鼠 Agent

3 台 RDK 协作运行的打地鼠程序。**核心改动**：

- **resolve_agent_id() 函数**: 自动从 Kubernetes 注入的环境变量 MY_NODE_NAME 中提取 Agent ID。例如 MY_NODE_NAME="pi1" 则 agent_id=1，"pi2" 则 agent_id=2，"pi3" 则 agent_id=3。如果没有 K8s 环境变量（比如在 Docker 单机运行时），也可以通过 --id 手动指定。
- **无 RPi.GPIO**: 传感器仅用 apds9960 + smbus2，LED 仅用 spidev（WS2812 SPI 协议），彻底避免容器兼容问题。
- **游戏逻辑**: 收到 activate 消息 → LED 亮起（绿色=真地鼠、红色=假地鼠）→ 传感器轮询 → 命中/超时 → LED 熄灭 → 随机选下一个 agent 发送 activate → 循环。

#### [3] src/qmole_trigger.py — 游戏触发器

向指定 Agent 发送一条 activate 消息来启动游戏。只需运行一次即可触发整个游戏循环。三个 Agent 之间会自动互相传递 activate 消息。

#### [4] src/qmole_single.py — 单机简化版打地鼠

任务二/三用于快速验证 Docker 封装正确性的单机版本：

- 只在一台 RDK 上运行，不需要其他节点参与。
- Agent 自己给自己发 activate（自我对局）。
- 验证传感器读取、LED 控制、MQTT 通信三项功能均正常。
- 运行指定轮数后自动退出（默认 10 轮）。

#### [5] src/score_collector.py — 分数收集 + Web 展示（选做）

- 订阅 `mole/activate/#` 和 `mole/heartbeat/#` 主题，收集所有 Agent 的游戏状态和分数。
- 内嵌 HTTP 服务器（纯 Python http.server，无额外框架依赖），提供实时 Web 页面。
- 页面显示：运行时间、总回合数、各节点分数、在线状态等。
- 提供 /api/state JSON API 接口。
- 页面每 3 秒自动刷新。

#### [6] src/entrypoint.sh — 完整版入口脚本

K8s 部署时容器的默认入口。它从环境变量读取 BROKER_IP 和 TRANSPORT，然后调用 qmole_agent.py。Agent ID 由 qmole_agent.py 自动从 MY_NODE_NAME 解析。

#### [7] src/entrypoint_single.sh — 单机简化版入口脚本

Docker 单机测试时的入口。调用 qmole_single.py，可通过环境变量 MOCK=1 启用模拟硬件模式。

#### [A] Dockerfile — 主镜像构建文件

- 基于 python:3.7 基础镜像。
- 通过清华 pip 源安装 Python 依赖（paho-mqtt, smbus2, spidev, apds9960, rpi_ws281x），不安装 RPi.GPIO。
- 复制 libmsquic.so.2 到容器的 /usr/lib/（支持 QUIC 通信）。
- 复制 src/ 下所有代码到容器的 /app/。
- 默认入口为 entrypoint.sh（完整版）。

#### [B] Dockerfile.collector — 选做任务镜像构建文件

- 基于轻量的 python:3.7-slim 镜像（体积更小）。
- 只安装 paho-mqtt（分数收集器只需要 MQTT 订阅和 HTTP 服务，不需要硬件库）。
- 只复制 score_collector.py 一个文件。
- 暴露 8080 端口。

#### [C] exp5.yaml — K8s 部署文件

定义一个 Deployment，包含 3 个 Pod 副本：

- **tolerations**: 容忍 key1=value1:NoSchedule 标记。
- **podAntiAffinity**: 确保每个 RDK 节点上只运行 1 个 Pod（不同 Pod 必须在不同 hostname 上）。
- 容器以 privileged 模式运行，映射 /dev/i2c-1 设备（传感器需要）。
- 通过环境变量注入 BROKER_IP、TRANSPORT、MY_POD_NAME、MY_POD_IP、MY_NODE_NAME。

#### [D] exp5-collector.yaml — 选做任务 K8s 部署文件

包含两个 K8s 对象：

- **Deployment**: 1 个 Pod 副本，通过 nodeSelector 强制调度到 server 节点。
- **Service (NodePort)**: 将容器的 8080 端口映射到集群所有节点的 30080 端口，允许公网访问。

---

## 二、任务一至四的执行步骤

### 环境约定

| 设备 | 说明 | VPN IP |
|------|------|--------|
| 云服务器 | Ubuntu 22.04，运行 MQTT broker (NanoMQ/EMQX)、k3s server | 10.0.0.1 |
| RDK-1 (pi1) | RDK X5，带 APDS9960 传感器 + WS2812 LED | 10.0.0.2 |
| RDK-2 (pi2) | RDK X5，带 APDS9960 传感器 + WS2812 LED | 10.0.0.3 |
| RDK-3 (pi3) | RDK X5，带 APDS9960 传感器 + WS2812 LED | 10.0.0.4 |

> 如果你的 IP 或节点名称不同，请在下方所有命令中做对应替换。

---

### 任务一：在 RDK 上安装 Docker

> 操作设备: **每台 RDK**（pi1、pi2、pi3），通过 SSH 连接。

#### 步骤 1.1：SSH 连接到 RDK

```bash
ssh pi@10.0.0.2
```

> 依次对 pi2(10.0.0.3) 和 pi3(10.0.0.4) 重复以下全部步骤。

#### 步骤 1.2：安装 Docker

**方式一：官方脚本安装（推荐先试这个）**

```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
```

**方式二：清华源手动安装（如果方式一报错"不支持 Raspbian Buster"）**

先修改 APT 源：

```bash
sudo vim /etc/apt/sources.list
```

将内容替换为：

```text
deb http://mirrors.tuna.tsinghua.edu.cn/raspbian/raspbian/ buster main non-free contrib rpi
deb-src http://mirrors.tuna.tsinghua.edu.cn/raspbian/raspbian/ buster main non-free contrib rpi
```

保存退出（Vim 操作：按 Esc，输入 :wq，回车）。

安装依赖工具：

```bash
sudo apt update
sudo apt install -y apt-transport-https ca-certificates curl gnupg2
```

添加 Docker GPG 密钥：

```bash
curl -fsSL https://download.docker.com/linux/debian/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
```

添加 Docker 清华源：

```bash
echo "deb [arch=armhf signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://mirrors.tuna.tsinghua.edu.cn/docker-ce/linux/debian buster stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
```

安装 Docker：

```bash
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io
```

验证安装：

```bash
sudo docker run --rm hello-world
```

如果看到 "Hello from Docker!" 则安装成功。如果报错拉取镜像失败，需要配置 Docker 镜像加速器（参考实验四指导书）。

#### 步骤 1.3：解决时间同步问题

添加 testing 仓库：

```bash
echo "deb http://raspbian.raspberrypi.org/raspbian/ testing main" | sudo tee -a /etc/apt/sources.list
```

设置 testing 仓库低优先级：

```bash
echo 'Package: *
Pin: release a=testing
Pin-Priority: 150' | sudo tee /etc/apt/preferences.d/testing
```

更新并安装新版 libseccomp2：

```bash
sudo apt update
sudo apt install libseccomp2/testing
```

如果上面报错，手动下载安装：

```bash
wget http://archive.raspbian.org/raspbian/pool/main/libs/libseccomp/libseccomp2_2.5.4-1%2Brpi1%2Bdeb12u1_armhf.deb
sudo dpkg -i libseccomp2_2.5.4-1+rpi1+deb12u1_armhf.deb
```

#### 步骤 1.4：测试时间同步

```bash
sudo docker run --rm ubuntu date
date
```

对比这两个时间输出，如果相差在几秒内则时间同步正常。

#### 步骤 1.5：非 root 用户使用 Docker

```bash
sudo usermod -aG docker pi
```

**退出 SSH 并重新登录**（这一步必须做，否则组更改不会生效）：

```bash
exit
ssh pi@10.0.0.2
```

验证不需要 sudo 就能运行 docker：

```bash
docker ps
```

如果不报 "permission denied" 则配置成功。

> **重要**: 以上步骤 1.2 ~ 1.5 需要在 pi1、pi2、pi3 每台 RDK 上都执行一遍。

---

### 任务二：编写 Dockerfile 并构建 Docker 镜像

> 操作设备: **任意一台 RDK**（以 pi1 为例），只需在一台上操作。

#### 步骤 2.1：将代码上传到 RDK

在你的 **本地电脑（Windows PowerShell）** 上执行：

```powershell
scp -r "C:\Users\12447\Desktop\交叉\hajicar\experiment\experiment5" pi@10.0.0.2:~/
```

> 如果 scp 速度慢，也可以使用 WinSCP 等图形化工具。

#### 步骤 2.2：SSH 连接到 pi1

```bash
ssh pi@10.0.0.2
```

#### 步骤 2.3：确保 libmsquic.so.2 存在

```bash
cd ~/experiment5
ls -la libmsquic.so.2
```

如果文件不存在，从实验四目录复制：

```bash
cp ~/experiment4/libmsquic.so.2 ~/experiment5/
```

> 如果实验四的目录路径不同，请调整为你的实际路径。

#### 步骤 2.4：确认文件结构完整

```bash
ls ~/experiment5/
```

应看到：

```text
Dockerfile  Dockerfile.collector  exp5-collector.yaml  exp5.yaml  libmsquic.so.2  README.md  src
```

```bash
ls ~/experiment5/src/
```

应看到：

```text
entrypoint.sh  entrypoint_single.sh  qmole_agent.py  qmole_common.py  qmole_single.py  qmole_trigger.py  requirements.txt  score_collector.py
```

#### 步骤 2.5：构建 Docker 镜像

```bash
cd ~/experiment5
sudo docker build -t exp5:latest .
```

**预期输出**：构建过程逐步执行 Dockerfile 中的每条指令。最后几行应显示：

```text
Successfully built xxxxxxxxxxxx
Successfully tagged exp5:latest
```

首次构建约 5-10 分钟（主要是下载 Python 3.7 基础镜像和 pip 安装依赖）。后续修改代码后重新构建会很快（Docker 缓存机制）。

#### 步骤 2.6：验证镜像已构建

```bash
docker images
```

应看到：

```text
REPOSITORY   TAG       IMAGE ID       CREATED          SIZE
exp5         latest    xxxxxxxxxxxx   10 seconds ago   xxx MB
```

---

### 任务三：使用 Docker 运行打地鼠代码

> 操作设备: **pi1**（构建镜像的那台 RDK）。

#### 步骤 3.1：确保云服务器 MQTT broker 在运行

SSH 到 **云服务器**：

```bash
ssh root@<云服务器公网IP>
```

确认 broker 正在运行：

```bash
# 如果用的是 EMQX:
sudo docker ps | grep emqx

# 如果用的是 NanoMQ:
ps aux | grep nanomq
```

如果 broker 没在运行，启动它：

```bash
# EMQX:
sudo docker start emqx

# 或 NanoMQ:
sudo nanomq start
```

确认后回到 pi1 的 SSH 窗口。

#### 步骤 3.2：确保 VPN 连接正常

在 pi1 上：

```bash
sudo wg-quick up wg0
ping -c 3 10.0.0.1
```

应看到 3 packets transmitted, 3 received（ping 通）。

#### 步骤 3.3：运行单机简化版打地鼠（真实硬件）

```bash
sudo docker run --rm --privileged \
    --device /dev/i2c-1:/dev/i2c-1 \
    -e BROKER_IP=10.0.0.1 \
    --name exp5-test \
    exp5:latest bash entrypoint_single.sh
```

**命令各部分解释**：

| 参数 | 作用 |
|------|------|
| docker run | 启动新容器 |
| --rm | 容器退出后自动删除 |
| --privileged | 赋予容器访问所有设备的权限（GPIO/SPI/I2C） |
| --device /dev/i2c-1:/dev/i2c-1 | 将 I2C 设备映射到容器内（APDS9960 传感器需要） |
| -e BROKER_IP=10.0.0.1 | 设置环境变量，指定 MQTT broker 地址 |
| --name exp5-test | 给容器命名为 exp5-test |
| exp5:latest | 使用刚才构建的镜像 |
| bash entrypoint_single.sh | 覆盖默认入口，使用单机版入口脚本 |

**预期输出**：

```text
==============================
 单机打地鼠 Docker 测试
 Broker: 10.0.0.1
 Transport: mqtt
==============================
=== 单机打地鼠测试启动 (broker=10.0.0.1, transport=mqtt) ===
=== 传感器: 硬件 ===
=== LED: 硬件 ===
[单机] 真地鼠出现！
  命中真地鼠 +1，总分 1
[单机] 假地鼠出现！
  成功躲开假地鼠，总分 1
...
=== 10 轮结束，最终得分: 7 ===
=== 单机测试完成 ===
```

在程序运行期间，RDK 上的 LED 灯带应该会亮起（绿色=真地鼠，红色=假地鼠）。

#### 步骤 3.4：可选 — 用模拟模式测试（无需硬件）

如果暂时没有硬件或想快速测试 Docker 封装是否正确：

```bash
sudo docker run --rm \
    -e BROKER_IP=10.0.0.1 \
    -e MOCK=1 \
    --name exp5-test \
    exp5:latest bash entrypoint_single.sh
```

模拟模式下不需要 --privileged 和 --device，输出中会显示 `传感器: 模拟` 和 `LED: 模拟`。

按 Ctrl+C 可随时停止容器。

---

### 任务四：设置 Kubernetes 集群并部署完整版打地鼠

#### 步骤四-1：安装 k3s

##### 步骤 4.1.1：确保 VPN 连接

> 操作设备: **云服务器 + 每台 RDK**。

在云服务器上：

```bash
sudo wg-quick up wg0
```

在每台 RDK 上：

```bash
sudo wg-quick up wg0
```

验证互通（在各设备上互 ping）：

```bash
# 在 RDK 上 ping 云服务器
ping -c 3 10.0.0.1

# 在云服务器上 ping 每台 RDK
ping -c 3 10.0.0.2
ping -c 3 10.0.0.3
ping -c 3 10.0.0.4
```

所有 ping 都应成功（0% packet loss）。

##### 步骤 4.1.2：在云服务器上安装 k3s server

> 操作设备: **云服务器**。

```bash
ssh root@<云服务器公网IP>
```

**方式一：在线安装**

```bash
curl -sfL https://rancher-mirror.oss-cn-beijing.aliyuncs.com/k3s/k3s-install.sh | INSTALL_K3S_MIRROR=cn K3S_NODE_NAME=server sh -
```

**方式二：离线安装（如果方式一网络不通或报错）**

```bash
wget https://rancher-mirror.rancher.cn/k3s/k3s-install.sh
wget https://rancher-mirror.rancher.cn/k3s/v1.30.2-k3s2/k3s
sudo chmod a+x ./k3s ./k3s-install.sh
sudo cp ./k3s /usr/local/bin
INSTALL_K3S_MIRROR=cn K3S_NODE_NAME=server INSTALL_K3S_SKIP_DOWNLOAD=true ./k3s-install.sh
```

##### 步骤 4.1.3：设置 k3s server 使用 VPN IP

> 操作设备: **云服务器**。

由于云服务器可能有多个 IP（公网、内网、VPN），需要指定使用 VPN IP。

```bash
sudo vim /etc/systemd/system/k3s.service
```

找到 ExecStart= 开头的行，修改为（注意末尾的反斜杠 \ 表示续行）：

```text
ExecStart=/usr/local/bin/k3s \
   server \
   --node-ip 10.0.0.1 \
   --advertise-address 10.0.0.1 \
```

保存退出后重启 k3s：

```bash
sudo systemctl daemon-reload
sudo systemctl restart k3s
```

##### 步骤 4.1.4：验证 k3s server 运行

> 操作设备: **云服务器**。

```bash
kubectl get nodes
```

**预期输出**：

```text
NAME     STATUS   ROLES                  AGE   VERSION
server   Ready    control-plane,master   1m    v1.30.2+k3s2
```

##### 步骤 4.1.5：获取 k3s Token

> 操作设备: **云服务器**。

```bash
sudo cat /var/lib/rancher/k3s/server/node-token
```

**将输出的 Token 完整复制保存**，后面 RDK 加入集群时需要。Token 格式类似：

```text
K10xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx::server:xxxxxxxxxxxxxxxx
```

##### 步骤 4.1.6：在每台 RDK 上启用 cgroup

> 操作设备: **每台 RDK（pi1, pi2, pi3）**，以下以 pi1 为例。

```bash
ssh pi@10.0.0.2
```

编辑启动文件：

```bash
sudo vim /boot/cmdline.txt
```

在文件 **已有内容的末尾**（同一行上，前面加一个空格）添加：

```text
 cgroup_memory=1 cgroup_enable=memory
```

> **重要**: cmdline.txt 整个文件的内容必须在同一行上，不要换行！

保存退出后重启 RDK：

```bash
sudo reboot
```

等待 1-2 分钟后重新 SSH 连接：

```bash
ssh pi@10.0.0.2
```

重新启动 VPN：

```bash
sudo wg-quick up wg0
```

验证 VPN 连通：

```bash
ping -c 3 10.0.0.1
```

> **以上步骤 4.1.6 需要在 pi1、pi2、pi3 每台 RDK 上都执行一遍**，每台都要 reboot 并重连。

##### 步骤 4.1.7：在每台 RDK 上安装 k3s agent

> 操作设备: **每台 RDK**。

**方式一：在线安装**

在 pi1 (10.0.0.2) 上：

```bash
curl -sfL https://rancher-mirror.oss-cn-beijing.aliyuncs.com/k3s/k3s-install.sh | \
    INSTALL_K3S_MIRROR=cn \
    K3S_URL=https://10.0.0.1:6443 \
    K3S_TOKEN=<在步骤4.1.5中获取的Token> \
    K3S_NODE_NAME=pi1 \
    sh -
```

在 pi2 (10.0.0.3) 上：

```bash
curl -sfL https://rancher-mirror.oss-cn-beijing.aliyuncs.com/k3s/k3s-install.sh | \
    INSTALL_K3S_MIRROR=cn \
    K3S_URL=https://10.0.0.1:6443 \
    K3S_TOKEN=<在步骤4.1.5中获取的Token> \
    K3S_NODE_NAME=pi2 \
    sh -
```

在 pi3 (10.0.0.4) 上：

```bash
curl -sfL https://rancher-mirror.oss-cn-beijing.aliyuncs.com/k3s/k3s-install.sh | \
    INSTALL_K3S_MIRROR=cn \
    K3S_URL=https://10.0.0.1:6443 \
    K3S_TOKEN=<在步骤4.1.5中获取的Token> \
    K3S_NODE_NAME=pi3 \
    sh -
```

> 把 `<在步骤4.1.5中获取的Token>` 替换为实际 Token（不带尖括号）。
> 每台 RDK 的 K3S_NODE_NAME 必须不同。

**方式二：离线安装（如果在线方式失败）**

在 RDK 上（或先在本地下载再 scp 上传）：

```bash
wget https://rancher-mirror.rancher.cn/k3s/k3s-install.sh
wget https://rancher-mirror.rancher.cn/k3s/v1.30.2-k3s2/k3s-armhf
```

如果 RDK 无法下载，在本地电脑下载后 scp 到 RDK：

```powershell
scp k3s-install.sh k3s-armhf pi@10.0.0.2:~/
```

然后在 RDK 上：

```bash
sudo chmod a+x ./k3s-armhf ./k3s-install.sh
sudo cp ./k3s-armhf /usr/local/bin
sudo mv /usr/local/bin/k3s-armhf /usr/local/bin/k3s
INSTALL_K3S_MIRROR=cn \
    K3S_URL=https://10.0.0.1:6443 \
    K3S_TOKEN=<Token> \
    K3S_NODE_NAME=pi1 \
    INSTALL_K3S_SKIP_DOWNLOAD=true \
    ./k3s-install.sh
```

##### 步骤 4.1.8：验证集群节点

> 操作设备: **云服务器**。

等待所有 RDK 都完成安装后：

```bash
kubectl get nodes
```

**预期输出**（全部三台 RDK 加入后）：

```text
NAME     STATUS   ROLES                  AGE   VERSION
server   Ready    control-plane,master   10m   v1.30.2+k3s2
pi1      Ready    <none>                 5m    v1.30.2+k3s2
pi2      Ready    <none>                 3m    v1.30.2+k3s2
pi3      Ready    <none>                 1m    v1.30.2+k3s2
```

> 如果某个节点显示 NotReady，等待几分钟后重试。如果持续 NotReady，在该 RDK 上检查：
> `sudo systemctl status k3s-agent`
> `ping 10.0.0.1`

---

#### 步骤四-2：同步 Docker 镜像

##### 步骤 4.2.1：在云服务器上搭建 Docker registry

> 操作设备: **云服务器**。

```bash
sudo docker run -d -p 5000:5000 --restart=always --name registry registry:2
```

验证 registry 正在运行：

```bash
docker ps | grep registry
```

应看到 registry 容器的 STATUS 为 Up。

##### 步骤 4.2.2：在每台 RDK 上允许不安全的 registry

> 操作设备: **每台 RDK（pi1, pi2, pi3）**。

编辑 Docker 配置文件：

```bash
sudo vim /etc/docker/daemon.json
```

写入以下内容（如果文件已有其他内容，在 JSON 对象中添加这一项）：

```json
{
  "insecure-registries": ["10.0.0.1:5000"]
}
```

保存退出。

创建 k3s registry 配置目录和文件：

```bash
sudo mkdir -p /etc/rancher/k3s
sudo vim /etc/rancher/k3s/registries.yaml
```

写入以下内容：

```yaml
mirrors:
  10.0.0.1:5000:
    endpoint:
      - "http://10.0.0.1:5000"
  docker.io:
    endpoint:
      - "https://registry.aliyuncs.com"
      - "https://docker.mirrors.ustc.edu.cn"
```

保存退出。重启 Docker 和 k3s-agent 服务：

```bash
sudo systemctl restart docker
sudo systemctl restart k3s-agent.service
```

> **以上步骤 4.2.2 需要在 pi1、pi2、pi3 每台 RDK 上都执行一遍。**

##### 步骤 4.2.3：在 pi1 上构建并推送镜像到 registry

> 操作设备: **pi1**。

```bash
cd ~/experiment5

# 1. 构建镜像（如果之前已构建且代码未改动，可跳过此步）
sudo docker build -t exp5:latest .

# 2. 给镜像打上 registry 地址标签
sudo docker tag exp5:latest 10.0.0.1:5000/exp5

# 3. 推送镜像到 registry
sudo docker push 10.0.0.1:5000/exp5
```

**预期输出**：推送过程显示各层的上传进度，最后显示 digest 和 size。

验证推送成功（在任意设备上执行）：

```bash
curl http://10.0.0.1:5000/v2/_catalog
```

应输出：

```json
{"repositories":["exp5"]}
```

---

#### 步骤四-3：部署应用

##### 步骤 4.3.1：设置服务器节点的 Taint

> 操作设备: **云服务器**。

```bash
kubectl taint nodes server key1=value1:NoSchedule
```

此命令确保 agent Pod 不会被调度到云服务器上（只分配到 RDK 节点上）。

##### 步骤 4.3.2：上传 K8s 部署文件到云服务器

在 **本地电脑（Windows PowerShell）** 上：

```powershell
scp "C:\Users\12447\Desktop\交叉\hajicar\experiment\experiment5\exp5.yaml" root@<云服务器公网IP>:~/
```

或者在云服务器上用 vim 创建 exp5.yaml，粘贴 exp5.yaml 文件的完整内容。

##### 步骤 4.3.3：部署打地鼠应用

> 操作设备: **云服务器**。

```bash
kubectl apply -f ~/exp5.yaml
```

**预期输出**：

```text
deployment.apps/exp5 created
```

##### 步骤 4.3.4：等待 Pod 就绪

> 操作设备: **云服务器**。

```bash
kubectl get pods -o wide
```

等待 STATUS 全部变为 Running（可能需要 1-3 分钟，因为 RDK 需要从 registry 拉取镜像）：

```text
NAME                    READY   STATUS    RESTARTS   AGE   IP           NODE
exp5-xxxxxxxxxx-aaaaa   1/1     Running   0          60s   10.42.1.3    pi1
exp5-xxxxxxxxxx-bbbbb   1/1     Running   0          60s   10.42.2.3    pi2
exp5-xxxxxxxxxx-ccccc   1/1     Running   0          60s   10.42.3.3    pi3
```

如果 STATUS 显示 ContainerCreating，继续等待。
如果显示 ErrImagePull 或 ImagePullBackOff，排查：
- registry 是否运行：在云服务器上 `docker ps | grep registry`
- RDK 上 registries.yaml 配置是否正确
- VPN 是否连通：在 RDK 上 `ping 10.0.0.1`

##### 步骤 4.3.5：触发游戏开始

> 操作设备: **云服务器**。

先安装 paho-mqtt（如果未安装）：

```bash
pip3 install paho-mqtt
```

将 trigger 相关文件上传到云服务器：

```powershell
# 在本地电脑上执行
scp "C:\Users\12447\Desktop\交叉\hajicar\experiment\experiment5\src\qmole_trigger.py" root@<云服务器公网IP>:~/
scp "C:\Users\12447\Desktop\交叉\hajicar\experiment\experiment5\src\qmole_common.py" root@<云服务器公网IP>:~/
```

在云服务器上运行 trigger：

```bash
python3 ~/qmole_trigger.py --broker 10.0.0.1 --target 1
```

**预期输出**：

```text
Sent activate to agent 1: {"score": 0, "mole_type": 1}
```

##### 步骤 4.3.6：观察游戏运行

> 操作设备: **云服务器**（看日志）+ **肉眼观察三台 RDK 的 LED 灯**。

查看 Pod 日志：

```bash
kubectl logs -l app=exp5 --all-containers --prefix -f
```

**预期输出**（来自不同 Pod 的日志会交替出现）：

```text
[pod/exp5-xxx-aaa/exp5] [K8s Env] MY_NODE_NAME=pi1, ...
[pod/exp5-xxx-aaa/exp5] [Auto-ID] Resolved agent_id=1 from MY_NODE_NAME='pi1'
[pod/exp5-xxx-aaa/exp5] === Agent 1 started (transport=mqtt, broker=10.0.0.1) ===
[pod/exp5-xxx-aaa/exp5] [1] 真地鼠出现！
[pod/exp5-xxx-aaa/exp5] [1] 命中真地鼠 +1，总分 1
[pod/exp5-xxx-bbb/exp5] [2] 假地鼠出现！
[pod/exp5-xxx-bbb/exp5] [2] 成功躲开假地鼠，总分 1
[pod/exp5-xxx-ccc/exp5] [3] 真地鼠出现！
...
```

同时观察三台 RDK，LED 灯带应该轮流亮起。

按 Ctrl+C 退出日志跟踪。

##### 步骤 4.3.7：更新代码后重新部署

如果需要修改代码：

在 pi1 上：

```bash
# 编辑代码...
cd ~/experiment5
sudo docker build -t exp5:latest .
sudo docker tag exp5:latest 10.0.0.1:5000/exp5
sudo docker push 10.0.0.1:5000/exp5
```

在云服务器上：

```bash
kubectl delete -f ~/exp5.yaml
kubectl apply -f ~/exp5.yaml
```

---

## 三、验收要求的执行步骤

### 验收 1：通过 docker run 运行单机简化打地鼠程序

> 操作设备: **pi1**（或任意一台已构建镜像的 RDK）

**前置条件**: 已完成任务一（Docker 已安装）+ 任务二（镜像已构建）+ 云服务器 broker 在运行 + VPN 连通。

**执行命令**:

```bash
sudo docker run --rm --privileged \
    --device /dev/i2c-1:/dev/i2c-1 \
    -e BROKER_IP=10.0.0.1 \
    --name exp5-test \
    exp5:latest bash entrypoint_single.sh
```

**验收标准**:
- 终端看到 "单机打地鼠 Docker 测试" 字样
- 看到 "真地鼠出现" / "假地鼠出现" 等游戏日志
- LED 灯带正常亮灭
- 传感器响应正常（手靠近时触发命中）
- 10 轮后程序自动退出并显示最终得分

---

### 验收 2：搭建 k3s 集群，kubectl get pods 查看状态

> 操作设备: **云服务器**

**前置条件**: 已完成任务四步骤一（k3s 集群搭建）+ 步骤二（镜像推送到 registry）+ 步骤三（kubectl apply）。

**执行命令**:

```bash
kubectl get nodes
```

**预期输出**: server, pi1, pi2, pi3 全部 Ready。

```bash
kubectl get pods -o wide
```

**预期输出**: 3 个 Pod 全部 Running，分别在 pi1, pi2, pi3 节点上。

---

### 验收 3：在 k3s 集群中运行打地鼠游戏

> 操作设备: **云服务器**（发 trigger + 看日志）+ **肉眼观察三台 RDK 的 LED**

**步骤 1**: 确认 Pod 运行中

```bash
kubectl get pods -o wide
```

**步骤 2**: 发送 trigger 触发游戏

```bash
python3 ~/qmole_trigger.py --broker 10.0.0.1 --target 1
```

**步骤 3**: 观察日志

```bash
kubectl logs -l app=exp5 --all-containers --prefix -f
```

**验收标准**:
- 三台 RDK 的 LED 灯带轮流亮起
- 日志显示打地鼠在三个节点之间轮转
- 传感器触发正常

---

### 验收 4：Docker 内存占用对比

> 操作设备: **pi1**（需要开两个 SSH 窗口）

#### 步骤 A：测量 Docker 内的内存占用

**SSH 窗口 1** — 启动 Docker 容器（注意不加 --rm，让容器在后台保持运行）：

```bash
sudo docker run -d --privileged \
    --device /dev/i2c-1:/dev/i2c-1 \
    -e BROKER_IP=10.0.0.1 \
    --name exp5-mem \
    exp5:latest bash entrypoint_single.sh
```

> 这里用了 `-d` 让容器在后台运行。

**SSH 窗口 2** — 查看内存占用：

```bash
docker stats --no-stream --format "{{.Container}}: {{.MemUsage}}"
```

**预期输出**（示例）：

```text
exp5-mem: 45.2MiB / 3.7GiB
```

**记录** Docker 内存占用数值（例如 45.2 MiB）。

查看完后停止并删除容器：

```bash
sudo docker stop exp5-mem
sudo docker rm exp5-mem
```

#### 步骤 B：测量直接运行的内存占用

**SSH 窗口 1** — 直接运行 Python 程序：

```bash
cd ~/experiment5/src
pip3 install -r requirements.txt   # 如果之前没装过
python3 qmole_single.py --broker 10.0.0.1 --rounds 0
```

> --rounds 0 表示无限运行，方便在另一个窗口测量。

**SSH 窗口 2** — 用 htop 查看内存：

```bash
htop
```

在 htop 中按 F4（Filter），输入 python3，找到 qmole_single.py 进程，查看 RES（Resident Memory）列的数值。

**记录** 直接运行的内存占用数值（例如 25.3 MiB）。

在 SSH 窗口 1 按 Ctrl+C 退出程序。

#### 步骤 C：回答问题

**问题**：使用 Docker 运行程序造成的额外内存开销有多大？

**回答模板**（根据你的实际测量数据填写）：

```text
Docker 运行时内存占用约 XX MiB（docker stats 测量），
直接运行时内存占用约 YY MiB（htop RES 列测量）。
Docker 造成的额外内存开销约为 XX - YY = ZZ MiB。

这部分额外开销主要来自:
1. Docker 容器运行时（containerd shim）的基础资源消耗
2. 容器网络栈（veth pair、bridge）的内存占用
3. 容器内基础镜像中运行的系统服务

Docker 容器共享宿主机内核（不运行独立 OS），因此额外开销相对较小，
一般在 10-30 MiB 范围内，远小于虚拟机的开销。
```

---

### 选做 1：分数收集程序，封装为镜像，Pod 在云服务器运行

#### 步骤 S1.1：在 pi1 上构建分数收集器镜像

> 操作设备: **pi1**

```bash
cd ~/experiment5

# 构建镜像（注意 -f 指定使用 Dockerfile.collector）
sudo docker build -t exp5-collector:latest -f Dockerfile.collector .

# 给镜像打 registry 标签
sudo docker tag exp5-collector:latest 10.0.0.1:5000/exp5-collector

# 推送到 registry
sudo docker push 10.0.0.1:5000/exp5-collector
```

验证推送成功：

```bash
curl http://10.0.0.1:5000/v2/_catalog
```

应输出：

```json
{"repositories":["exp5","exp5-collector"]}
```

#### 步骤 S1.2：上传部署文件到云服务器

在 **本地电脑（Windows PowerShell）** 上：

```powershell
scp "C:\Users\12447\Desktop\交叉\hajicar\experiment\experiment5\exp5-collector.yaml" root@<云服务器公网IP>:~/
```

#### 步骤 S1.3：部署分数收集器

> 操作设备: **云服务器**

```bash
kubectl apply -f ~/exp5-collector.yaml
```

**预期输出**：

```text
deployment.apps/exp5-collector created
service/exp5-collector-svc created
```

#### 步骤 S1.4：验证部署

> 操作设备: **云服务器**

```bash
kubectl get pods -o wide
```

应看到 4 个 Pod — 3 个 agent Pod 在 pi1/pi2/pi3 上，1 个 collector Pod 在 server 上：

```text
NAME                              READY   STATUS    NODE
exp5-xxxxxxxxxx-aaaaa             1/1     Running   pi1
exp5-xxxxxxxxxx-bbbbb             1/1     Running   pi2
exp5-xxxxxxxxxx-ccccc             1/1     Running   pi3
exp5-collector-yyyyyy-zzzzz       1/1     Running   server
```

查看 collector Pod 日志：

```bash
kubectl logs $(kubectl get pods -l app=exp5-collector -o name)
```

应看到：

```text
[Collector] Subscribing to broker 10.0.0.1:1883
[Collector] Connected to broker (rc=0)
[Collector] Web server listening on http://0.0.0.0:8080
```

---

### 选做 2：Kubernetes Service 公网访问 Web 页面

#### 步骤 S2.1：查看 Service 状态

> 操作设备: **云服务器**

```bash
kubectl get svc
```

应看到：

```text
NAME                 TYPE        CLUSTER-IP     EXTERNAL-IP   PORT(S)          AGE
kubernetes           ClusterIP   10.43.0.1      <none>        443/TCP          30m
exp5-collector-svc   NodePort    10.43.x.x      <none>        8080:30080/TCP   2m
```

#### 步骤 S2.2：确保防火墙开放 30080 端口

> 操作设备: **云服务器**

如果使用阿里云/腾讯云，在云控制台的安全组中添加入站规则：

| 协议 | 端口范围 | 授权对象 |
|------|---------|---------|
| TCP  | 30080   | 0.0.0.0/0 |

如果使用 iptables：

```bash
sudo iptables -A INPUT -p tcp --dport 30080 -j ACCEPT
```

如果使用 ufw：

```bash
sudo ufw allow 30080/tcp
```

#### 步骤 S2.3：访问 Web 页面

在浏览器中打开：

```text
http://<云服务器公网IP>:30080
```

**预期看到的页面内容**：

标题：🎮 打地鼠游戏实时状态

统计信息：
- ⏱ 运行时间: 00:05:32
- 🔄 总回合数: 47
- 📡 在线节点: 3 / 3

节点状态表格：

| Agent ID | 节点名称 | 当前分数 | 最近事件 | 状态 | 最后活跃 |
|----------|---------|---------|---------|------|---------|
| 1 | pi1 | 12 | 地鼠类型=真, 分数=12 | 🟢 在线 | 2秒前 |
| 2 | pi2 | 8 | 地鼠类型=假, 分数=8 | 🟢 在线 | 5秒前 |
| 3 | pi3 | 10 | 地鼠类型=真, 分数=10 | 🟢 在线 | 1秒前 |

页面每 3 秒自动刷新。

也可以访问 JSON API 获取原始数据：

```text
http://<云服务器公网IP>:30080/api/state
```

#### 步骤 S2.4：查看 Collector 日志

```bash
kubectl logs -f $(kubectl get pods -l app=exp5-collector -o name)
```

---

## 四、常用命令速查

### Docker 命令

| 命令 | 说明 |
|------|------|
| `docker ps` | 列出运行中的容器 |
| `docker ps -a` | 列出所有容器（包括已停止的） |
| `docker images` | 列出本地所有镜像 |
| `docker build -t 名称:标签 .` | 从当前目录的 Dockerfile 构建镜像 |
| `docker run --rm 镜像名` | 运行容器（退出后自动删除） |
| `docker run -d 镜像名` | 后台运行容器 |
| `docker stop 容器名` | 停止容器 |
| `docker rm 容器名` | 删除容器 |
| `docker rmi 镜像名` | 删除镜像 |
| `docker exec -it 容器名 bash` | 进入正在运行的容器 shell |
| `docker logs 容器名` | 查看容器日志 |
| `docker stats --no-stream` | 查看容器资源占用（一次性快照） |
| `docker tag 源镜像 目标镜像` | 给镜像打标签 |
| `docker push 镜像名` | 推送镜像到 registry |

### Kubernetes 命令

| 命令 | 说明 |
|------|------|
| `kubectl get nodes` | 列出所有节点 |
| `kubectl get pods` | 列出所有 Pod |
| `kubectl get pods -o wide` | 列出所有 Pod（含节点、IP 等详情） |
| `kubectl get svc` | 列出所有 Service |
| `kubectl describe pod <Pod名>` | 查看 Pod 详细信息（排错必备） |
| `kubectl logs <Pod名>` | 查看 Pod 日志 |
| `kubectl logs -f <Pod名>` | 实时跟踪 Pod 日志 |
| `kubectl logs -l app=exp5 --all-containers --prefix` | 查看所有匹配标签的 Pod 日志 |
| `kubectl exec -it <Pod名> -- /bin/bash` | 进入 Pod 的 shell |
| `kubectl apply -f <文件.yaml>` | 创建或更新部署 |
| `kubectl delete -f <文件.yaml>` | 删除部署 |
| `kubectl taint nodes <节点名> <键>=<值>:<效果>` | 给节点设置 Taint |

### 完整操作流程快速参考

```text
=== 一次性设置 ===
每台RDK:   安装Docker → 解决时间同步 → 非root用户配置
云服务器:  安装k3s server → 设置VPN IP → 搭建Docker registry
每台RDK:   启用cgroup → reboot → 安装k3s agent → 配置insecure-registry

=== 首次部署 ===
pi1:       上传代码 → docker build → docker tag → docker push
云服务器:  kubectl taint → kubectl apply -f exp5.yaml
云服务器:  python3 qmole_trigger.py --broker 10.0.0.1 --target 1

=== 更新部署 ===
pi1:       修改代码 → docker build → docker tag → docker push
云服务器:  kubectl delete -f exp5.yaml → kubectl apply -f exp5.yaml

=== 查看状态 ===
云服务器:  kubectl get nodes
云服务器:  kubectl get pods -o wide
云服务器:  kubectl logs -l app=exp5 --all-containers --prefix -f

=== 选做部署 ===
pi1:       docker build -f Dockerfile.collector → docker tag → docker push
云服务器:  kubectl apply -f exp5-collector.yaml
浏览器:   http://<公网IP>:30080
```
