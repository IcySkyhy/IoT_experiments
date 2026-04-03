"""Whack-a-Mole trigger — send an initial activate to kick off the game.

Usage:
  python3 qmole_trigger.py --broker 10.0.0.1 --target 1
"""

import argparse
import json
import time

from qmole_common import Transport, TransportConfig


def parse_args():
    p = argparse.ArgumentParser(description="Whack-a-mole trigger (exp5)")
    p.add_argument("--broker", required=True)
    p.add_argument("--transport", choices=["mqtt", "quic"], default="mqtt")
    p.add_argument("--tcp-port", type=int, default=1883)
    p.add_argument("--quic-port", type=int, default=14567)
    p.add_argument("--qos", type=int, default=1)
    p.add_argument("--target", type=int, default=1, help="Target agent ID")
    p.add_argument("--score", type=int, default=0)
    p.add_argument("--mole-type", type=int, choices=[0, 1], default=1)
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
    transport = Transport(cfg, on_message=lambda t, p: None)
    transport.connect()
    topic = f"mole/activate/{args.target}"
    payload = {"score": args.score, "mole_type": args.mole_type}
    transport.publish(topic, payload)
    print(f"Sent activate to agent {args.target}: {json.dumps(payload)}")
    time.sleep(0.5)
    transport.close()


if __name__ == "__main__":
    main()
