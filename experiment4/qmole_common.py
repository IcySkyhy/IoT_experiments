"""Common utilities for MQTT/QUIC Whack-a-Mole (NanoMQ) and latency tests.

Features
- Transport abstraction: MQTT over TCP (paho-mqtt) and MQTT over QUIC via external nanomq_cli.
- Heartbeat helper for agents.
- Optional mock hardware (LED/sensor) when running on PC.

Notes
- nanomq_cli command-line switches may differ by build. Adjust NANOMQ_PUB_CMD / NANOMQ_SUB_CMD templates below if needed.
- QUIC path uses subprocess-based pub/sub; ensure nanomq_cli is executable on the target OS (Linux/RDK).
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
except ImportError:  # pragma: no cover
    mqtt = None  # Will be guarded in code

# --------------------------
# Configuration
# --------------------------
NANOMQ_CLI_DEFAULT = os.environ.get("NANOMQ_CLI", "./nanomq_cli")


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
        # Simulate proximity spike every ~80ms when counter hits multiples of 15
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
        cmd = [
            NANOMQ_CLI_DEFAULT,
            "sub",
            "-h", self.cfg.broker,
            "-p", str(self.cfg.quic_port),
            "-t", self.topic,
            "-q", str(self.cfg.qos),
            "--quic",
        ]
        print(f"[QUIC sub] starting: {' '.join(cmd)}", flush=True)
        try:
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                         stderr=subprocess.DEVNULL,
                                         stdin=subprocess.DEVNULL, text=True)
            if not self.proc.stdout:
                return
            print(f"[QUIC sub] process started, waiting for messages on {self.topic}", flush=True)
            for line in self.proc.stdout:
                if self._stop.is_set():
                    break
                line = line.strip()
                if not line:
                    continue
                # nanomq_cli sub outputs "topic: payload" format
                if ": " in line:
                    recv_topic, _, payload = line.partition(": ")
                    payload = payload.strip()
                else:
                    recv_topic = self.topic
                    payload = line
                if not payload:
                    continue
                # Skip non-payload status lines
                if not payload.startswith("{") and not payload.startswith("["):
                    print(f"[QUIC sub info] {line}", flush=True)
                    continue
                try:
                    self.on_message(recv_topic, payload)
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
    msg = json.dumps(payload) if isinstance(payload, (dict, list)) else str(payload)
    cmd = [
        NANOMQ_CLI_DEFAULT,
        "pub",
        "-h", cfg.broker,
        "-p", str(cfg.quic_port),
        "-t", topic,
        "-q", str(cfg.qos),
        "-l",
        "--quic",
    ]
    subprocess.run(cmd, input=msg + "\n", text=True, check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class QuicClient:
    def __init__(self, cfg: TransportConfig, on_message: Callable[[str, str], None]):
        self.cfg = cfg
        self.on_message = on_message
        self.sub_threads: list[NanoMQCliSub] = []

    def connect(self):
        # nothing to do; each sub starts its own process
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
    def __init__(self, transport: Transport, agent_id: int, interval: float = 2.0):
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
