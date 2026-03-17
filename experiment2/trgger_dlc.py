#!/usr/bin/env python
import zmq
import time
import sys

def main():
    broker_ip = sys.argv[1] if len(sys.argv) > 1 else "localhost"
    target_id = 1

    context = zmq.Context()
    publisher = context.socket(zmq.PUB)
    
    print(f"正在连接到 Broker {broker_ip}:5556 ...")
    publisher.connect(f"tcp://{broker_ip}:5556")
    
    time.sleep(1.0)
    
    # 消息格式: "ID: activate 分数 地鼠类型"
    # 初始分数 0，类型 1 (代表第一个地鼠必为绿色真地鼠)
    initial_score = 0
    mole_type = 1 
    
    start_msg = f"{target_id}: activate {initial_score} {mole_type}"
    publisher.send_string(start_msg)
    
    print(f"已向 Agent {target_id} 发送进阶版启动信号: '{start_msg}'")
    print("规则：绿灯打，红灯别打，3秒不打自动切换。")
    
    publisher.close()
    context.term()

if __name__ == '__main__':
    main()