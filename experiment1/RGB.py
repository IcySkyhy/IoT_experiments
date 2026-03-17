import spidev
import time

spi = spidev.SpiDev()
spi.open(1, 0)  # RDK X5 是 bus 1（不是 0）
spi.max_speed_hz = 6400000
spi.mode = 0

def send(pixels):
    buf = []
    for r, g, b in pixels:
        for byte in (g, r, b):  # WS2812 传输顺序：GRB
            for i in range(7, -1, -1):
                buf.append(0xF8 if byte & (1 << i) else 0xC0)
    buf += [0x00] * 50  # ≥50µs 低电平 reset
    spi.xfer2(buf)

LED_COUNT = 32
# 定义各种颜色
RED = (20, 0, 0)      # 红色
GREEN = (0, 20, 0)    # 绿色
BLUE = (0, 0, 20)     # 蓝色
YELLOW = (20, 20, 0)  # 黄色
PURPLE = (20, 0, 20)  # 紫色
CYAN = (0, 20, 20)    # 青色
ORANGE = (20, 10, 0)  # 橙色
PINK = (20, 0, 10)    # 粉色
WHITE = (20, 20, 20)  # 白色

colors = [RED, GREEN, BLUE, YELLOW, PURPLE, CYAN, ORANGE, PINK, WHITE]

# 实现跑马灯效果：LED灯逐个点亮，每个灯使用不同颜色
for t in range(LED_COUNT):
    pixels = []
    for i in range(LED_COUNT):
        if i == t:
            # 循环使用颜色列表中的颜色
            color_index = t % len(colors)
            pixels.append(colors[color_index])
        else:
            pixels.append((0, 0, 0))
    send(pixels)
    time.sleep(0.1)  # 每个LED点亮0.1秒

send([(0, 0, 0)] * LED_COUNT)  # 熄灭所有LED
spi.close()