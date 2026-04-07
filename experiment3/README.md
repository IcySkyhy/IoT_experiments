# 实验三：基于 batman-adv 无线自组网的打地鼠游戏

## 实验概述

本实验将实验二的有线 ZeroMQ 打地鼠程序迁移到基于 **batman-adv** 的无线自组网（Mesh Network）上。断开有线连接后，多节点之间通过 WiFi Ad-Hoc 模式自动组网并维持通信。

### 任务说明

| 类型 | 描述 |
|------|------|
| 必做 | 将实验二移植到 bat0 无线自组网上运行 |
| 选做 DLC1 | 心跳检测：Broker 追踪节点在线状态 |
| 选做 DLC2 | 去中心化：Broker 广播在线列表，Agent 动态选择目标 |
| 可视化 | 用 batadv-vis + graphviz 展示网络拓扑 |

### 文件说明

```
experiment3/
├── broker.py          # 必做：基础消息代理（XPUB/XSUB 透明代理）
├── agent.py           # 必做：基础 Agent（LED + APDS9960）
├── trigger.py         # 必做：游戏启动触发器
├── broker_dlc1.py     # DLC1：带心跳追踪的 Broker
├── agent_dlc1.py      # DLC1：发送心跳的 Agent
├── trigger_dlc1.py    # DLC1：启动触发器
├── broker_dlc2.py     # DLC2：广播在线列表的 Broker
├── agent_dlc2.py      # DLC2：订阅在线列表的 Agent
├── trigger_dlc2.py    # DLC2：启动触发器
└── visualize.ipynb    # 网络拓扑可视化（graphviz）
```

---

## 环境准备

### 1. 安装依赖软件包

在每台节点上执行：

```bash
sudo apt update
sudo apt install -y alfred batctl python3-pip

# 如果 apt 中的 batctl 版本过旧，手动编译 batctl 2021.0：
wget https://downloads.open-mesh.org/batman/releases/batman-adv-2021.0/batctl-2021.0.tar.gz
tar xf batctl-2021.0.tar.gz
cd batctl-2021.0
make
sudo make install
cd ..
```

安装 Python 依赖：

```bash
pip3 install pyzmq smbus2 spidev apds9960
```

### 2. 设置 WiFi 国家代码

```bash
sudo iw reg set CN
```

> **注意**：此设置重启后会失效，每次开机需重新执行，或写入开机脚本。

---

## 配置 batman-adv 无线自组网

> **重要提示**：部分 WiFi 网卡芯片（如 rtl8188 等）**不支持 IBSS/Ad-Hoc 模式**，会显示 `Operation not supported`。
> 遇到此错误说明硬件不支持，可以先用现有有线 IP（如 `10.42.0.x`）验证程序逻辑，无需 batman-adv 也能完成实验。

### 逐步配置脚本

在每台节点上执行以下命令（以 **pi1** 为例，IP 设为 `172.27.0.1`）：

```bash
# 步骤 1：加载 batman-adv 内核模块
sudo modprobe batman-adv

# 步骤 2：将 wlan0 切换到 Ad-Hoc 模式
sudo ip link set wlan0 down
sudo iw dev wlan0 set type ibss
sudo ip link set wlan0 up

# 步骤 3：加入同一个 IBSS 网络（所有节点使用相同的 ssid 和频道）
sudo iw dev wlan0 ibss join mesh 2437   # 2437 MHz = 信道 6

# 步骤 4：将 wlan0 加入 batman-adv
sudo batctl if add wlan0

# 步骤 5：启动 bat0 虚拟接口
sudo ip link set bat0 up

# 步骤 6：分配 IP（每台节点使用不同的 x）
# pi1: 172.27.0.1，pi2: 172.27.0.2，pi3: 172.27.0.3
sudo ip addr add 172.27.0.1/16 dev bat0
```

### 验证组网成功

```bash
# 查看直接邻居节点
sudo batctl n

# 查看全网路由表
sudo batctl o

# 测试连通性（从 pi1 ping pi2）
ping 172.27.0.2
```

### 封装为一键脚本（推荐）

将以下内容保存为 `setup_mesh.sh`，修改最后一行的 IP 地址后执行：

```bash
#!/bin/bash
AGENT_IP="172.27.0.1"   # <<< 修改为本节点 IP

sudo modprobe batman-adv
sudo ip link set wlan0 down
sudo iw dev wlan0 set type ibss
sudo ip link set wlan0 up
sudo iw dev wlan0 ibss join mesh 2437
sudo batctl if add wlan0
sudo ip link set bat0 up
sudo ip addr add ${AGENT_IP}/16 dev bat0

echo "bat0 配置完成，本机 IP: ${AGENT_IP}"
sudo batctl n
```

```bash
chmod +x setup_mesh.sh
sudo ./setup_mesh.sh
```

---

## 使用 tmux 保持 SSH 会话

> **关键**：断开有线连接后 SSH 会断开，需用 **tmux** 提前将程序放入后台会话，程序才能继续运行。

```bash
# 创建新的 tmux 会话
tmux new -s broker

# 在 tmux 内运行程序后，按 Ctrl+B 再按 D 分离会话（程序继续后台运行）

# 重新连接到已有会话
tmux attach -t broker

# 查看所有会话
tmux ls

# 关闭会话（在 tmux 内执行）
exit
```

---

## 必做任务：基础无线打地鼠

按照以下顺序启动各组件：**Broker → Agent → Trigger**

### 步骤 1：在某台节点（如 pi1）启动 Broker

```bash
# 假设 pi1 的 bat0 IP 为 172.27.0.1
tmux new -s broker
sudo python3 broker.py
# 按 Ctrl+B，再按 D 分离会话
```

输出示例：
```
Broker 启动，监听 5555/5556 ...
```

### 步骤 2：在每台节点启动 Agent

```bash
# pi1（172.27.0.1）：
tmux new -s agent
sudo python3 agent.py 172.27.0.1 1
# 按 Ctrl+B, D 分离

# pi2（172.27.0.2）：
tmux new -s agent
sudo python3 agent.py 172.27.0.1 2
# 按 Ctrl+B, D 分离

# pi3（172.27.0.3）：
tmux new -s agent
sudo python3 agent.py 172.27.0.1 3
# 按 Ctrl+B, D 分离
```

### 步骤 3：从任意节点发送启动信号

```bash
python3 trigger.py 172.27.0.1
```

输出示例：
```
正在连接到 Broker 172.27.0.1:5556 ...
已向 Agent 1 发送启动信号: '1: activate 0 1'
```

### 游戏说明

- **绿灯**（真地鼠）：接近传感器打它，得 +1 分
- **红灯**（假地鼠）：不要打，打了扣 -1 分
- 地鼠 3 秒内无动作自动消失，传到下一个节点
- 打中后随机选下一个节点，70% 真地鼠 / 30% 假地鼠

---

## 选做 DLC1：心跳检测动态节点

**功能**：每个 Agent 每 2 秒向 Broker 发送心跳包，Broker 追踪并打印在线节点列表。

```
消息流: Agent --heartbeat--> Broker（记录上线时间）
        Broker 每隔 2 秒打印: "Current Online Agents: ['1', '2', '3']"
        超时 5 秒未收到心跳 → 判定该节点离线
```

### 启动顺序

```bash
# 步骤 1：启动 DLC1 Broker（pi1）
tmux new -s broker
sudo python3 broker_dlc1.py

# 步骤 2：在每台节点启动 DLC1 Agent（第三个参数为总节点数）
# pi1:
tmux new -s agent
sudo python3 agent_dlc1.py 172.27.0.1 1 3

# pi2:
tmux new -s agent
sudo python3 agent_dlc1.py 172.27.0.1 2 3

# pi3:
tmux new -s agent
sudo python3 agent_dlc1.py 172.27.0.1 3 3

# 步骤 3：发送启动信号
python3 trigger_dlc1.py 172.27.0.1
```

Broker 输出示例：
```
Broker (DLC1) started. Listening for heartbeats...
Current Online Agents: ['1', '2', '3']
Current Online Agents: ['1', '2', '3']
Agent 3 timed out (offline).
Current Online Agents: ['1', '2']
```

> **说明**：DLC1 中 Broker 负责追踪在线状态，Agent 使用固定节点数。DLC2 进一步让 Agent 也动态感知在线列表。

---

## 选做 DLC2：去中心化广播动态节点

**功能**：Broker 每 2 秒广播当前在线节点列表（`GLOBAL online 1,2,3`），Agent 收到后动态更新可选目标，节点加入/退出时游戏自动适应。

```
消息流: Agent --heartbeat--> Broker（更新在线表）
        Broker --"GLOBAL online 1,2"--> 所有 Agent
        Agent 从 online_agents 中随机选下一目标（排除自己）
```

### 启动顺序

```bash
# 步骤 1：启动 DLC2 Broker（pi1）
tmux new -s broker
sudo python3 broker_dlc2.py

# 步骤 2：在每台节点启动 DLC2 Agent（无需指定总节点数）
# pi1:
tmux new -s agent
sudo python3 agent_dlc2.py 172.27.0.1 1

# pi2:
tmux new -s agent
sudo python3 agent_dlc2.py 172.27.0.1 2

# pi3:
tmux new -s agent
sudo python3 agent_dlc2.py 172.27.0.1 3

# 步骤 3：发送启动信号
python3 trigger_dlc2.py 172.27.0.1
```

Agent 输出示例：
```
Agent 2 (DLC2 Dynamic) 启动...
[2] 真地鼠！
得分+1, 总分: 1
传球给 Agent 3
没有其他在线节点，游戏暂停。等待其他节点上线...
```

### 测试动态加入/退出

1. 先启动 pi1 和 pi2 的 Agent，发送 trigger
2. 游戏在两节点间交替
3. 在 pi3 上启动 Agent，约 2 秒后 Broker 广播更新，pi3 自动加入游戏
4. 对 pi2 执行 Ctrl+C，约 5 秒后 pi2 超时，游戏在 pi1 和 pi3 间继续

---

## 可视化：batman-adv 网络拓扑

### 安装 batadv-vis

```bash
sudo apt install batadv-vis
# 或从 BATMAN 源码安装（与 batctl 同包）
```

### 启动 alfred 守护进程和 batadv-vis

在**每台**节点上：

```bash
# 启动 alfred 守护进程（收集链路信息）
sudo alfred -i bat0 -m &
```

在**一台**节点上：

```bash
# 启动 batadv-vis（汇总并生成 DOT 格式输出）
sudo batadv-vis -i bat0 -s &

# 等待几秒收集数据，然后查看拓扑
sudo alfred -r 61 | batadv-vis
```

输出为 DOT 语言格式，形如：

```dot
digraph {
    subgraph "cluster_aa:bb:cc:dd:ee:ff" {
        "aa:bb:cc:dd:ee:ff"
    }
    "aa:bb:cc:dd:ee:ff" -> "11:22:33:44:55:66" [label="1.000"]
    ...
}
```

### 在 visualize.ipynb 中可视化

1. 将以上 DOT 输出复制到 `visualize.ipynb` 的 `graph = """..."""` 变量中
2. 运行 notebook 中的所有单元格
3. 生成并显示 `network.gv.png` 拓扑图

---

## 故障排除

### 问题 1：网卡不支持 Ad-Hoc / IBSS 模式

```
Operation not supported
```

**原因**：该网卡芯片驱动不支持 IBSS 模式（如 rtl8188cu、rtl8192cu 等）。
**解决**：
- 更换支持的网卡（推荐 Atheros 芯片：ath9k 驱动）
- 用现有有线 IP 测试游戏逻辑（见下方）

### 问题 2：先用有线 IP 验证程序逻辑

```bash
# 用有线 IP（如 10.42.0.1）代替 bat0 IP 先测试
sudo python3 broker.py                   # 在 Radxa（10.42.0.1）
sudo python3 agent.py 10.42.0.1 1        # pi1
sudo python3 agent.py 10.42.0.1 2        # pi2
sudo python3 agent.py 10.42.0.1 3        # pi3
python3 trigger.py 10.42.0.1
```

程序逻辑与是否使用 batman-adv 无关，只要 IP 可达即可运行。

### 问题 3：第一条消息丢失（游戏不启动）

**原因**：ZMQ PUB/SUB 连接建立需要时间，trigger.py 中已有 `time.sleep(1.0)` 等待。
**解决**：如仍不触发，将 trigger.py 中的等待时间改为 `time.sleep(2.0)` 后重试。

### 问题 4：LED 不亮 / I2C 错误

```bash
# 检查 SPI 是否启用
ls /dev/spidev*

# 检查 I2C 设备
ls /dev/i2c-*

# 扫描 APDS9960（I2C 地址 0x39）
sudo i2cdetect -y 5
```

如果 `/dev/spidev1.0` 或 `/dev/i2c-5` 不存在，需要在系统配置中启用对应接口后重启。

### 问题 5：bat0 配置丢失（重启后）

batman-adv 配置不会持久化，每次开机需重新执行配置脚本：

```bash
sudo ./setup_mesh.sh
```

---

## 完整实验检查清单

### 必做

- [ ] 在各节点成功设置 bat0 接口（或有线网络验证通过）
- [ ] broker.py 正常启动并在 tmux 中后台运行
- [ ] 三台节点的 agent.py 均已启动
- [ ] trigger.py 成功触发游戏
- [ ] 游戏消息在节点间正常传递，LED 正常亮灭
- [ ] 通过 tmux 验证断开 SSH 后程序继续运行

### 选做 DLC1

- [ ] broker_dlc1.py 终端显示在线节点列表
- [ ] 关闭一台 Agent 后，Broker 在 5 秒内检测到超时并打印 offline 信息

### 选做 DLC2

- [ ] 关闭一台 Agent 后，其他节点不会再将球传给它
- [ ] 重新启动该 Agent，2 秒内自动重新加入游戏并接收到地鼠

### 可视化

- [ ] `batadv-vis` 输出有效的 DOT 格式数据
- [ ] visualize.ipynb 成功渲染网络拓扑图
