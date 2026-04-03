"""Score collector — runs on cloud server, subscribes to game events, serves Web UI.

This is the OPTIONAL task for Experiment 5:
- Subscribes to MQTT topics to collect game state & scores from all agents.
- Provides a simple HTTP web page showing live game status.
- Designed to run as a Pod on the cloud server node (via K8s Service).

Usage (standalone):
  python3 score_collector.py --broker 10.0.0.1 --web-port 8080

Usage (Docker):
  docker run --rm -p 8080:8080 -e BROKER_IP=10.0.0.1 exp5-collector:latest
"""

import argparse
import json
import os
import sys
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("ERROR: paho-mqtt not installed. pip install paho-mqtt")
    sys.exit(1)


# --------------------------
# Global game state
# --------------------------
game_state = {
    "agents": {},       # agent_id -> {"score": int, "last_event": str, "last_seen": float}
    "heartbeats": {},   # agent_id -> last_heartbeat_time
    "total_rounds": 0,
    "start_time": time.time(),
}
state_lock = threading.Lock()


def update_agent_event(agent_id, score, event_text):
    with state_lock:
        game_state["agents"][agent_id] = {
            "score": score,
            "last_event": event_text,
            "last_seen": time.time(),
        }
        game_state["total_rounds"] += 1


def update_heartbeat(agent_id):
    with state_lock:
        game_state["heartbeats"][agent_id] = time.time()


# --------------------------
# MQTT subscriber
# --------------------------
def on_connect(client, userdata, flags, rc):
    print(f"[Collector] Connected to broker (rc={rc})")
    # Subscribe to all activate and heartbeat topics
    client.subscribe("mole/activate/#", qos=1)
    client.subscribe("mole/heartbeat/#", qos=1)


def on_message(client, userdata, msg):
    topic = msg.topic
    try:
        payload = msg.payload.decode("utf-8")
    except Exception:
        return

    # Parse activate messages: mole/activate/<id>
    if topic.startswith("mole/activate/"):
        try:
            agent_id = topic.split("/")[-1]
            data = json.loads(payload)
            score = int(data.get("score", 0))
            mole_type = int(data.get("mole_type", 1))
            event = f"地鼠类型={'真' if mole_type == 1 else '假'}, 分数={score}"
            update_agent_event(agent_id, score, event)
        except Exception as e:
            print(f"[Collector] Parse error: {e}")

    # Parse heartbeat: mole/heartbeat/<id>
    elif topic.startswith("mole/heartbeat/"):
        agent_id = topic.split("/")[-1]
        update_heartbeat(agent_id)


# --------------------------
# Web server
# --------------------------
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta http-equiv="refresh" content="3">
<title>打地鼠游戏状态</title>
<style>
  body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 40px; background: #f0f2f5; }}
  h1 {{ color: #333; border-bottom: 2px solid #4CAF50; padding-bottom: 10px; }}
  .stats {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #ddd; padding: 12px; text-align: center; }}
  th {{ background: #4CAF50; color: white; }}
  tr:nth-child(even) {{ background: #f9f9f9; }}
  .online {{ color: #4CAF50; font-weight: bold; }}
  .offline {{ color: #f44336; font-weight: bold; }}
  .footer {{ color: #888; margin-top: 20px; font-size: 0.9em; }}
</style>
</head>
<body>
<h1>🎮 打地鼠游戏实时状态</h1>
<div class="stats">
  <p>⏱ 运行时间: {uptime}</p>
  <p>🔄 总回合数: {total_rounds}</p>
  <p>📡 在线节点: {online_count} / {total_count}</p>
</div>
<h2>节点状态</h2>
<table>
  <tr><th>Agent ID</th><th>节点名称</th><th>当前分数</th><th>最近事件</th><th>状态</th><th>最后活跃</th></tr>
  {rows}
</table>
<p class="footer">页面每 3 秒自动刷新 | 实验五 · Docker & Kubernetes</p>
</body>
</html>"""


class GameHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(self._build_page().encode("utf-8"))
        elif self.path == "/api/state":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            with state_lock:
                self.wfile.write(json.dumps(game_state, default=str, ensure_ascii=False).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def _build_page(self):
        now = time.time()
        with state_lock:
            uptime_sec = int(now - game_state["start_time"])
            hours, rem = divmod(uptime_sec, 3600)
            mins, secs = divmod(rem, 60)
            uptime = f"{hours:02d}:{mins:02d}:{secs:02d}"

            rows = []
            all_ids = set(list(game_state["agents"].keys()) + list(game_state["heartbeats"].keys()))
            online_count = 0
            for aid in sorted(all_ids):
                info = game_state["agents"].get(aid, {})
                hb_time = game_state["heartbeats"].get(aid, 0)
                last_seen = max(info.get("last_seen", 0), hb_time)
                is_online = (now - last_seen) < 10  # 10s timeout
                if is_online:
                    online_count += 1

                score = info.get("score", "-")
                event = info.get("last_event", "-")
                status_class = "online" if is_online else "offline"
                status_text = "🟢 在线" if is_online else "🔴 离线"
                ago = f"{int(now - last_seen)}秒前" if last_seen > 0 else "-"

                rows.append(
                    f"<tr><td>{aid}</td><td>pi{aid}</td><td>{score}</td>"
                    f"<td>{event}</td>"
                    f'<td class="{status_class}">{status_text}</td>'
                    f"<td>{ago}</td></tr>"
                )

        return HTML_TEMPLATE.format(
            uptime=uptime,
            total_rounds=game_state["total_rounds"],
            online_count=online_count,
            total_count=len(all_ids),
            rows="\n  ".join(rows) if rows else "<tr><td colspan='6'>暂无数据</td></tr>",
        )

    def log_message(self, format, *args):
        # Suppress default logging
        pass


def run_web_server(port):
    server = HTTPServer(("0.0.0.0", port), GameHandler)
    print(f"[Collector] Web server listening on http://0.0.0.0:{port}")
    server.serve_forever()


# --------------------------
# Main
# --------------------------
def parse_args():
    p = argparse.ArgumentParser(description="Game score collector + Web UI (exp5 optional)")
    p.add_argument("--broker", default=os.getenv("BROKER_IP", "10.0.0.1"))
    p.add_argument("--tcp-port", type=int, default=1883)
    p.add_argument("--web-port", type=int, default=8080)
    return p.parse_args()


def main():
    args = parse_args()

    # Start MQTT subscriber
    client = mqtt.Client(client_id="score-collector")
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(args.broker, args.tcp_port, keepalive=30)
    client.loop_start()

    # Start Web server in main thread
    print(f"[Collector] Subscribing to broker {args.broker}:{args.tcp_port}")
    run_web_server(args.web_port)


if __name__ == "__main__":
    main()
