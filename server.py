from flask import Flask, jsonify, request, render_template
import docker
import threading
import time
import socket
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
client = docker.from_env()

# Data structures
nodes = {}  # Stores node information
pods = {}   # Stores pod information
node_last_heartbeat = {}  # Tracks last heartbeat time for each node

# Constants
HEARTBEAT_TIMEOUT = 15  # Seconds before a node is considered unhealthy

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/nodes', methods=['GET'])
def list_nodes():
    return jsonify(nodes)

@app.route('/pods', methods=['GET'])
def list_pods():
    return jsonify(pods)

@app.route('/nodes/add', methods=['POST'])
def add_node():
    try:
        data = request.json
        cpu_cores = data.get('cpu_cores', 1)
        
        # Find the network to use
        networks = client.networks.list(names=["cluster-network"])
        network_name = networks[0].name if networks else "bridge"
        
        # Create the container
        container = client.containers.run(
            "node-heartbeat:latest",
            detach=True,
            environment={
                "API_SERVER": "http://api-server:5000"
            },
            network=network_name
        )
        
        node_id = container.short_id
        nodes[node_id] = {
            "cpu_cores": cpu_cores, 
            "status": "healthy", 
            "available_cores": cpu_cores,
            "pods": []
        }
        
        # Initialize the heartbeat time
        node_last_heartbeat[node_id] = datetime.now()
        
        return jsonify({
            "message": "Node added", 
            "node_id": node_id, 
            "cpu_cores": cpu_cores
        })
        
    except Exception as e:
        logger.error(f"Error adding node: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/heartbeat', methods=['POST'])
def heartbeat():
    data = request.json
    node_id = data.get('node_id')
    
    if node_id in nodes:
        node_last_heartbeat[node_id] = datetime.now()
        nodes[node_id]["status"] = "healthy"
        return jsonify({"status": "ok"})
    
    return jsonify({"status": "error", "message": "Node not found"}), 404

@app.route('/pods/add', methods=['POST'])
def add_pod():
    try:
        data = request.json
        cpu_request = data.get('cpu_request', 1)
        
        # Generate a pod ID
        pod_id = f"pod-{len(pods) + 1}"
        
        # Schedule the pod
        assigned_node = schedule_pod(cpu_request)
        
        if assigned_node:
            # Update node resources
            nodes[assigned_node]["available_cores"] -= cpu_request
            nodes[assigned_node]["pods"].append(pod_id)
            
            # Save pod information
            pods[pod_id] = {
                "cpu_request": cpu_request,
                "node_id": assigned_node,
                "status": "running"
            }
            
            return jsonify({
                "message": "Pod created and scheduled", 
                "pod_id": pod_id,
                "node_id": assigned_node
            })
        
        return jsonify({
            "message": "Failed to schedule pod. Not enough resources available."
        }), 400
    except Exception as e:
        logger.error(f"Error adding pod: {str(e)}")
        return jsonify({"error": str(e)}), 500

def schedule_pod(cpu_request):
    """Simple scheduling algorithm that assigns pods to nodes with enough CPU."""
    for node_id, info in nodes.items():
        if info["status"] == "healthy" and info["available_cores"] >= cpu_request:
            return node_id
    return None

def health_check_worker():
    """Background worker that checks node health."""
    logger.info("Health check worker started")
    while True:
        try:
            current_time = datetime.now()
            for node_id in list(nodes.keys()):
                if node_id in node_last_heartbeat:
                    last_heartbeat = node_last_heartbeat[node_id]
                    time_since_last_heartbeat = (current_time - last_heartbeat).total_seconds()
                    
                    if time_since_last_heartbeat > HEARTBEAT_TIMEOUT:
                        logger.info(f"Node {node_id} is unhealthy. Last heartbeat: {last_heartbeat}")
                        nodes[node_id]["status"] = "unhealthy"
                        
                        # Handle pods on unhealthy nodes
                        for pod_id in nodes[node_id]["pods"]:
                            if pod_id in pods:
                                pods[pod_id]["status"] = "pending"
        except Exception as e:
            logger.error(f"Error in health check worker: {str(e)}")
            
        time.sleep(5)  # Check every 5 seconds

if __name__ == '__main__':
    # Start health check worker in a background thread
    health_thread = threading.Thread(target=health_check_worker, daemon=True)
    health_thread.start()
    
    app.run(debug=True, port=5000, host='0.0.0.0', threaded=True)