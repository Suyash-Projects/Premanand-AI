# -*- coding: utf-8 -*-
import socket
import uvicorn
import os
import sys

# Ensure UTF-8 output on Windows
os.environ.setdefault("PYTHONUTF8", "1")

def get_free_port(start_port=8000, max_port=8099):
    for port in range(start_port, max_port + 1):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                if s.connect_ex(('localhost', port)) != 0:
                    return port
        except:
            return port
    raise RuntimeError("No available ports found in range")

if __name__ == "__main__":
    host = os.environ.get("APP_HOST", "0.0.0.0")

    if os.environ.get("APP_PORT"):
        port = int(os.environ.get("APP_PORT"))
    elif os.environ.get("UVICORN_PORT"):
        port = int(os.environ.get("UVICORN_PORT"))
    elif os.environ.get("PORT"):
        port = int(os.environ.get("PORT"))
    else:
        port = get_free_port()

    os.environ["UVICORN_PORT"] = str(port)
    print(f"Starting Bhakti Marg AI server on {host}:{port}...")

    try:
        uvicorn.run(
            "app.main:app",
            host=host,
            port=port,
            reload=True,
            log_level="info"
        )
    except KeyboardInterrupt:
        print("\nServer stopped.")
        sys.exit(0)