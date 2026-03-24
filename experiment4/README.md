# 实验四：MQTT/QUIC 打地鼠与云端-RDK 延迟测试

本目录包含两部分：

1. **基于 NanoMQ（MQTT over QUIC）的打地鼠程序**：参考 experiment2 的 ZMQ 版本，改为 MQTT 主题模型，并支持 QUIC（通过 `nanomq_cli`）与 TCP（通过 `paho-mqtt`）。
2. **云服务器 ↔ RDK 端到端延迟测试框架**：覆盖 TCP vs QUIC、VPN vs 直连、有线 vs 无线、Payload 大小、QoS 等维度；一端 1~2 个脚本即可跑全组合，产出 CSV 与曲线。

> 备注：当前仓库中的 `nanomq_cli` 与 `libmsquic.so.2` 适用于类 Linux/RDK 环境，Windows 下无法直接执行。请在 RDK 或服务器上运行。

---
## 目录
- `qmole_agent.py`：Agent 端（RDK）逻辑，支持 MQTT-TCP 与 QUIC（经 `nanomq_cli`）。
- `qmole_trigger.py`：启动首轮地鼠。
- `qmole_common.py`：共用的配置、传输抽象（MQTT-TCP / NanoMQ-QUIC），LED/传感器桩。
- `nanomq_quic_sample.conf`：NanoMQ 开启 QUIC 的示例配置片段。
- `latency_probe.py`：单次/单维度延迟测试（本端既发又收），记录统计到 CSV。
- `latency_runner.py`：批量组合跑表；一端脚本自动遍历组合，另一端只需运行同一脚本或镜像方式。
- `plot_latency.py`：读取 CSV，输出汇总表和曲线（PNG）。
- `requirements.txt`：Python 依赖（仅用于 TCP/绘图；QUIC 依赖 `nanomq_cli`）。
- `test_timing.py`：原始参考代码，保留。

---
## 1. 环境准备
- **硬件**：RDK X5，APDS9960 传感器 + WS2812 LED 条（与 experiment2 相同接线）。
- **Broker**：NanoMQ 开启 MQTT over QUIC（参考 `nanomq_quic_sample.conf`），同时保留 TCP 端口以便对照。
- **Python 依赖（TCP/绘图部分）**：

```bash
pip install -r requirements.txt
```

- **NanoMQ CLI (QUIC 客户端)**：使用本目录 `nanomq_cli`（Linux 可执行），必要时 `chmod +x nanomq_cli`。

---
## 2. NanoMQ（MQTT over QUIC）示例配置
见 `nanomq_quic_sample.conf`。要点：
- 开启 QUIC 监听，如 `quic_listen = "quic://0.0.0.0:14567"`。
- 为 QUIC 配置证书/密钥，或使用 `verify_peer false` 仅供内网实验。
- TCP 监听保留，例如 `mqtt.tcp_listen = "0.0.0.0:1883"` 便于对照测试。

启动示例（在 NanoMQ 安装目录）：
```bash
./nanomq start -c /path/to/nanomq_quic_sample.conf
```

---
## 3. 打地鼠（MQTT/QUIC 版）
### 3.1 主题与消息格式
- 激活消息主题：`mole/activate/<agent_id>`，Payload JSON：`{"score": int, "mole_type": 0|1}`。
- 心跳主题：`mole/heartbeat/<agent_id>`，Payload `"alive"`。
- 在线列表广播（可选）：`mole/online`，Payload JSON：`{"online": [ids...]}`（由任意 Agent 或外部小脚本发布）。

### 3.2 运行
假设 Broker IP 为 `192.168.1.100`，QUIC 端口 14567，TCP 端口 1883。

#### QUIC 模式（需 `nanomq_cli` 可执行，默认路径 `./nanomq_cli`）
```bash
# Agent 1（RDK）
python3 qmole_agent.py --transport quic --broker 192.168.1.100 --quic-port 14567 --id 1
# Agent 2（RDK）
python3 qmole_agent.py --transport quic --broker 192.168.1.100 --quic-port 14567 --id 2
# 触发首轮
auth_env="NANOMQ_CLI=./nanomq_cli"  # 如需自定义 CLI 路径
python3 qmole_trigger.py --transport quic --broker 192.168.1.100 --quic-port 14567 --target 1
```

#### TCP 模式（便于在 PC 上仿真，无需硬件）
```bash
python3 qmole_agent.py --transport mqtt --broker 192.168.1.100 --tcp-port 1883 --id 1 --mock
python3 qmole_agent.py --transport mqtt --broker 192.168.1.100 --tcp-port 1883 --id 2 --mock
python3 qmole_trigger.py --transport mqtt --broker 192.168.1.100 --tcp-port 1883 --target 1
```
- `--mock` 会使用虚拟 LED/传感器，便于无硬件调试。
- QUIC 模式下消息收发通过外部进程 `nanomq_cli sub/pub`，请确保其支持 `--quic`（部分版本使用 `--transport quic`，可在 README 顶部调整命令模板）。

---
## 4. 云↔RDK 延迟测试
脚本支持：协议（ZMQ-TCP / MQTT-TCP / MQTT-QUIC）、QoS、payload，标签记录 VPN / 有线 / 无线（需手动切换网络，脚本记录标签）。

### 4.1 单次探测
在双方各运行一次同参脚本（或一端运行，另一端同样运行；双方互发互收）：
```bash
# 例：MQTT-QUIC，payload 512B，QoS 1，标签 vpn_wireless
python3 latency_probe.py --protocol mqtt-quic --broker 192.168.1.100 --quic-port 14567 \
  --payload 512 --qos 1 --tag vpn_wireless --out results_quic.csv
```
- 运行时每端都会发送带时间戳的消息并接收对端消息，计算单向延迟（本地接收时刻减去对端发送时刻）。
- CSV 追加写入，字段包括时间、协议、qos、payload、tag、mean/median/std/样本数。

### 4.2 批量跑全组合
在“主动端”运行（另一端也需同时运行 `latency_probe.py` 或同一 runner，以便互发互收）：
```bash
python3 latency_runner.py \
  --protocols mqtt-tcp,mqtt-quic,zmq-tcp \
  --payloads 64,512,1024 \
  --qos-levels 0,1,2 \
  --tag wired_vpn \
  --broker 192.168.1.100 --tcp-port 1883 --quic-port 14567 \
  --per-test-seconds 8 \
  --out results_matrix.csv
```
- `latency_runner.py` 会顺序调用 `latency_probe.py` 执行每组参数，自动汇总到同一 CSV。
- 切换“有线/无线、VPN/直连”需人工切换网络后重新运行并用不同 `--tag` 标记。

### 4.3 绘图与表格
```bash
python3 plot_latency.py --csv results_matrix.csv --out-dir charts
```
生成：
- 各协议/参数的箱线图、折线图（按 payload、QoS 分组）。
- 同步输出聚合表（均值/中位/标准差）为 `charts/summary.csv`。

---
## 5. 注意事项
- QUIC 客户端依赖 `nanomq_cli`；如命令行选项与此处示例不同，请在 `qmole_common.py` 顶部的 CLI 模板处调整。
- RDK 硬件访问需 `sudo`（I2C/SPI）。若仅仿真，请加 `--mock`。
- CSV/图表可直接用于报告，标签字段用来标记“有线/无线、VPN/直连”等环境。

祝实验顺利！
