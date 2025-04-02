from flask import Flask, jsonify, request, render_template
import docker
import os

app = Flask(__name__)
os.environ["DOCKER_HOST"] = "unix:///Users/lapac/.docker/run/docker.sock"  # Ensure Docker is accessible via TCP
client = docker.from_env()

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

    container = client.containers.run(
        "ubuntu",
        command="sleep infinity",
        detach=True
    )

    node_id = container.short_id
    nodes[node_id] = {"cpu_cores": cpu_cores, "status": "healthy"}

    return jsonify({"message": "Node added", "node_id": node_id, "cpu_cores": cpu_cores})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
