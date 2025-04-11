#!/usr/bin/env python3
import time
import requests
import os
import socket
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("heartbeat")

# Get container hostname (will be the container ID)
node_id = socket.gethostname()
if len(node_id) > 12:
    node_id = node_id[:12]

logger.info(f"Starting heartbeat for node: {node_id}")

# API server options in order of preference
API_SERVERS = [
    os.environ.get('API_SERVER', 'http://api-server:5000'),
    'http://api-server:5000',
    'http://host.docker.internal:5000'
]

def send_heartbeat(server_url):
    """Send a heartbeat to a specific server URL"""
    try:
        response = requests.post(
            f"{server_url}/heartbeat",
            json={"node_id": node_id},
            timeout=3
        )
        return True
    except Exception as e:
        logger.debug(f"Failed to send heartbeat to {server_url}: {e}")
        return False

if __name__ == "__main__":
    working_server = None
    
    while True:
        # If we have a working server, try it first
        if working_server:
            success = send_heartbeat(working_server)
            if not success:
                working_server = None
        
        # If no working server, try all options
        if not working_server:
            for server in API_SERVERS:
                if send_heartbeat(server):
                    working_server = server
                    logger.info(f"Connected to API server: {working_server}")
                    break
        
        time.sleep(5)  # Send heartbeat every 5 seconds