#!/usr/bin/env python3
import zmq
import time
import sys


def main():
    broker_ip = sys.argv[1] if len(sys.argv) > 1 else "localhost"
    target_id = 1  # 游戏从 Agent 1 开始

    context = zmq.Context()
    publisher = context.socket(zmq.PUB)

    print(f"正在连接到 Broker {broker_ip}:5556 ...")
    publisher.connect(f"tcp://{broker_ip}:5556")

    # 等待连接建立，避免第一条消息丢失
    time.sleep(1.0)

    # 消息格式: "<agent_id>: activate <初始分数> <地鼠类型>"
    initial_score = 0
    mole_type = 1  # 1=真地鼠（绿灯）

    start_msg = f"{target_id}: activate {initial_score} {mole_type}"
    publisher.send_string(start_msg)

    print(f"已向 Agent {target_id} 发送启动信号: '{start_msg}'")

    publisher.close()
    context.term()


if __name__ == "__main__":
    main()
