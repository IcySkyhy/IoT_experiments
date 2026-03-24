# 快速起步指南（实验四：MQTT/QUIC 打地鼠 & 云-RDK 延迟测试）

面向接手代码的人类和 AI，提供从 0 开始的完整步骤：环境与硬件、Broker 部署、打地鼠运行、延迟测试、绘图。

## 目录结构

- `qmole_agent.py` / `qmole_trigger.py` / `qmole_common.py`：MQTT/QUIC 打地鼠（3 台 RDK）。
- `latency_probe.py` / `latency_runner.py` / `latency_dual_runner.py`：云-RDK 延迟测试（主动 ping，云端回显）。
- `plot_latency.py`：读取 CSV 生成图表和 summary。
- `nanomq_quic_sample.conf`：NanoMQ 配置模板（含 QUIC）。
- `requirements.txt`：Python 依赖（仅 TCP/绘图，QUIC 由外部 `nanomq_cli` 提供）。
- `nanomq_cli`：Linux/RDK 可执行的 NanoMQ CLI，用于 QUIC 客户端收发。

## 环境与硬件要求

- **云服务器**：Ubuntu 22.04（无桌面），部署 NanoMQ Broker，需放行 TCP 1883 和 QUIC 14567（默认）。
- **RDK（3 台）**：Server 版，无桌面。接有 APDS9960 + WS2812（SPI/I2C）。如无硬件，可用 `--mock` 纯软件仿真。
- **Python 依赖**（TCP/绘图）：`pip install -r requirements.txt`。
- **QUIC 客户端**：使用目录内 `nanomq_cli`（需 Linux/RDK 环境，可执行 `chmod +x nanomq_cli`）。

## 第 1 步：部署并启动 NanoMQ（云端）

1. 将 `nanomq_quic_sample.conf` 拷贝到云端，例如 `/etc/nanomq/nanomq.conf`，并按需修改端口/证书：
   - TCP：`mqtt.tcp_listen = "0.0.0.0:1883"`
   - QUIC：`quic_listen = "quic://0.0.0.0:14567"`
   - 内网实验可暂时 `verify_peer = false`；有证书时填写 `certfile/keyfile/cafile`。

2. 启动 Broker：

   ```bash
   ./nanomq start -c /etc/nanomq/nanomq.conf
   ```

3. 防火墙放行：

   ```bash
   sudo ufw allow 1883/tcp
   sudo ufw allow 14567/udp
   ```

4. 验证监听：

   ```bash
   sudo netstat -lnpt | grep nano
   ```

## 第 2 步：打地鼠（3 台 RDK）

假设云端 IP 为 `192.168.1.100`，默认端口 TCP 1883 / QUIC 14567。

RDK 1/2/3 分别运行（MQTT/QUIC）：

```bash
python3 qmole_agent.py --transport quic --broker 192.168.1.100 --quic-port 14567 --id 1 --num-agents 3
python3 qmole_agent.py --transport quic --broker 192.168.1.100 --quic-port 14567 --id 2 --num-agents 3
python3 qmole_agent.py --transport quic --broker 192.168.1.100 --quic-port 14567 --id 3 --num-agents 3
```

> 无硬件加 `--mock`；如需 TCP 对照：`--transport mqtt --tcp-port 1883`。

触发首轮（任一设备）：

```bash
python3 qmole_trigger.py --transport quic --broker 192.168.1.100 --quic-port 14567 --target 1
```

## 第 3 步：延迟测试（RDK 主动 ping，云端回显）

### 云端（echo 端）

为每个要测的协议各启动一个 echo 进程，保持运行：

```bash
# MQTT-QUIC echo
python3 latency_probe.py --role echo --protocol mqtt-quic \
  --broker 192.168.1.100 --quic-port 14567 --active-id rdk1 &

# MQTT-TCP echo
python3 latency_probe.py --role echo --protocol mqtt-tcp \
  --broker 192.168.1.100 --tcp-port 1883 --active-id rdk1 &

# ZMQ-TCP echo
python3 latency_probe.py --role echo --protocol zmq-tcp \
  --broker 192.168.1.100 &
```

> `--active-id` 与 RDK 端的 `--id` 对应（例如 `rdk1`）。只测某个协议就只开对应的进程。

### RDK（active 端，批量一键跑完）

```bash
python3 latency_runner.py \
  --broker 192.168.1.100 \
  --tcp-port 1883 --quic-port 14567 \
  --protocols mqtt-tcp,mqtt-quic,zmq-tcp \
  --payloads 64,512,1024 \
  --qos-levels 0,1,2 \
  --seconds 8 \
  --tag batch_all \
  --out results_batch.csv \
  --plot --plot-out charts
```

- 这一次 runner 会依次跑三种协议的组合，写入同一 CSV，并在 `charts/` 生成图表和 summary。
- 如果只测一种协议，把 `--protocols` 改为单项，并在云端只开对应 echo。

### 单次快速测（示例 MQTT-QUIC）

RDK：

```bash
python3 latency_probe.py --role active --protocol mqtt-quic \
  --broker 192.168.1.100 --quic-port 14567 \
  --payload 512 --qos 1 --seconds 8 \
  --id rdk1 --tag quick --out quick.csv
```

云端：

```bash
python3 latency_probe.py --role echo --protocol mqtt-quic \
  --broker 192.168.1.100 --quic-port 14567 --active-id rdk1
```

## 第 4 步：查看结果与绘图

- CSV：`results_batch.csv`（或你指定的文件），含 mean/median/std/p95/n。
- 图表：`charts/` 下的 PNG 与 `summary.csv`（runner 用 `--plot` 已自动生成；否则可手动）：

```bash
python3 plot_latency.py --csv results_batch.csv --out-dir charts
```

## 关键说明

- 时钟同步：RTT 用同一台 RDK 的时间戳，云端仅回显，不依赖两端时钟同步。
- 端口一致性：命令行的 `--tcp-port`/`--quic-port` 必须与 NanoMQ 配置中的监听端口一致。
- 进程数量：要测几种协议，云端就开几个 echo 进程；RDK 端一次 runner 覆盖全部组合即可。
- 无桌面：所有绘图均 `savefig`，无 `plt.show()`。
- QUIC 客户端：使用目录内 `nanomq_cli`；如 CLI 参数与模板不符，可在 `qmole_common.py` 顶部调整 `NANOMQ_PUB_CMD/NANOMQ_SUB_CMD`。

祝实验顺利！
