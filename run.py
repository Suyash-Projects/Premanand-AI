import socket
import uvicorn
import os

def get_free_port(start_port=8000, max_port=8099):
    for port in range(start_port, max_port + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('0.0.0.0', port)) != 0:
                return port
    raise RuntimeError("No available ports found in range")

if __name__ == "__main__":
    if os.environ.get("UVICORN_PORT"):
        port = int(os.environ.get("UVICORN_PORT"))
    else:
        port = get_free_port()
        os.environ["UVICORN_PORT"] = str(port)
        
    print(f"Starting server on port {port}...")
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
