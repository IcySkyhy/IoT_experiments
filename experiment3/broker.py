#!/usr/bin/env python3
import zmq


def main():
    context = zmq.Context()

    # 面向订阅者（Agents）的端口：XPUB 5555
    frontend = context.socket(zmq.XPUB)
    frontend.bind("tcp://*:5555")

    # 面向发布者（Agents）的端口：XSUB 5556
    backend = context.socket(zmq.XSUB)
    backend.bind("tcp://*:5556")

    print("Broker 启动，监听 5555/5556 ...")

    # 透明代理：将所有消息双向转发
    zmq.proxy(frontend, backend)

    # 正常情况下不会到达这里
    frontend.close()
    backend.close()
    context.term()


if __name__ == "__main__":
    main()
