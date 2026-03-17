这份 README 旨在帮助你（或者未来的 AI 开发者）快速部署并运行基于 **RDK X5** 的分布式“打地鼠”趣味实验。该系统利用 **ZeroMQ (ZMQ)** 实现多设备间的异步通信，并将硬件传感器（APDS9960）与 LED 灯带结合，打造一个交互式游戏。

---

## 🎮 项目概述：分布式打地鼠 (Whack-a-Mole)

这是一个基于“接力”机制的游戏。游戏在多台 RDK X5 设备间进行，每一时刻只有一台设备的“地鼠”处于活跃状态。玩家需要通过手势感应“打击”地鼠，随后地鼠会随机“逃窜”到网络中的另一台设备上。

---

## 🛠 环境配置

在开始实验前，请确保所有 RDK X5 设备均已完成以下准备：

### 1. 硬件连接
* **传感器**：APDS9960 接近/手势传感器，连接至 RDK X5 的 **I2C 端口 5**。
* **灯光**：WS2812 LED 灯带（或板载 LED 阵列），通过 **SPI 总线 1** 控制。

### 2. 软件依赖
需要安装 Python 3 及其相关库：
```bash
sudo pip3 install pyzmq spidev smbus2 apds9960
```
*注：由于涉及 SPI 和 I2C 底层硬件访问，运行程序时通常需要 `sudo` 权限。*

### 3. 网络拓扑
* **Broker (代理)**：选择一台设备（可以是 PC 或其中一台 RDK X5）运行 `broker.py`，充当消息中转站。
* **Agents (节点)**：多台 RDK X5 运行 `agent.py`，作为游戏终端。
* **Trigger (触发器)**：运行一次 `trigger.py` 来启动游戏首个回合。

---

## 📁 版本一：基础版 (Basic Edition)
**文件：** `agent_basic.py`, `trigger_basic.py`

### 💡 核心逻辑
* **启动**：Agent 处于静默状态，直到收到 `activate` 消息。
* **交互**：地鼠出现（绿灯亮起），Agent 开始高频轮询 APDS9960 的接近感应值（Proximity）。
* **计分**：检测到数值超过 `THRESHOLD`（手靠近）后，熄灯，本地得分 +1。
* **接力**：Agent 随机选择一个非自身的 `agent_id`，将**更新后的总分**发送出去。

### 📨 消息格式
`"<target_id>: activate <current_total_score>"`
> 例如：`"2: activate 5"` 表示激活 2 号机，当前全场总分为 5。

---

## 🚀 版本二：进阶版 (Advanced Edition)
**文件：** `agent_adv.py`, `trigger_adv.py`

在基础版之上，增加了游戏性惩罚机制和自动调度。

### 🌟 新增功能
1.  **假地鼠机制 (Fake Moles)**：
    * **真地鼠**：亮**绿灯**。打中 +1 分。
    * **假地鼠**：亮**红灯**。打中 **-1 分**。
2.  **超时机制 (Timeout)**：
    * 若地鼠出现 `TIMEOUT_SECONDS`（默认 3 秒）后玩家未作反应，地鼠自动消失并跳转到下一台设备，分数不变。
3.  **状态机优化**：
    * 使用非阻塞的 `zmq.Poller`，确保在等待消息的同时，传感器检测和超时计时器能正常工作。

### 📨 消息格式
`"<target_id>: activate <current_total_score> <mole_type>"`
* `mole_type`: `1` 为真地鼠，`0` 为假地鼠。

---

## 📖 使用指南

### 第一步：启动 Broker (中心节点)
在作为服务器的机器上运行：
```bash
python3 broker.py
```

### 第二步：启动 Agents (游戏终端)
在每台 RDK X5 上运行（假设 Broker IP 为 `192.168.1.100`，当前设备编号为 `1`）：
```bash
# 基础版
sudo python3 agent_basic.py 192.168.1.100 1
# 或 进阶版
sudo python3 agent_adv.py 192.168.1.100 1
```

### 第三步：启动游戏 (触发器)
在任意联网终端运行一次，激活 1 号机：
```bash
python3 trigger_basic.py 192.168.1.100
# 或
python3 trigger_adv.py 192.168.1.100
```

---

## ⚠️ 注意事项

1.  **ID 分配**：请确保每台 Agent 启动时的 `agent_id` 是唯一的，且在代码顶部的 `num_agents` 范围内。
2.  **网络延迟**：ZMQ 的连接需要时间握手。`trigger.py` 中设置了 `time.sleep(1.0)` 以确保连接稳定后再发送首条消息。如果游戏未启动，请尝试再次运行 trigger。
3.  **传感器阈值**：`THRESHOLD = 100` 是一个参考值。如果环境光较强或安装位置不同，请根据实验现象自行调整该值（范围 0-255）。
4.  **连击防护**：为了防止一次挥手动作连续触发多个回合，Agent 在发送消息后会有短暂的 `sleep` 缓冲。

---
