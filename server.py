from flask import Flask, jsonify, request
import docker

app = Flask(__name__)
client = docker.from_env()

# Store nodes
nodes = {}

@app.route('/nodes', methods=['GET'])
def list_nodes():
    return jsonify(nodes)

@app.route('/nodes/add', methods=['POST'])
def add_node():
    data = request.json
    cpu_cores = data.get('cpu_cores', 1)

    # Launch a new Docker container to simulate a node
    container = client.containers.run(
        "ubuntu",  # Use a lightweight OS image
        command="sleep infinity",  # Keep the container running
        detach=True
    )

    node_id = container.short_id
    nodes[node_id] = {"cpu_cores": cpu_cores, "status": "healthy"}

    return jsonify({"message": "Node added", "node_id": node_id})


if __name__ == '__main__':
    app.run(debug=True, port=5000)

