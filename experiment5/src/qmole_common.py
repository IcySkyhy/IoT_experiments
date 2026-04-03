"""Common utilities for MQTT/QUIC Whack-a-Mole (NanoMQ) — Experiment 5 Docker/K8s version.

Changes vs experiment4:
- Removed RPi.GPIO dependency (k3s container incompatible).
- Sensor via apds9960 only (smbus2), no RPi.GPIO needed.
- LED via spidev WS2812 only, no RPi.GPIO needed.
"""

import json
import os
import queue
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

try:
    import paho.mqtt.client as mqtt  # type: ignore
except ImportError:
    mqtt = None

# --------------------------
# Configuration
# --------------------------
NANOMQ_CLI_DEFAULT = os.environ.get("NANOMQ_CLI", "./nanomq_cli")
NANOMQ_PUB_CMD = "{cli} pub -h {host} -p {port} -t {topic} -m {message} --quic -q {qos}"
NANOMQ_SUB_CMD = "{cli} sub -h {host} -p {port} -t {topic} --quic -q {qos}"


@dataclass
class TransportConfig:
    mode: str  # "mqtt" or "quic"
    broker: str
    tcp_port: int = 1883
    quic_port: int = 14567
    qos: int = 1


# --------------------------
# Mock hardware helpers
# --------------------------
class MockLED:
    def on(self, color):
        print(f"[MOCK LED] ON {color}")

    def off(self):
        print("[MOCK LED] OFF")


class MockSensor:
    def __init__(self):
        self._counter = 0

    def read(self):
        self._counter += 1
        return 200 if self._counter % 15 == 0 else 20


# --------------------------
# MQTT (TCP) client wrapper
# --------------------------
class MqttClient:
    def __init__(self, cfg: TransportConfig, on_message: Callable[[str, str], None]):
        if mqtt is None:
            raise RuntimeError("paho-mqtt not installed; install via pip -r requirements.txt")
        self.cfg = cfg
        self.on_message = on_message
        self.client = mqtt.Client()
        self.client.on_message = self._on_msg

    def _on_msg(self, _client, _userdata, msg):
        try:
            payload = msg.payload.decode("utf-8")
            self.on_message(msg.topic, payload)
        except Exception as exc:
            print(f"[MQTT] decode error: {exc}")

    def connect(self):
        self.client.connect(self.cfg.broker, self.cfg.tcp_port, keepalive=30)
        self.client.loop_start()

    def subscribe(self, topic: str):
        self.client.subscribe(topic, qos=self.cfg.qos)

    def publish(self, topic: str, payload: str):
        self.client.publish(topic, payload, qos=self.cfg.qos)

    def close(self):
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:
            pass


# --------------------------
# NanoMQ CLI (QUIC) wrapper
# --------------------------
class NanoMQCliSub(threading.Thread):
    def __init__(self, cfg: TransportConfig, topic: str, on_message: Callable[[str, str], None]):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.topic = topic
        self.on_message = on_message
        self.proc: Optional[subprocess.Popen] = None
        self._stop = threading.Event()

    def run(self):
        cmd = NANOMQ_SUB_CMD.format(
            cli=NANOMQ_CLI_DEFAULT,
            host=self.cfg.broker,
            port=self.cfg.quic_port,
            topic=self.topic,
            qos=self.cfg.qos,
        ).split()
        try:
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            if not self.proc.stdout:
                return
            for line in self.proc.stdout:
                if self._stop.is_set():
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    self.on_message(self.topic, line)
                except Exception as exc:
                    print(f"[QUIC sub] parse err: {exc}")
        finally:
            if self.proc:
                self.proc.terminate()

    def stop(self):
        self._stop.set()
        if self.proc:
            try:
                self.proc.terminate()
            except Exception:
                pass


def nanomq_cli_pub(cfg: TransportConfig, topic: str, payload: str):
    cmd = NANOMQ_PUB_CMD.format(
        cli=NANOMQ_CLI_DEFAULT,
        host=cfg.broker,
        port=cfg.quic_port,
        topic=topic,
        message=json.dumps(payload) if isinstance(payload, (dict, list)) else payload,
        qos=cfg.qos,
    ).split()
    subprocess.run(cmd, check=False)


class QuicClient:
    def __init__(self, cfg: TransportConfig, on_message: Callable[[str, str], None]):
        self.cfg = cfg
        self.on_message = on_message
        self.sub_threads: list[NanoMQCliSub] = []

    def connect(self):
        return

    def subscribe(self, topic: str):
        t = NanoMQCliSub(self.cfg, topic, self.on_message)
        t.start()
        self.sub_threads.append(t)

    def publish(self, topic: str, payload: str):
        nanomq_cli_pub(self.cfg, topic, payload)

    def close(self):
        for t in self.sub_threads:
            t.stop()


# --------------------------
# Transport factory
# --------------------------
class Transport:
    def __init__(self, cfg: TransportConfig, on_message: Callable[[str, str], None]):
        self.cfg = cfg
        if cfg.mode == "mqtt":
            self.client = MqttClient(cfg, on_message)
        elif cfg.mode == "quic":
            self.client = QuicClient(cfg, on_message)
        else:
            raise ValueError("cfg.mode must be 'mqtt' or 'quic'")

    def connect(self):
        self.client.connect()

    def subscribe(self, topic: str):
        self.client.subscribe(topic)

    def publish(self, topic: str, payload: str):
        if isinstance(payload, (dict, list)):
            payload = json.dumps(payload)
        self.client.publish(topic, payload)

    def close(self):
        self.client.close()


# --------------------------
# Heartbeat helper
# --------------------------
class Heartbeat(threading.Thread):
    def __init__(self, transport: Transport, agent_id, interval: float = 2.0):
        super().__init__(daemon=True)
        self.transport = transport
        self.agent_id = agent_id
        self.interval = interval
        self._stop = threading.Event()

    def run(self):
        topic = f"mole/heartbeat/{self.agent_id}"
        while not self._stop.is_set():
            self.transport.publish(topic, "alive")
            time.sleep(self.interval)

    def stop(self):
        self._stop.set()


# --------------------------
# Simple debounce timer
# --------------------------
class Debounce:
    def __init__(self, min_gap: float):
        self.min_gap = min_gap
        self.last = 0.0

    def ready(self):
        now = time.time()
        if now - self.last >= self.min_gap:
            self.last = now
            return True
        return False
