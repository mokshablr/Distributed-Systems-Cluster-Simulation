from flask import Flask, jsonify, request, render_template
import docker
import sys
import logging

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

@app.route('/nodes/add', methods=['POST'])
def add_node():
    data = request.json
    cpu_cores = data.get('cpu_cores', 1)

    if not docker_available:
        return jsonify({"error": "Docker is not available. Cannot create container."}), 503
    
    try:
        container = client.containers.run(
            "ubuntu",
            command="sleep infinity",
            detach=True
        )

        node_id = container.short_id
        nodes[node_id] = {"cpu_cores": cpu_cores, "status": "healthy"}

        return jsonify({"message": "Node added", "node_id": node_id, "cpu_cores": cpu_cores})
    except Exception as e:
        logger.error(f"Error creating container: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
