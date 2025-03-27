# Distributed-Systems-Cluster-Simulation
A lightweight, simulation-based distributed system that mimics core Kubernetes cluster management functionalities. 

How to run:
0. Create a virtual environment(optional)
1. `pip install flask docker` 
2. Start docker
3. `python3 server.py`

List nodes:
`curl http://127.0.0.1:5000/nodes
`
Add a node:
`curl -X POST http://127.0.0.1:5000/nodes/add -H "Content-Type: application/json" -d '{"cpu_cores": 2}'`

