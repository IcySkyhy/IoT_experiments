import argparse
import json
import random
import sys
import time

from qmole_common import (
    Debounce,
    Heartbeat,
    MockLED,
    MockSensor,
    Transport,
    TransportConfig,
)

# Hardware tries
try:
    import spidev  # type: ignore
    import smbus2 as smbus  # type: ignore
    from apds9960 import APDS9960  # type: ignore
    from apds9960.const import *  # type: ignore
    HAS_HW = True
except Exception:
    HAS_HW = False

LED_COUNT = 32
THRESHOLD = 100
TIMEOUT_SECONDS = 3.0
HEARTBEAT_INTERVAL = 2.0


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
    p = argparse.ArgumentParser(description="MQTT/QUIC whack-a-mole agent")
    p.add_argument("--broker", required=True)
    p.add_argument("--id", type=int, required=True)
    p.add_argument("--transport", choices=["mqtt", "quic"], default="mqtt")
    p.add_argument("--tcp-port", type=int, default=1883)
    p.add_argument("--quic-port", type=int, default=14567)
    p.add_argument("--qos", type=int, default=1)
    p.add_argument("--mock", action="store_true", help="use mock LED/sensor")
    p.add_argument("--num-agents", type=int, default=3)
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
    debounce = Debounce(min_gap=0.5)

    def on_message(topic: str, payload: str):
        nonlocal is_active, current_score, mole_type, active_time
        try:
            if topic.startswith(f"mole/activate/{agent_id}"):
                data = json.loads(payload)
                current_score = int(data.get("score", 0))
                mole_type = int(data.get("mole_type", 1))
                is_active = True
                active_time = time.time()
                if mole_type == 1:
                    led.on((0, 50, 0))
                    print(f"[{agent_id}] 真地鼠出现！")
                else:
                    led.on((50, 0, 0))
                    print(f"[{agent_id}] 假地鼠出现！")
        except Exception as exc:
            print(f"[agent] msg err: {exc}")

    transport = Transport(cfg, on_message)
    transport.connect()

    agent_id = args.id
    topic_self = f"mole/activate/{agent_id}"
    transport.subscribe(topic_self)

    hb = Heartbeat(transport, agent_id, interval=HEARTBEAT_INTERVAL)
    hb.start()

    is_active = False
    current_score = 0
    mole_type = 1
    active_time = 0

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
                            print(f"[{agent_id}] 命中真地鼠 +1，总分 {current_score}")
                        else:
                            current_score -= 1
                            print(f"[{agent_id}] 误伤假地鼠 -1，总分 {current_score}")
                    else:
                        if mole_type == 1:
                            print(f"[{agent_id}] 超时未击中，总分 {current_score}")
                        else:
                            print(f"[{agent_id}] 成功躲开假地鼠，总分 {current_score}")

                    # choose next
                    candidates = [i for i in range(1, args.num_agents + 1) if i != agent_id]
                    next_id = random.choice(candidates)
                    next_type = random.choices([0, 1], weights=[0.3, 0.7])[0]
                    if hit and debounce.ready():
                        time.sleep(0.2)
                    transport.publish(
                        f"mole/activate/{next_id}",
                        {"score": current_score, "mole_type": next_type},
                    )
            time.sleep(0.02)
    except KeyboardInterrupt:
        print("\nexit")
    finally:
        led.off()
        hb.stop()
        transport.close()


if __name__ == "__main__":
    main()
