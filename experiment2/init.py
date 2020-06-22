#!/usr/bin/env python

import zmq


if __name__ == '__main__':
    context = zmq.Context()
    publisher = context.socket(zmq.PUB)
    publisher.connect("tcp://localhost:5556")
    publisher.send_string('%d: %s' % (1, 'activate'))
    publisher.close()
