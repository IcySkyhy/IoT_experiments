#!/usr/bin/env python
import zmq
import time

def main():
    try:
        context = zmq.Context()

        # Socket facing clients (Subscribers connect here)
        frontend = context.socket(zmq.XPUB)
        frontend.bind("tcp://*:5555")

        # Socket facing services (Publishers connect here)
        backend = context.socket(zmq.XSUB)
        backend.bind("tcp://*:5556")

        poller = zmq.Poller()
        poller.register(frontend, zmq.POLLIN)
        poller.register(backend, zmq.POLLIN)

        # Dictionary to store last seen time of agents: {agent_id: timestamp}
        heartbeats = {}
        HEARTBEAT_TIMEOUT = 5.0 # Seconds before considering a node offline
        last_check_time = time.time()

        print("Broker (DLC1) started. Listening for heartbeats...")

        while True:
            # Poll with short timeout 
            socks = dict(poller.poll(50))
            current_time = time.time()

            # Handle messages from publishers (Agents sending data)
            if backend in socks:
                try:
                    msg_parts = backend.recv_multipart()
                    
                    # Check for heartbeat message
                    try:
                        # msg_parts[0] is typically the topic
                        msg_str = msg_parts[0].decode('utf-8')
                        if msg_str.startswith("heartbeat"):
                            # Format: "heartbeat <agent_id>" 
                            parts = msg_str.split()
                            if len(parts) >= 2:
                                agent_id = parts[1]
                                heartbeats[agent_id] = current_time
                                # print(f"Heartbeat from {agent_id}")
                    except Exception:
                        pass # Not a text message or parse error

                    # Forward message to subscribers (XPUB)
                    frontend.send_multipart(msg_parts)
                except zmq.ZMQError:
                    pass

            # Handle subscriptions from subscribers (Agents subscribing)
            if frontend in socks:
                try:
                    msg_parts = frontend.recv_multipart()
                    backend.send_multipart(msg_parts)
                except zmq.ZMQError:
                    pass

            # Periodic cleanup and logging of online nodes (every 2 seconds)
            if current_time - last_check_time > 2.0:
                online_agents = []
                to_remove = []
                
                for aid, last_time in heartbeats.items():
                    if current_time - last_time < HEARTBEAT_TIMEOUT:
                        online_agents.append(aid)
                    else:
                        to_remove.append(aid)
                
                for aid in to_remove:
                    del heartbeats[aid]
                    print(f"Agent {aid} timed out (offline).")
                
                if online_agents:
                    print(f"Current Online Agents: {sorted(online_agents)}")
                
                last_check_time = current_time

    except KeyboardInterrupt:
        print("\nInterrupted")
    finally:
        frontend.close()
        backend.close()
        context.term()

if __name__ == "__main__":
    main()
