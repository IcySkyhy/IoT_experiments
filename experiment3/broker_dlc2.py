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
        HEARTBEAT_TIMEOUT = 5.0 
        last_check_time = time.time()
        last_broadcast_time = time.time()

        print("Broker (DLC2) started. Broadcasting online agents...")

        while True:
            socks = dict(poller.poll(50))
            current_time = time.time()

            # Handle messages from publishers (Agents sending data)
            if backend in socks:
                try:
                    msg_parts = backend.recv_multipart()
                    try:
                        msg_str = msg_parts[0].decode('utf-8')
                        if msg_str.startswith("heartbeat"):
                            parts = msg_str.split()
                            if len(parts) >= 2:
                                agent_id = parts[1]
                                heartbeats[agent_id] = current_time
                    except Exception:
                        pass
                    frontend.send_multipart(msg_parts)
                except zmq.ZMQError:
                    pass

            # Handle subscriptions from subscribers 
            if frontend in socks:
                try:
                    msg_parts = frontend.recv_multipart()
                    backend.send_multipart(msg_parts)
                except zmq.ZMQError:
                    pass

            # Periodic cleanup and broadcast
            if current_time - last_check_time > 1.0: # Check every second
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
                
                # Broadcast online list every 2 seconds or so
                if current_time - last_broadcast_time > 2.0:
                    if online_agents:
                        # Format: "GLOBAL online 1,2,3"
                        agents_str = ",".join(sorted(online_agents))
                        # Agents subscribe to "GLOBAL"
                        msg = f"GLOBAL online {agents_str}"
                        frontend.send_string(msg)
                        # print(f"Broadcast: {msg}")
                    last_broadcast_time = current_time
                
                last_check_time = current_time

    except KeyboardInterrupt:
        print("\nInterrupted")
    finally:
        frontend.close()
        backend.close()
        context.term()

if __name__ == "__main__":
    main()
