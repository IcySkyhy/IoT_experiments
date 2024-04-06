import time
import argparse
import sys
import select

# Read command line arguments: number of message, payload size
parser = argparse.ArgumentParser(description='Process some integers.')
# parser.add_argument('num_messages', type=int, help='number of messages')
parser.add_argument('payload_size', type=int, help='payload size')
parser.add_argument('protocol', choices=['zmq-tcp', 'quic'], help='protocol')
args = parser.parse_args()

latencies = []

def print_stat():
    # Output mean, median, std of latencies to stderr
    mean = sum(latencies) / len(latencies)
    print('Mean latency: ', mean, file=sys.stderr)
    sorted_latencies = sorted(latencies)
    median = sorted_latencies[len(sorted_latencies) // 2]
    print('Median latency: ', median, file=sys.stderr)
    std = (sum([(x - mean) ** 2 for x in latencies]) / len(latencies)) ** 0.5
    print('Standard deviation of latency: ', std, file=sys.stderr)

def process_message(message):
    # Split with space or comma
    timestamp, payload = message.split(' ')[1].split(',')
    latency_ns = time.time_ns() - int(timestamp)
    # Convert to milliseconds
    latency_ms = latency_ns / 1e6
    latencies.append(latency_ms)

def process_received_messages_quic():
    # Read from stdin
    data_available = True
    while data_available:
        # Use select with a zero timeout to check for availability of more data
        if select.select([sys.stdin], [], [], 0)[0]:
            message = sys.stdin.readline()
            if not message.startswith('test'):
                continue
            process_message(message)
        else:
            data_available = False
    if len(latencies) > 0:
        print_stat()

if args.protocol == 'zmq-tcp':
    import zmq
    context = zmq.Context()
    publisher = context.socket(zmq.PUB)
    publisher.connect('tcp://10.0.0.1:5556')
    subscriber = context.socket(zmq.SUB)
    subscriber.connect('tcp://10.0.0.1:5555')
    subscriber.setsockopt_string(zmq.SUBSCRIBE, 'test')
    poller = zmq.Poller()
    poller.register(subscriber, zmq.POLLIN)

while True:
    # Timestamp in nanoseconds
    timestamp = str(time.time_ns())
    payload = 'a' * args.payload_size
    message = timestamp + ',' + payload
    if args.protocol == 'quic':
        print(message, flush=True)
    else:
        publisher.send_string("test: " + message)
    # Wait for stdin for 1ms, 1000 times -- 1 second per sent message
    for _ in range(1000):
        if args.protocol == 'quic':
            i, o, e = select.select([sys.stdin], [], [], 0.001)
            if i:
                process_received_messages_quic()
        else:
            # Poll for 1ms
            socks = dict(poller.poll(1))
            if subscriber in socks and socks[subscriber] == zmq.POLLIN:
                message = subscriber.recv_string()
                process_message(message)
    if args.protocol == 'zmq-tcp':
        if len(latencies) > 0:
            print_stat()
