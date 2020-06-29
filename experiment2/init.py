#!/usr/bin/env python

import zmq
import time


if __name__ == '__main__':
    context = zmq.Context()
    publisher = context.socket(zmq.PUB)
    publisher.connect("tcp://localhost:5556")
    time.sleep(0.5)
    publisher.send_string('%d: %s' % (1, 'activate'))
    publisher.close()
