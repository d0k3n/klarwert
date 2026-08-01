import sys
import os
import time
import threading
import socket
import urllib.request

import webview
from app import app, resource_path


def find_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def run_server(port):
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


def wait_for_server(url, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.1)
    return False


def main():
    port = find_free_port()
    server_thread = threading.Thread(target=run_server, args=(port,), daemon=True)
    server_thread.start()

    url = f"http://127.0.0.1:{port}/"
    if not wait_for_server(f"{url}api/status"):
        print("ERROR: backend failed to start", file=sys.stderr)
        sys.exit(1)

    webview.create_window(
        "Trade Republic Portfolio Analyzer",
        url,
        width=1280,
        height=900,
    )
    webview.start()


if __name__ == "__main__":
    main()
