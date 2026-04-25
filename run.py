# -*- coding: utf-8 -*-
import socket
import uvicorn
import os

# Ensure UTF-8 output on Windows (fixes Hindi character display in console)
os.environ.setdefault("PYTHONUTF8", "1")

def get_free_port(start_port=8000, max_port=8099):
    for port in range(start_port, max_port + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('0.0.0.0', port)) != 0:
                return port
    raise RuntimeError("No available ports found in range")

if __name__ == "__main__":
    host = os.environ.get("APP_HOST", "0.0.0.0")

    if os.environ.get("APP_PORT"):
        port = int(os.environ.get("APP_PORT"))
    elif os.environ.get("UVICORN_PORT"):
        port = int(os.environ.get("UVICORN_PORT"))
    elif os.environ.get("PORT"):  # Render / Railway / Heroku
        port = int(os.environ.get("PORT"))
    else:
        port = get_free_port()

    os.environ["UVICORN_PORT"] = str(port)
    print(f"Starting Bhakti Marg AI server on {host}:{port}...")
    uvicorn.run("app.main:app", host=host, port=port, reload=True)

