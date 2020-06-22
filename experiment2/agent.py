#!/usr/bin/env python

import zmq
import sys
import time
from random import randint

numofagents = 4


def main(id):
    context = zmq.Context()
    publisher = context.socket(zmq.PUB)
    publisher.connect("tcp://localhost:5556")

    subscriber = context.socket(zmq.SUB)
    subscriber.connect("tcp://localhost:5555")
    subscriber.setsockopt_string(zmq.SUBSCRIBE, str(id))
    while True:
        message = subscriber.recv()
        print('%d: %s' % (id, message))
        time.sleep(.5)
        publisher.send_string('%d: %s' % (randint(1, numofagents), 'activate'))


if __name__ == "__main__":
    id = 1
    if len(sys.argv) > 1:
        id = sys.argv[1]
    id = int(id)
    main(id)
