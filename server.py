from flask import Flask, jsonify, request, render_template
import docker
import sys
import logging
import uuid
import time
import threading

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Try to connect to Docker
try:
    client = docker.from_env()
    docker_available = True
    logger.info("Successfully connected to Docker")
except docker.errors.DockerException as e:
    docker_available = False
    logger.error(f"Docker connection error: {e}")
    print("ERROR: Could not connect to Docker daemon.")
    print("Please ensure Docker is installed and running.")
    print("On macOS/Windows, make sure Docker Desktop is started.")
    print("On Linux, check if docker service is running with 'systemctl status docker'")
    print("The application will run in limited mode without Docker functionality.")

nodes = {}
pods = {}  # New global pods store

# Start health-monitor thread
def health_monitor():
    while True:
        now = time.time()
        for nid, info in nodes.items():
            last = info.get('last_heartbeat', 0)
            if now - last > 10:  # 10s timeout
                info['status'] = 'unhealthy'
        time.sleep(5)

threading.Thread(target=health_monitor, daemon=True).start()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/nodes', methods=['GET'])
def list_nodes():
    return jsonify(nodes)

@app.route('/nodes/<node_id>', methods=['GET'])
def get_node(node_id):
    if node_id in nodes:
        return jsonify(nodes[node_id])
    return jsonify({"error": f"Node with ID {node_id} not found"}), 404

@app.route('/nodes/add', methods=['POST'])
def add_node():
    data = request.json
    cpu_cores = data.get('cpu_cores', 1)

    node_id = str(uuid.uuid4())[:12]
    nodes[node_id] = {
        "cpu_cores": cpu_cores,
        "status": docker_available and "healthy" or "simulated",
        "virtual": not docker_available,
        "pods": [],  # Track pod IDs
        "last_heartbeat": time.time()  # Init heartbeat
    }

    if not docker_available:
        # Create a virtual node when Docker isn't available
        logger.info(f"Created virtual node {node_id} (Docker unavailable)")
        return jsonify({"message": "Virtual node added", "node_id": node_id, "cpu_cores": cpu_cores})
    
    try:
        container = client.containers.run(
            "ubuntu",
            command="sleep infinity",
            detach=True
        )

        nodes[node_id].update({
            "container_id": container.id,
            "virtual": False
        })

        return jsonify({"message": "Node added", "node_id": node_id, "cpu_cores": cpu_cores})
    except Exception as e:
        logger.error(f"Error creating container: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/nodes/<node_id>/remove', methods=['DELETE'])
def remove_node(node_id):
    if node_id not in nodes:
        return jsonify({"error": f"Node with ID {node_id} not found"}), 404
    
    node = nodes[node_id]
    
    # If it's a real Docker container, try to remove it
    if docker_available and not node.get('virtual', False):
        try:
            container = client.containers.get(node.get('container_id'))
            container.remove(force=True)
            logger.info(f"Removed Docker container for node {node_id}")
        except Exception as e:
            logger.error(f"Error removing container for node {node_id}: {e}")
    
    # Remove from our nodes dictionary
    del nodes[node_id]
    
    return jsonify({"message": f"Node {node_id} removed successfully"})

@app.route('/heartbeat', methods=['POST'])
def heartbeat():
    data = request.json
    nid = data.get('node_id')
    if nid in nodes:
        nodes[nid]['last_heartbeat'] = time.time()
        nodes[nid]['status'] = 'healthy'
        return jsonify({"message": "Heartbeat received"}), 200
    return jsonify({"error": "Node not found"}), 404

@app.route('/pods', methods=['GET'])
def list_pods():
    return jsonify(pods)

@app.route('/pods', methods=['POST'])
def schedule_pod():
    data = request.json
    cpu_req = data.get('cpu', 1)
    # Find any healthy node with enough free CPU
    for nid, info in nodes.items():
        if info['status'] != 'healthy':
            continue
        used = sum(pods[pid]['cpu'] for pid in info['pods'])
        if info['cpu_cores'] - used >= cpu_req:
            pod_id = str(uuid.uuid4())[:12]
            pods[pod_id] = {
                "cpu": cpu_req,
                "node_id": nid,
                "status": "running"
            }
            info['pods'].append(pod_id)
            return jsonify({"message": "Pod scheduled", "pod_id": pod_id, "node_id": nid}), 201
    return jsonify({"error": "No nodes available for this pod"}), 503

@app.route('/pods/<pod_id>/remove', methods=['DELETE'])
def remove_pod(pod_id):
    if pod_id not in pods:
        return jsonify({"error": f"Pod {pod_id} not found"}), 404
    node_id = pods[pod_id]['node_id']
    if node_id in nodes and pod_id in nodes[node_id]['pods']:
        nodes[node_id]['pods'].remove(pod_id)
    del pods[pod_id]
    return jsonify({"message": f"Pod {pod_id} removed"}), 200

if __name__ == '__main__':
    app.run(debug=True, port=5000)
