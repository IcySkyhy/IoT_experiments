"""Whack-a-Mole agent — Experiment 5 (Docker / K8s).

Key differences vs experiment4/qmole_agent.py:
1. Agent ID can be auto-resolved from K8s environment variables (MY_NODE_NAME)
   so that a single image runs identically on all RDK nodes.
2. Removed RPi.GPIO dependency — sensor uses only apds9960 + smbus2,
   LED uses only spidev WS2812.  This avoids errors in k3s containers.
3. Added --auto-id flag: when set, reads MY_NODE_NAME and maps "pi1"->1, "pi2"->2, etc.
"""

import argparse
import json
import os
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

# Hardware (no RPi.GPIO)
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
HEARTBEAT_INTERVAL = 2.0


# --------------------------
# LED strip (WS2812 via SPI, no RPi.GPIO)
# --------------------------
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


# --------------------------
# Proximity sensor (APDS9960 via smbus2 only, no RPi.GPIO)
# --------------------------
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


# --------------------------
# Auto Agent ID from K8s env
# --------------------------
def resolve_agent_id(args):
    """Determine agent ID from --id or K8s environment variables."""
    if args.id is not None:
        return args.id

    # Auto mode: read from K8s env
    node_name = os.getenv("MY_NODE_NAME", "")
    pod_name = os.getenv("MY_POD_NAME", "")
    pod_ip = os.getenv("MY_POD_IP", "")

    print(f"[K8s Env] MY_NODE_NAME={node_name}, MY_POD_NAME={pod_name}, MY_POD_IP={pod_ip}")

    # Try to extract numeric id from node name, e.g. "pi1" -> 1, "pi2" -> 2
    if node_name:
        digits = "".join(ch for ch in node_name if ch.isdigit())
        if digits:
            aid = int(digits)
            print(f"[Auto-ID] Resolved agent_id={aid} from MY_NODE_NAME='{node_name}'")
            return aid

    # Fallback: hash pod name to a small int
    if pod_name:
        aid = (hash(pod_name) % 100) + 1
        print(f"[Auto-ID] Fallback agent_id={aid} from pod_name hash")
        return aid

    print("[Auto-ID] WARNING: No K8s env found and --id not set; defaulting to 1")
    return 1


# --------------------------
# CLI
# --------------------------
def parse_args():
    p = argparse.ArgumentParser(description="MQTT/QUIC whack-a-mole agent (exp5 Docker/K8s)")
    p.add_argument("--broker", required=True, help="Broker IP/hostname")
    p.add_argument("--id", type=int, default=None,
                   help="Agent ID (if omitted, auto-resolve from K8s MY_NODE_NAME)")
    p.add_argument("--transport", choices=["mqtt", "quic"], default="mqtt")
    p.add_argument("--tcp-port", type=int, default=1883)
    p.add_argument("--quic-port", type=int, default=14567)
    p.add_argument("--qos", type=int, default=1)
    p.add_argument("--mock", action="store_true", help="Use mock LED/sensor (no hardware)")
    p.add_argument("--num-agents", type=int, default=3,
                   help="Total number of agents in the game")
    return p.parse_args()


# --------------------------
# Main
# --------------------------
def main():
    args = parse_args()
    agent_id = resolve_agent_id(args)

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

    is_active = False
    current_score = 0
    mole_type = 1
    active_time = 0.0

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

    topic_self = f"mole/activate/{agent_id}"
    transport.subscribe(topic_self)

    hb = Heartbeat(transport, agent_id, interval=HEARTBEAT_INTERVAL)
    hb.start()

    print(f"=== Agent {agent_id} started (transport={args.transport}, broker={args.broker}) ===")

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

                    # Choose next agent
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
