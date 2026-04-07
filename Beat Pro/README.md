# Beat Pro —— 多人联机打地鼠进阶版

## 项目概述

基于课程实验 2–5 的打地鼠游戏进行大幅升级，打造一个支持多人对战、多游戏模式、Web 实时观战的完整联机游戏系统。保留 3 台 RDK X5 + WS2812 LED + APDS9960 手势传感器的核心硬件，在软件层面全面增强。

---

## 升级要点

### 🎮 游戏模式扩展

| 模式 | 说明 |
| ---- | ---- |
| **经典单人** | 与实验原版一致，地鼠在 3 台 RDK 间随机出现 |
| **竞速对抗** | 3 名玩家各守一台 RDK，地鼠随机出现在任意设备，谁先拍到得分 |
| **合作生存** | 地鼠出现频率递增，任意一只逃脱则全队扣血，坚持越久分越高 |
| **节奏模式** | 地鼠按预设节奏序列出现（类音游），精准度越高分数越高 |

### 🌈 LED 效果升级

- 从 32 颗单色扩展为 **多区域独立控制**，支持渐变、呼吸灯、彩虹流水效果
- 击中反馈动画：绿色爆裂扩散（真鼹鼠） / 红色闪烁警告（假鼹鼠）
- 连击（combo）时 LED 颜色随连击数升级：绿 → 蓝 → 紫 → 金

### 📡 通讯与部署

- **MQTT over TCP**（NanoMQ Broker），复用实验 4/5 成熟方案
- 可选 **MQTT over QUIC** 对比延迟对游戏体验的影响
- Docker 容器化部署，一键启动三节点 + Web 观战服务

### 🖥️ Web 实时观战

- 基于实验 5 的 `score_collector.py` 扩展
- 实时显示：各玩家得分、连击数、在线状态
- 游戏回放：记录每次击打事件的时间戳与结果

### 📊 网络公平性补偿

- 利用实验 4 的延迟测量框架，实时监测各节点到 Broker 的 RTT
- 动态调整地鼠激活延迟，补偿网络不对称性

---

## 预设文件结构

```
Beat Pro/
├── README.md
├── src/
│   ├── game_agent.py         # 游戏终端主逻辑
│   ├── led_effects.py        # LED 特效引擎
│   ├── game_modes.py         # 游戏模式管理
│   ├── mqtt_comm.py          # MQTT 通讯封装
│   ├── web_dashboard.py      # Web 观战服务
│   └── latency_compensator.py # RTT 补偿模块
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
└── assets/
    └── rhythm_patterns/      # 节奏模式谱面
```

---

## 技术栈

| 层级 | 技术 |
| ---- | ---- |
| 硬件 | RDK X5 × 3 + WS2812 LED (SPI) + APDS9960 (I2C) |
| 通讯 | MQTT-TCP / MQTT-QUIC（NanoMQ） |
| 后端 | Python 3.10 + paho-mqtt |
| 前端 | Python http.server（轻量 Web UI） |
| 部署 | Docker 容器化 |

> 本项目为课下个人兴趣开发，在实验打地鼠基础上自由发挥。
