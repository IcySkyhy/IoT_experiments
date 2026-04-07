import zmq
import sys
import time
import random
import spidev
import smbus2 as smbus
from apds9960.const import *
from apds9960 import APDS9960

# --- 全局配置 ---
num_agents = 3
LED_COUNT = 32
I2C_PORT = 5
SPI_BUS = 1
THRESHOLD = 100
TIMEOUT_SECONDS = 3.0  # 地鼠停留的时间（秒）

# --- LED 控制类（通过SPI驱动WS2812）---
class LEDController:
    def __init__(self):
        self.spi = spidev.SpiDev()
        self.spi.open(SPI_BUS, 0)
        self.spi.max_speed_hz = 6400000
        self.spi.mode = 0

    def send(self, pixels):
        buf = []
        for r, g, b in pixels:
            for byte in (g, r, b):
                for i in range(7, -1, -1):
                    buf.append(0xF8 if byte & (1 << i) else 0xC0)
        buf += [0x00] * 50
        self.spi.xfer2(buf)

    def off(self):
        self.send([(0, 0, 0)] * LED_COUNT)

    def close(self):
        self.spi.close()

def main():
    if len(sys.argv) < 3:
        print("用法: sudo python3 agent.py <broker_ip> <agent_id>")
        print("示例: sudo python3 agent.py 172.27.0.1 2")
        sys.exit(1)

    broker_ip = sys.argv[1]
    agent_id = int(sys.argv[2])

    led = LEDController()
    bus = smbus.SMBus(I2C_PORT)
    apds = APDS9960(bus)
    apds.enableProximitySensor()

    context = zmq.Context()

    # Publisher: 向broker发消息（连接到broker的XSUB端口5556）
    publisher = context.socket(zmq.PUB)
    publisher.connect(f"tcp://{broker_ip}:5556")

    # Subscriber: 订阅自己的ID（连接到broker的XPUB端口5555）
    subscriber = context.socket(zmq.SUB)
    subscriber.connect(f"tcp://{broker_ip}:5555")
    subscriber.setsockopt_string(zmq.SUBSCRIBE, str(agent_id))

    poller = zmq.Poller()
    poller.register(subscriber, zmq.POLLIN)

    is_active = False
    current_score = 0
    mole_type = 1       # 1: 真地鼠(绿灯), 0: 假地鼠(红灯)
    active_time = 0     # 记录地鼠出现的时间

    print(f"Agent {agent_id} 启动，等待地鼠出现...")
    led.off()

    try:
        while True:
            socks = dict(poller.poll(50))  # 50ms 超时轮询

            if subscriber in socks and socks[subscriber] == zmq.POLLIN:
                message = subscriber.recv_string()
                # 消息格式: "<agent_id>: activate <score> <mole_type>"
                parts = message.split()
                if len(parts) >= 4 and parts[1] == "activate":
                    current_score = int(parts[2])
                    mole_type = int(parts[3])
                    is_active = True
                    active_time = time.time()

                    if mole_type == 1:
                        led.send([(0, 20, 0)] * LED_COUNT)  # 绿灯：真地鼠
                        print(f"\n[{agent_id}] 真地鼠出现（绿灯）！快打它！")
                    else:
                        led.send([(20, 0, 0)] * LED_COUNT)  # 红灯：假地鼠
                        print(f"\n[{agent_id}] 假地鼠出现（红灯）！千万别打！")

            if is_active:
                val = apds.readProximity()
                is_hit = val > THRESHOLD
                is_timeout = (time.time() - active_time) > TIMEOUT_SECONDS

                if is_hit or is_timeout:
                    led.off()
                    is_active = False

                    # 结算逻辑
                    if is_hit:
                        if mole_type == 1:
                            current_score += 1
                            print(f"[{agent_id}] 啪！好球！得分+1，总分: {current_score}")
                        else:
                            current_score -= 1
                            print(f"[{agent_id}] 哎呀！误伤假地鼠！扣分-1，总分: {current_score}")
                    elif is_timeout:
                        if mole_type == 1:
                            print(f"[{agent_id}] 动作太慢，真地鼠逃跑了。总分: {current_score}")
                        else:
                            print(f"[{agent_id}] 成功放过假地鼠，干得漂亮。总分: {current_score}")

                    # 选择下一个节点并发送激活消息
                    candidates = [i for i in range(1, num_agents + 1) if i != agent_id]
                    next_id = random.choice(candidates)
                    # 70% 真地鼠，30% 假地鼠
                    next_type = random.choices([0, 1], weights=[0.3, 0.7])[0]

                    if is_hit:
                        time.sleep(0.5)  # 防止手未离开就触发下一节点

                    publisher.send_string(f"{next_id}: activate {current_score} {next_type}")

    except KeyboardInterrupt:
        print("\n退出游戏...")
    except Exception as e:
        print(f"\n错误: {e}")
    finally:
        led.off()
        led.close()
        context.term()

if __name__ == "__main__":
    main()
