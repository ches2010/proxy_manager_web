# launch.py
import subprocess
import threading
import time
import socket
import sys
import os
import queue
import shutil

# --- Configuration ---
FLASK_HOST = "127.0.0.1"
FLASK_PORT = 5000
FLASK_APP_MODULE = "app.app"

def wait_for_port(host, port, timeout=60):
    """等待指定的端口开放"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex((host, port))
        sock.close()
        if result == 0:
            return True
        time.sleep(0.5)
    return False

def read_stderr(pipe, q):
    """在独立线程中读取 stderr，避免阻塞"""
    try:
        for line in iter(pipe.readline, ''):
            q.put(line)
    except Exception:
        pass
    finally:
        pipe.close()

def cloudflared_thread(host, port):
    """在后台线程中启动 cloudflared"""
    print(f"[LAUNCH] Waiting for Flask app to start on {host}:{port}...")
    if not wait_for_port(host, port, timeout=60):
        print("[ERROR] Flask app did not start within the timeout period.", file=sys.stderr)
        return

    print(f"[LAUNCH] Flask app is running. Starting cloudflared tunnel...")
    print("[LAUNCH] If it gets stuck here, cloudflared might be having issues or taking time to connect.")

    cloudflared_path = shutil.which("cloudflared")
    if not cloudflared_path:
        print("[ERROR] 'cloudflared' command not found. Please install it from https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/", file=sys.stderr)
        return

    try:
        process = subprocess.Popen(
            [cloudflared_path, "tunnel", "--url", f"http://{host}:{port}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )

        q = queue.Queue()
        t = threading.Thread(target=read_stderr, args=(process.stderr, q), daemon=True)
        t.start()

        printed_url = False
        while True:
            try:
                line = q.get(timeout=1)
                if ".trycloudflare.com " in line and not printed_url:
                    url_start = line.find("http")
                    if url_start != -1:
                        url = line[url_start:].split()[0]
                        print(f"\n[SUCCESS] Public URL: {url}\n")
                        printed_url = True
            except queue.Empty:
                if process.poll() is not None:
                    break
                continue

    except Exception as e:
        print(f"[ERROR] Failed to start cloudflared: {e}", file=sys.stderr)

def main():
    """主函数：启动 Flask 应用和 cloudflared"""
    print("[LAUNCH] Starting Proxy Manager...")

    tunnel_thread = threading.Thread(target=cloudflared_thread, args=(FLASK_HOST, FLASK_PORT), daemon=True)
    tunnel_thread.start()

    flask_env = os.environ.copy()
    flask_env["FLASK_APP"] = FLASK_APP_MODULE

    try:
        print(f"[LAUNCH] Launching Flask app: {FLASK_APP_MODULE} on {FLASK_HOST}:{FLASK_PORT}")
        flask_process = subprocess.run(
            [sys.executable, "-m", "flask", "run", "--host", FLASK_HOST, "--port", str(FLASK_PORT), "--no-reload"],
            env=flask_env
        )
        print("[LAUNCH] Flask app process finished.")
    except KeyboardInterrupt:
        print("\n[LAUNCH] Received interrupt signal. Shutting down...")
    except Exception as e:
        print(f"[ERROR] Failed to launch Flask app: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
