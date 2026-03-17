import spidev
import smbus2 as smbus
from apds9960.const import *
from apds9960 import APDS9960
import time
import random

# --- 配置参数 ---
LED_COUNT = 32
PROXIMITY_THRESHOLD = 150  # 触发阈值，值越大需要手贴得越近
PORT = 5                   # I2C 端口

# --- 初始化 SPI (LED) ---
spi = spidev.SpiDev()
spi.open(1, 0)
spi.max_speed_hz = 6400000
spi.mode = 0

# --- 初始化 I2C (传感器) ---
bus = smbus.SMBus(PORT)
apds = APDS9960(bus)
apds.enableProximitySensor()

# --- LED 发送函数 ---
def send_pixels(pixels):
    buf = []
    for r, g, b in pixels:
        for byte in (g, r, b):  # WS2812 顺序: GRB
            for i in range(7, -1, -1):
                buf.append(0xF8 if byte & (1 << i) else 0xC0)
    buf += [0x00] * 50  # reset
    spi.xfer2(buf)

def clear_leds():
    send_pixels([(0, 0, 0)] * LED_COUNT)

# --- 游戏逻辑 ---
colors = [
    (20, 0, 0),   # 红
    (0, 20, 0),   # 绿
    (0, 0, 20),   # 蓝
    (20, 20, 0),  # 黄
    (20, 0, 20)   # 紫
]

print("游戏开始！把手靠近传感器来'打地鼠'吧。按 Ctrl+C 退出。")

try:
    while True:
        # 1. 随机生成地鼠位置和颜色
        mole_pos = random.randint(0, LED_COUNT - 1)
        mole_color = random.choice(colors)
        
        # 2. 点亮地鼠
        pixels = [(0, 0, 0)] * LED_COUNT
        pixels[mole_pos] = mole_color
        send_pixels(pixels)
        
        print(f"地鼠出现在位置: {mole_pos}")

        # 3. 等待玩家“打击”
        hit = False
        while not hit:
            val = apds.readProximity()
            if val > PROXIMITY_THRESHOLD:
                print(f"💥 打中了！感应值: {val}")
                # 闪烁一下白色表示打中反馈
                send_pixels([(30, 30, 30)] * LED_COUNT)
                time.sleep(0.1)
                hit = True
            time.sleep(0.05) # 稍微采样快一点

except KeyboardInterrupt:
    print("\n游戏结束")
finally:
    clear_leds()
    spi.close()