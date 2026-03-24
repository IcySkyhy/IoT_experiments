"""Dual-side batch runner for ping-pong RTT.

Use this script ONLY on the active (RDK) side; it will call latency_probe with --role active.
On the cloud side, run a simple echo:
    python3 latency_probe.py --role echo --protocol ... --broker ... --tcp-port ... --quic-port ...
Ensure protocol/ports match.
"""
import argparse
import itertools
import subprocess
import sys
from time import sleep


def parse_args():
    p = argparse.ArgumentParser(description="Dual-side batch runner")
    p.add_argument("--protocols", default="mqtt-tcp,mqtt-quic,zmq-tcp")
    p.add_argument("--payloads", default="64,512,1024")
    p.add_argument("--qos-levels", default="0,1,2")
    p.add_argument("--broker", required=True)
    p.add_argument("--tcp-port", type=int, default=1883)
    p.add_argument("--quic-port", type=int, default=14567)
    p.add_argument("--seconds", type=int, default=8)
    p.add_argument("--tag", default="dual")
    p.add_argument("--out", default="latency_dual.csv")
    p.add_argument("--probe", default="latency_probe.py")
    return p.parse_args()


def main():
    args = parse_args()
    protocols = args.protocols.split(",")
    payloads = [int(x) for x in args.payloads.split(",")]
    qos_levels = [int(x) for x in args.qos_levels.split(",")]

    combos = list(itertools.product(protocols, payloads, qos_levels))
    for idx, (proto, payload, qos) in enumerate(combos, 1):
        print(f"[{idx}/{len(combos)}] proto={proto} payload={payload} qos={qos}")
        cmd = [
            sys.executable,
            args.probe,
            "--protocol",
            proto,
            "--broker",
            args.broker,
            "--tcp-port",
            str(args.tcp_port),
            "--quic-port",
            str(args.quic_port),
            "--qos",
            str(qos),
            "--payload",
            str(payload),
            "--seconds",
            str(args.seconds),
            "--tag",
            args.tag,
            "--out",
            args.out,
            "--role",
            "active",
        ]
        subprocess.run(cmd, check=False)


if __name__ == "__main__":
    main()
