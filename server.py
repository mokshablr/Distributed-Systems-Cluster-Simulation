from flask import Flask, jsonify, request, render_template
import docker
import sys
import logging
import uuid

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

    if not docker_available:
        # Create a virtual node when Docker isn't available
        node_id = str(uuid.uuid4())[:12]  # Generate ID similar to Docker's short_id
        nodes[node_id] = {
            "cpu_cores": cpu_cores,
            "status": "simulated",
            "virtual": True
        }
        logger.info(f"Created virtual node {node_id} (Docker unavailable)")
        return jsonify({"message": "Virtual node added", "node_id": node_id, "cpu_cores": cpu_cores})
    
    try:
        container = client.containers.run(
            "ubuntu",
            command="sleep infinity",
            detach=True
        )

        node_id = container.short_id
        nodes[node_id] = {
            "cpu_cores": cpu_cores,
            "status": "healthy",
            "container_id": container.id,
            "virtual": False
        }

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

if __name__ == '__main__':
    app.run(debug=True, port=5000)
