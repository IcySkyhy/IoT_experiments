#!/usr/bin/env python
import zmq
import time
import sys

def main():
    # 可以通过命令行参数指定 Broker IP，默认为本地
    broker_ip = sys.argv[1] if len(sys.argv) > 1 else "localhost"
    target_id = 1  # 初始激活 1 号地鼠机

    context = zmq.Context()
    publisher = context.socket(zmq.PUB)
    
    # 连接到 Broker 的接收端口
    print(f"正在连接到 Broker {broker_ip}:5556 ...")
    publisher.connect(f"tcp://{broker_ip}:5556")
    
    # 必须等待一小段时间，确保连接完全建立，否则第一条消息可能会丢失
    time.sleep(1.0)
    
    # 消息格式: "ID: activate 分数"
    # 初始分数为 0
    start_msg = f"{target_id}: activate 0"
    publisher.send_string(start_msg)
    
    print(f"已发送启动信号: '{start_msg}'。游戏开始！")
    
    publisher.close()
    context.term()

if __name__ == '__main__':
    main()