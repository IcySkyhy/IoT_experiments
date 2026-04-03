"""Simplified single-node whack-a-mole for Docker quick-test (Task 2/3).

This version runs on a SINGLE RDK and verifies:
  - Sensor reading (APDS9960 / mock)
  - LED control (WS2812 / mock)
  - MQTT communication with cloud broker

Game logic: agent sends activate to itself (self-play), reads sensor, controls LED.
No multi-agent coordination needed — perfect for Docker single-container testing.

Usage:
  # With real hardware inside Docker:
  python3 qmole_single.py --broker 10.0.0.1

  # Mock mode for quick test:
  python3 qmole_single.py --broker 10.0.0.1 --mock
"""

import argparse
import json
import random
import sys
import time

from qmole_common import (
    Debounce,
    MockLED,
    MockSensor,
    Transport,
    TransportConfig,
)

# Hardware (no RPi.GPIO — compatible with k3s containers)
try:
    import spidev  # type: ignore
    import smbus2 as smbus  # type: ignore
    from apds9960 import APDS9960  # type: ignore
    HAS_HW = True
except Exception:
    HAS_HW = False

LED_COUNT = 32
THRESHOLD = 100
TIMEOUT_SECONDS = 3.0
AGENT_ID = 1  # Fixed for single-node test


def build_led(mock: bool):
    if mock or not HAS_HW:
        return MockLED()
    spi = spidev.SpiDev()
    spi.open(1, 0)
    spi.max_speed_hz = 6400000
    spi.mode = 0

    class LedStrip:
        def on(self, color):
            r, g, b = color
            buf = []
            for _ in range(LED_COUNT):
                for byte in (g, r, b):
                    for i in range(7, -1, -1):
                        buf.append(0xF8 if byte & (1 << i) else 0xC0)
            buf += [0x00] * 50
            spi.xfer2(buf)

        def off(self):
            self.on((0, 0, 0))

        def close(self):
            spi.close()

    return LedStrip()


def build_sensor(mock: bool):
    if mock or not HAS_HW:
        return MockSensor()
    bus = smbus.SMBus(5)
    apds = APDS9960(bus)
    apds.enableProximitySensor()

    class Sensor:
        def read(self):
            return apds.readProximity()

    return Sensor()


def parse_args():
    p = argparse.ArgumentParser(description="Single-node whack-a-mole (Docker test)")
    p.add_argument("--broker", required=True, help="MQTT broker IP")
    p.add_argument("--transport", choices=["mqtt", "quic"], default="mqtt")
    p.add_argument("--tcp-port", type=int, default=1883)
    p.add_argument("--quic-port", type=int, default=14567)
    p.add_argument("--qos", type=int, default=1)
    p.add_argument("--mock", action="store_true", help="Use mock LED/sensor")
    p.add_argument("--rounds", type=int, default=10,
                   help="Number of rounds to play (0=infinite)")
    return p.parse_args()


def main():
    args = parse_args()
    cfg = TransportConfig(
        mode=args.transport,
        broker=args.broker,
        tcp_port=args.tcp_port,
        quic_port=args.quic_port,
        qos=args.qos,
    )

    led = build_led(args.mock)
    sensor = build_sensor(args.mock)

    is_active = False
    current_score = 0
    mole_type = 1
    active_time = 0.0

    def on_message(topic: str, payload: str):
        nonlocal is_active, current_score, mole_type, active_time
        try:
            if topic == f"mole/activate/{AGENT_ID}":
                data = json.loads(payload)
                current_score = int(data.get("score", 0))
                mole_type = int(data.get("mole_type", 1))
                is_active = True
                active_time = time.time()
                if mole_type == 1:
                    led.on((0, 50, 0))
                    print(f"[单机] 真地鼠出现！")
                else:
                    led.on((50, 0, 0))
                    print(f"[单机] 假地鼠出现！")
        except Exception as exc:
            print(f"[单机] msg err: {exc}")

    transport = Transport(cfg, on_message)
    transport.connect()
    transport.subscribe(f"mole/activate/{AGENT_ID}")

    print(f"=== 单机打地鼠测试启动 (broker={args.broker}, transport={args.transport}) ===")
    print(f"=== 传感器: {'硬件' if HAS_HW and not args.mock else '模拟'} ===")
    print(f"=== LED: {'硬件' if HAS_HW and not args.mock else '模拟'} ===")

    # Send first activate to self
    time.sleep(1)
    transport.publish(f"mole/activate/{AGENT_ID}",
                      json.dumps({"score": 0, "mole_type": 1}))

    rounds_played = 0
    try:
        while True:
            if is_active:
                val = sensor.read()
                hit = val > THRESHOLD
                timeout = (time.time() - active_time) > TIMEOUT_SECONDS
                if hit or timeout:
                    led.off()
                    is_active = False
                    if hit:
                        if mole_type == 1:
                            current_score += 1
                            print(f"  命中真地鼠 +1，总分 {current_score}")
                        else:
                            current_score -= 1
                            print(f"  误伤假地鼠 -1，总分 {current_score}")
                    else:
                        if mole_type == 1:
                            print(f"  超时未击中，总分 {current_score}")
                        else:
                            print(f"  成功躲开假地鼠，总分 {current_score}")

                    rounds_played += 1
                    if args.rounds > 0 and rounds_played >= args.rounds:
                        print(f"\n=== {rounds_played} 轮结束，最终得分: {current_score} ===")
                        break

                    # Send next activate to self
                    next_type = random.choices([0, 1], weights=[0.3, 0.7])[0]
                    time.sleep(0.3)
                    transport.publish(
                        f"mole/activate/{AGENT_ID}",
                        json.dumps({"score": current_score, "mole_type": next_type}),
                    )
            time.sleep(0.02)
    except KeyboardInterrupt:
        print(f"\n手动退出，最终得分: {current_score}")
    finally:
        led.off()
        transport.close()

    print("=== 单机测试完成 ===")


if __name__ == "__main__":
    main()
