from flask import Flask, jsonify, request, render_template
import docker
import os
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
os.environ["DOCKER_HOST"] = "unix:///Users/lapac/.docker/run/docker.sock"  # Ensure Docker is accessible via TCP
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
    # Log all available nodes for debugging
    logger.info(f"Scheduling pod requiring {cpu_request} cores...")
    for node_id, info in nodes.items():
        logger.info(f"Checking node {node_id}: status={info['status']}, available_cores={info['available_cores']}")
        if info["status"] == "healthy" and info["available_cores"] >= cpu_request:
            logger.info(f"Selected node {node_id} for scheduling")
            return node_id
    logger.info("No suitable node found for scheduling")
    return None

def find_node_for_pod(cpu_request):
    """Find a healthy node with enough CPU for the given request."""
    suitable_nodes = []
    
    for node_id, info in nodes.items():
        if info["status"] == "healthy" and info["available_cores"] >= cpu_request:
            suitable_nodes.append(node_id)
    
    if suitable_nodes:
        # For simplicity, just return the first suitable node
        return suitable_nodes[0]
    
    return None

def reschedule_pending_pods():
    """Attempt to reschedule pods that are in pending state."""
    pending_pods = {pod_id: info for pod_id, info in pods.items() if info["status"] == "pending"}
    
    if pending_pods:
        logger.info(f"Attempting to reschedule {len(pending_pods)} pending pods")
        
    for pod_id, pod_info in pending_pods.items():
        cpu_request = pod_info["cpu_request"]
        old_node_id = pod_info["node_id"]
        
        logger.info(f"Trying to reschedule pod {pod_id} with CPU request {cpu_request}")
        
        # Find a new healthy node with direct function call
        new_node_id = find_node_for_pod(cpu_request)
        
        if new_node_id:
            logger.info(f"→ SUCCESS: Rescheduling pod {pod_id} from node {old_node_id} to node {new_node_id}")
            
            # Update pod status and node assignment
            pods[pod_id]["status"] = "running"
            pods[pod_id]["node_id"] = new_node_id
            
            # Remove from old node's pod list if the node still exists
            if old_node_id in nodes:
                if pod_id in nodes[old_node_id]["pods"]:
                    nodes[old_node_id]["pods"].remove(pod_id)
                    logger.info(f"Removed pod {pod_id} from old node {old_node_id}")
            
            # Add to new node's pod list and update resources
            nodes[new_node_id]["pods"].append(pod_id)
            nodes[new_node_id]["available_cores"] -= cpu_request
            
            logger.info(f"Node {new_node_id} now has {nodes[new_node_id]['available_cores']} cores available")
        else:
            logger.warning(f"× FAILED: Could not find suitable node for pending pod {pod_id}")

def health_check_worker():
    """Background worker that checks node health and reschedules pods from failed nodes."""
    logger.info("Health check worker started")
    # Try to reschedule pods every cycle regardless of new failures
    while True:
        try:
            current_time = datetime.now()
            
            # Check node health
            for node_id in list(nodes.keys()):
                if node_id in node_last_heartbeat:
                    last_heartbeat = node_last_heartbeat[node_id]
                    time_since_last_heartbeat = (current_time - last_heartbeat).total_seconds()
                    
                    # Mark unhealthy nodes
                    if time_since_last_heartbeat > HEARTBEAT_TIMEOUT:
                        # Only log if status is changing
                        if nodes[node_id]["status"] == "healthy":
                            logger.info(f"Node {node_id} is now UNHEALTHY. Last heartbeat was {time_since_last_heartbeat:.1f} seconds ago")
                            
                            # Mark all pods on this node as pending
                            for pod_id in nodes[node_id]["pods"]:
                                if pod_id in pods and pods[pod_id]["status"] == "running":
                                    pods[pod_id]["status"] = "pending"
                                    logger.info(f"Marked pod {pod_id} as pending due to unhealthy node")
                        
                        # Update node status
                        nodes[node_id]["status"] = "unhealthy"
            
            # Always try to reschedule pending pods in every cycle
            reschedule_pending_pods()
                
        except Exception as e:
            logger.error(f"Error in health check worker: {str(e)}")
            
        time.sleep(5)  # Check every 5 seconds

@app.route('/debug/reschedule', methods=['GET'])
def trigger_reschedule():
    """Debug endpoint to manually trigger pod rescheduling."""
    reschedule_pending_pods()
    return jsonify({"message": "Manual rescheduling triggered"})

if __name__ == '__main__':
    # Start health check worker in a background thread
    health_thread = threading.Thread(target=health_check_worker, daemon=True)
    health_thread.start()
    
    app.run(debug=True, port=5000, host='0.0.0.0', threaded=True)