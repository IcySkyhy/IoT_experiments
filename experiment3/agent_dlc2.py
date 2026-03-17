import zmq
import sys
import time
import random
import spidev
import smbus2 as smbus
from apds9960.const import *
from apds9960 import APDS9960

# --- 全局配置 ---
LED_COUNT = 32
I2C_PORT = 5
SPI_BUS = 1
THRESHOLD = 100
TIMEOUT_SECONDS = 3.0
HEARTBEAT_INTERVAL = 2.0

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
        print("用法: sudo python3 agent_dlc2.py <broker_ip> <agent_id>")
        sys.exit(1)

    broker_ip = sys.argv[1]
    agent_id = int(sys.argv[2])

    led = LEDController()
    bus = smbus.SMBus(I2C_PORT)
    apds = APDS9960(bus)
    apds.enableProximitySensor()

    context = zmq.Context()
    publisher = context.socket(zmq.PUB)
    publisher.connect(f"tcp://{broker_ip}:5556")

    subscriber = context.socket(zmq.SUB)
    subscriber.connect(f"tcp://{broker_ip}:5555")
    subscriber.setsockopt_string(zmq.SUBSCRIBE, str(agent_id))
    # Subscribe to GLOBAL channel for online list updates
    subscriber.setsockopt_string(zmq.SUBSCRIBE, "GLOBAL")

    poller = zmq.Poller()
    poller.register(subscriber, zmq.POLLIN)

    is_active = False
    current_score = 0
    mole_type = 1
    active_time = 0
    last_heartbeat_time = 0
    
    # Track online agents dynamically
    online_agents = [agent_id] 
    
    print(f"Agent {agent_id} (DLC2 Dynamic) 启动...")
    led.off()

    try:
        while True:
            socks = dict(poller.poll(50))
            
            if subscriber in socks and socks[subscriber] == zmq.POLLIN:
                message = subscriber.recv_string()
                
                # Check if it's a GLOBAL message
                if message.startswith("GLOBAL"):
                    try:
                        # Format "GLOBAL online 1,2,3"
                        parts = message.split()
                        if len(parts) >= 3 and parts[1] == "online":
                            ids_str = parts[2]
                            new_list = [int(x) for x in ids_str.split(',') if x.isdigit()]
                            online_agents = new_list
                            # print(f"Updated online agents: {online_agents}")
                    except:
                        pass
                else:
                    # Regular game message: "<agent_id>: activate ..."
                    parts = message.split()
                    if len(parts) >= 4 and parts[1] == "activate":
                        # Check destination (although we subscribe to our ID, good to double check or just parse)
                        target = parts[0]
                        if target.startswith(str(agent_id)):
                            current_score = int(parts[2])
                            mole_type = int(parts[3])
                            is_active = True
                            active_time = time.time()
                            
                            if mole_type == 1:
                                led.send([(0, 20, 0)] * LED_COUNT)
                                print(f"\n[{agent_id}] 真地鼠！")
                            else:
                                led.send([(20, 0, 0)] * LED_COUNT)
                                print(f"\n[{agent_id}] 假地鼠！")

            # Heartbeat (same as DLC1)
            if time.time() - last_heartbeat_time > HEARTBEAT_INTERVAL:
                publisher.send_string(f"heartbeat {agent_id}")
                last_heartbeat_time = time.time()

            if is_active:
                val = apds.readProximity()
                is_hit = val > THRESHOLD
                is_timeout = (time.time() - active_time) > TIMEOUT_SECONDS

                if is_hit or is_timeout:
                    led.off()
                    is_active = False
                    
                    if is_hit:
                        if mole_type == 1:
                            current_score += 1
                            print(f"得分+1, 总分: {current_score}")
                        else:
                            current_score -= 1
                            print(f"扣分-1, 总分: {current_score}")
                    elif is_timeout:
                        if mole_type == 1:
                            print("超时逃跑")
                        else:
                            print("成功放过假地鼠")
                    
                    # Select next agent from ONLINE agents
                    candidates = [i for i in online_agents if i != agent_id]
                    
                    if not candidates:
                        print("没有其他在线节点，游戏暂停。等待其他节点上线...")
                    else:
                        next_id = random.choice(candidates)
                        next_type = random.choices([0, 1], weights=[0.3, 0.7])[0]
                        
                        if is_hit:
                            time.sleep(0.5)
                            
                        publisher.send_string(f"{next_id}: activate {current_score} {next_type}")
                        print(f"传球给 Agent {next_id}")

    except KeyboardInterrupt:
        print("\n退出...")
    except Exception as e:
        print(f"\nError: {e}")
    finally:
        led.off()
        led.close()
        context.term()

if __name__ == "__main__":
    main()
