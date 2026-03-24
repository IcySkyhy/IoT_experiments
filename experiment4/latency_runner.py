"""Batch runner for latency_probe across parameter combinations (active side only).

Echo 端请运行 latency_probe.py --role echo（匹配同样的协议/端口），本脚本仅用于 active 端批量发起并记录 RTT。
可选自动绘图（headless）。
"""
import argparse
import itertools
import os
import subprocess
import sys

from plot_latency import main as plot_main  # reuse plotting without plt.show


def parse_args():
    p = argparse.ArgumentParser(description="Batch latency runner")
    p.add_argument("--protocols", default="mqtt-tcp,mqtt-quic,zmq-tcp")
    p.add_argument("--payloads", default="64,512,1024")
    p.add_argument("--qos-levels", default="0,1,2")
    p.add_argument("--broker", required=True)
    p.add_argument("--tcp-port", type=int, default=1883)
    p.add_argument("--quic-port", type=int, default=14567)
    p.add_argument("--seconds", type=int, default=8)
    p.add_argument("--tag", default="batch")
    p.add_argument("--out", default="latency_batch.csv")
    p.add_argument("--probe", default="latency_probe.py")
    p.add_argument("--plot", action="store_true", help="plot after run")
    p.add_argument("--plot-out", default="charts", help="output dir for plots")
    return p.parse_args()


def main():
    args = parse_args()
    protocols = args.protocols.split(",")
    payloads = [int(x) for x in args.payloads.split(",")]
    qos_levels = [int(x) for x in args.qos_levels.split(",")]

    combos = list(itertools.product(protocols, payloads, qos_levels))
    for proto, payload, qos in combos:
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
        print("Running:", " ".join(cmd))
        subprocess.run(cmd, check=False)

    # Optional plotting (headless)
    if args.plot and os.path.exists(args.out):
        plot_sys_argv = [sys.argv[0], "--csv", args.out, "--out-dir", args.plot_out]
        # plot_main expects to parse sys.argv; emulate
        orig_argv = sys.argv
        try:
            sys.argv = plot_sys_argv
            plot_main()
        finally:
            sys.argv = orig_argv


if __name__ == "__main__":
    main()
