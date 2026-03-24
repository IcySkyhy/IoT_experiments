"""Latency probe (ping-pong).

Roles:
- active: 运行在 RDK，定时发送带本地时间戳的 ping，收到 echo 后用同一台 RDK 的时间计算 RTT。
- echo: 运行在云端，收到 ping 立即原样回发（不写 CSV）。
"""
import argparse
import csv
import os
import statistics
import sys
import time
from typing import List

import numpy as np

# Optional imports guarded
try:
    import zmq  # type: ignore
except ImportError:  # pragma: no cover
    zmq = None
try:
    import paho.mqtt.client as mqtt  # type: ignore
except ImportError:  # pragma: no cover
    mqtt = None

from qmole_common import TransportConfig, QuicClient, nanomq_cli_pub


def parse_args():
    p = argparse.ArgumentParser(description="Latency probe (ping-pong RTT from active side)")
    p.add_argument("--protocol", choices=["mqtt-tcp", "mqtt-quic", "zmq-tcp"], required=True)
    p.add_argument("--broker", required=True)
    p.add_argument("--tcp-port", type=int, default=1883)
    p.add_argument("--quic-port", type=int, default=14567)
    p.add_argument("--qos", type=int, default=1)
    p.add_argument("--payload", type=int, default=512)
    p.add_argument("--seconds", type=int, default=8, help="duration to run")
    p.add_argument("--id", default=os.uname().nodename if hasattr(os, "uname") else "node")
    p.add_argument("--tag", default="default")
    p.add_argument("--out", default="latency.csv")
    p.add_argument("--role", choices=["active", "echo"], default="active")
    p.add_argument("--active-id", default="active", help="echo 端需要知道要回给谁，active 端可以忽略")
    return p.parse_args()


def compute_stats(latencies: List[float]):
    if not latencies:
        return None
    mean = sum(latencies) / len(latencies)
    median = statistics.median(latencies)
    std = statistics.pstdev(latencies)
    p95 = float(np.percentile(latencies, 95))
    return {
        "mean": mean,
        "median": median,
        "std": std,
        "p95": p95,
        "n": len(latencies),
    }


def mqtt_tcp_probe(cfg, args, latencies):
    if mqtt is None:
        raise RuntimeError("paho-mqtt not installed")
    topic_ping = "latency/ping"
    topic_echo = f"latency/echo/{args.id}"
    client = mqtt.Client()

    def on_msg(_c, _u, msg):
        try:
            payload = msg.payload.decode("utf-8")
            ts_ns, _body = payload.split(",", 1)
            rtt_ms = (time.time_ns() - int(ts_ns)) / 1e6
            latencies.append(rtt_ms)
        except Exception:
            pass

    if args.role == "active":
        client.on_message = on_msg
        client.connect(cfg.broker, cfg.tcp_port, keepalive=30)
        client.subscribe(topic_echo, qos=args.qos)
        client.loop_start()
        end = time.time() + args.seconds
        payload_body = "x" * args.payload
        try:
            while time.time() < end:
                ts = time.time_ns()
                msg = f"{ts},{payload_body}"
                client.publish(topic_ping, msg, qos=args.qos)
                time.sleep(1)
        finally:
            client.loop_stop()
            client.disconnect()
    else:  # echo role
        def on_ping(_c, _u, msg):
            try:
                payload = msg.payload.decode("utf-8")
                # Echo回同一个 ping 的发送者，通过 echo/<active_id>
                client.publish(f"latency/echo/{args.active_id}", payload, qos=args.qos)
            except Exception:
                pass

        client.connect(cfg.broker, cfg.tcp_port, keepalive=30)
        client.on_message = on_ping
        client.subscribe(topic_ping, qos=args.qos)
        client.loop_forever()


def mqtt_quic_probe(cfg, args, latencies):
    topic_ping = "latency/ping"
    topic_echo = f"latency/echo/{args.id}"

    if args.role == "active":
        def on_message(_topic, payload):
            try:
                ts_ns, _rest = payload.split(",", 1)
                rtt_ms = (time.time_ns() - int(ts_ns)) / 1e6
                latencies.append(rtt_ms)
            except Exception:
                pass

        client = QuicClient(cfg, on_message)
        client.connect()
        client.subscribe(topic_echo)
        payload_body = "x" * args.payload
        end = time.time() + args.seconds
        try:
            while time.time() < end:
                msg = f"{time.time_ns()},{payload_body}"
                nanomq_cli_pub(cfg, topic_ping, msg)
                time.sleep(1)
        finally:
            client.close()
    else:  # echo
        def on_message_echo(_topic, payload):
            try:
                nanomq_cli_pub(cfg, f"latency/echo/{args.active_id}", payload)
            except Exception:
                pass

        client = QuicClient(cfg, on_message_echo)
        client.connect()
        client.subscribe(topic_ping)
        try:
            while True:
                time.sleep(1)
        finally:
            client.close()


def zmq_tcp_probe(cfg, args, latencies):
    if zmq is None:
        raise RuntimeError("pyzmq not installed")
    context = zmq.Context()
    pub = context.socket(zmq.PUB)
    pub.connect(f"tcp://{cfg.broker}:5556")
    sub = context.socket(zmq.SUB)
    sub.connect(f"tcp://{cfg.broker}:5555")
    sub.setsockopt_string(zmq.SUBSCRIBE, "latency")
    poller = zmq.Poller()
    poller.register(sub, zmq.POLLIN)
    payload_body = "x" * args.payload

    if args.role == "active":
        end = time.time() + args.seconds
        try:
            while time.time() < end:
                ts = time.time_ns()
                pub.send_string(f"latency: ping,{ts},{payload_body}")
                for _ in range(1000):
                    socks = dict(poller.poll(1))
                    if sub in socks and socks[sub] == zmq.POLLIN:
                        m = sub.recv_string()
                        try:
                            _, rest = m.split(": ", 1)
                            kind, ts_ns, _rest = rest.split(",", 2)
                            if kind != "echo":
                                continue
                            rtt_ms = (time.time_ns() - int(ts_ns)) / 1e6
                            latencies.append(rtt_ms)
                            break
                        except Exception:
                            pass
                time.sleep(1)
        finally:
            pub.close()
            sub.close()
            context.term()
    else:  # echo role
        try:
            while True:
                socks = dict(poller.poll(1000))
                if sub in socks and socks[sub] == zmq.POLLIN:
                    m = sub.recv_string()
                    try:
                        _, rest = m.split(": ", 1)
                        kind, ts_ns, body = rest.split(",", 2)
                        if kind == "ping":
                            pub.send_string(f"latency: echo,{ts_ns},{body}")
                    except Exception:
                        pass
        finally:
            pub.close()
            sub.close()
            context.term()


def append_csv(path, row_dict):
    header = list(row_dict.keys())
    exists = os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header)
        if not exists:
            w.writeheader()
        w.writerow(row_dict)


def main():
    args = parse_args()
    cfg = TransportConfig(mode="mqtt" if args.protocol == "mqtt-tcp" else "quic", broker=args.broker,
                          tcp_port=args.tcp_port, quic_port=args.quic_port, qos=args.qos)
    latencies: List[float] = []

    if args.protocol == "mqtt-tcp":
        mqtt_tcp_probe(cfg, args, latencies)
    elif args.protocol == "mqtt-quic":
        mqtt_quic_probe(cfg, args, latencies)
    elif args.protocol == "zmq-tcp":
        zmq_tcp_probe(cfg, args, latencies)

    # Only active side writes CSV
    if args.role == "active":
        stats = compute_stats(latencies)
        if not stats:
            print("No samples collected")
            return
        row = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "protocol": args.protocol,
            "broker": args.broker,
            "qos": args.qos,
            "payload": args.payload,
            "tag": args.tag,
            "id": args.id,
            **stats,
        }
        append_csv(args.out, row)
        print("Result:", row)


if __name__ == "__main__":
    main()
