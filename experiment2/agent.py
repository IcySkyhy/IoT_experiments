import zmq
import sys
import time
from random import randint

num_agents = 3
broker_ip = sys.argv[1]
agent_id = int(sys.argv[2])


def main(agent_id):
    context = zmq.Context()
    publisher = context.socket(zmq.PUB)
    publisher.connect("tcp://%s:5556" % broker_ip)

    subscriber = context.socket(zmq.SUB)
    subscriber.connect("tcp://%s:5555" % broker_ip)
    subscriber.setsockopt_string(zmq.SUBSCRIBE, str(agent_id))
    while True:
        message = subscriber.recv()
        print('%d: %s' % (agent_id, message))
        # YOUR CODE HERE: add code for the sensors and LED HAT



        time.sleep(.5)
        publisher.send_string('%d: %s' % (randint(1, num_agents), 'activate'))

main(agent_id)
