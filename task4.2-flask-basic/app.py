"""SWE40006 Task 4.2 - basic containerised Flask application.

Returns JSON describing the container that served the request, so the same
image can be shown running on two different Docker hosts.
"""
import os
import platform
import socket
from datetime import datetime, timezone

from flask import Flask, jsonify

app = Flask(__name__)
STARTED = datetime.now(timezone.utc).isoformat(timespec="seconds")


@app.get("/")
def index():
    return jsonify(
        message="Hello from SWE40006 Task 4.2 - containerised Flask app",
        docker_host=os.environ.get("DEPLOY_HOST", "unspecified"),
        container_hostname=socket.gethostname(),  # the container ID inside Docker
        python_version=platform.python_version(),
        started_utc=STARTED,
    )


@app.get("/health")
def health():
    return jsonify(status="ok"), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    # 0.0.0.0 is required inside a container; 127.0.0.1 would only accept
    # connections from inside the container itself.
    app.run(host="0.0.0.0", port=port)
