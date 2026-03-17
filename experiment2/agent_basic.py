import zmq
import sys
import time
import random
import spidev
import smbus2 as smbus
from apds9960.const import *
from apds9960 import APDS9960

# --- 全局配置 ---
num_agents = 3         # 参与游戏的设备总数
LED_COUNT = 32         # LED 灯珠数量
I2C_PORT = 5           # RDK X5 传感器端口
SPI_BUS = 1            # RDK X5 SPI 总线
THRESHOLD = 100        # APDS9960 触发阈值

# --- LED 控制类 (参考 line.py) ---
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
        print("用法: sudo python3 agent_basic.py <broker_ip> <agent_id>")
        sys.exit(1)

    broker_ip = sys.argv[1]
    agent_id = int(sys.argv[2])

    # --- 硬件初始化 ---
    led = LEDController()
    bus = smbus.SMBus(I2C_PORT)
    apds = APDS9960(bus)
    apds.enableProximitySensor()

    # --- ZMQ 网络初始化 ---
    context = zmq.Context()
    publisher = context.socket(zmq.PUB)
    publisher.connect(f"tcp://{broker_ip}:5556")

    subscriber = context.socket(zmq.SUB)
    subscriber.connect(f"tcp://{broker_ip}:5555")
    subscriber.setsockopt_string(zmq.SUBSCRIBE, str(agent_id))

    # 使用 Poller 实现非阻塞接收，这样可以同时检测传感器
    poller = zmq.Poller()
    poller.register(subscriber, zmq.POLLIN)

    is_active = False
    current_score = 0
    
    print(f"Agent {agent_id} 启动，等待地鼠出现...")
    led.off()

    try:
        while True:
            # 轮询等待消息，超时时间为 50ms
            socks = dict(poller.poll(50))
            if subscriber in socks and socks[subscriber] == zmq.POLLIN:
                message = subscriber.recv_string()
                # 预期的消息格式: "<agent_id>: activate <score>"
                parts = message.split()
                if len(parts) >= 3 and parts[1] == "activate":
                    current_score = int(parts[2])
                    is_active = True
                    # 亮绿灯代表地鼠出现
                    led.send([(0, 20, 0)] * LED_COUNT)
                    print(f"[{agent_id}] 出现地鼠！当前总分: {current_score}")

            # 如果当前节点被激活，则持续检测传感器
            if is_active:
                val = apds.readProximity()
                if val > THRESHOLD:
                    # 手靠近，打中地鼠
                    led.off()
                    is_active = False
                    current_score += 1
                    print(f"[{agent_id}] 啪！打中了！得分+1，当前总分: {current_score}")
                    
                    # 随机选择下一个节点 (排除自己)
                    candidates = [i for i in range(1, num_agents + 1) if i != agent_id]
                    next_id = random.choice(candidates)
                    
                    # 避免手还没拿开就误触下一个回合，暂停一下
                    time.sleep(0.5) 
                    # 发送消息给下一个节点
                    publisher.send_string(f"{next_id}: activate {current_score}")
                    
    except KeyboardInterrupt:
        print("\n退出游戏...")
    finally:
        led.off()
        led.close()
        context.term()

if __name__ == "__main__":
    main()