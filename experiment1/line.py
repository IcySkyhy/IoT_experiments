import spidev
import smbus2 as smbus
import threading
import time
import random
from apds9960.const import *
from apds9960 import APDS9960

# --- 全局配置与状态 ---
LED_COUNT = 32
I2C_PORT = 5           # RDK X5 传感器端口
SPI_BUS = 1            # RDK X5 SPI 总线
THRESHOLD = 100        # 触发阈值 (0-255)

# 共享状态：使用线程事件 (Event) 来同步
hand_detected = threading.Event()
exit_signal = threading.Event()

# --- LED 控制类 (封装自 RGB.ipynb) ---
class LEDController:
    def __init__(self):
        self.spi = spidev.SpiDev()
        self.spi.open(SPI_BUS, 0)
        self.spi.max_speed_hz = 6400000
        self.spi.mode = 0

    def send(self, pixels):
        buf = []
        for r, g, b in pixels:
            for byte in (g, r, b):  # WS2812 顺序：GRB
                for i in range(7, -1, -1):
                    buf.append(0xF8 if byte & (1 << i) else 0xC0)
        buf += [0x00] * 50
        self.spi.xfer2(buf)

    def off(self):
        self.send([(0, 0, 0)] * LED_COUNT)

    def close(self):
        self.spi.close()

# --- 线程 1：传感器检测线程 ---
def sensor_thread():
    print("[Sensor] 线程已启动...")
    bus = smbus.SMBus(I2C_PORT)
    apds = APDS9960(bus)
    apds.enableProximitySensor()

    while not exit_signal.is_set():
        val = apds.readProximity()
        if val > THRESHOLD:
            if not hand_detected.is_set():
                hand_detected.set()
                print(f"检测到人手！当前值: {val}")
        else:
            if hand_detected.is_set():
                hand_detected.clear()
        time.sleep(0.05)  # 20Hz 采样率

# --- 线程 2：LED 响应线程 ---
def led_thread():
    print("[LED] 线程已启动...")
    led = LEDController()
    colors = [(20, 0, 0), (0, 20, 0), (0, 0, 20), (20, 20, 0), (20, 0, 20)]
    
    current_pos = 0
    
    try:
        while not exit_signal.is_set():
            if hand_detected.is_set():
                # 响应模式：随机跳动且颜色变亮
                pixels = [(0, 0, 0)] * LED_COUNT
                random_pos = random.randint(0, LED_COUNT - 1)
                pixels[random_pos] = (50, 50, 50) # 亮白色响应
                led.send(pixels)
                time.sleep(0.05)
            else:
                # 常规模式：平滑跑马灯 (来自 RGB.ipynb 逻辑)
                pixels = [(0, 0, 0)] * LED_COUNT
                color = colors[current_pos % len(colors)]
                pixels[current_pos] = color
                led.send(pixels)
                current_pos = (current_pos + 1) % LED_COUNT
                time.sleep(0.1)
    finally:
        led.off()
        led.close()

# --- 主程序 ---
if __name__ == "__main__":
    t1 = threading.Thread(target=sensor_thread)
    t2 = threading.Thread(target=led_thread)

    t1.start()
    t2.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n正在停止程序...")
        exit_signal.set()
        t1.join()
        t2.join()
        print("程序安全退出。")