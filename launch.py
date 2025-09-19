# launch.py
import subprocess
import threading
import time
import socket
import sys
import os
import queue
import shutil
import signal

# --- Configuration ---
FLASK_HOST = "127.0.0.1"
FLASK_PORT = 5000
FLASK_APP_MODULE = "app.app:app"  # ✅ 修正：明确指定 Flask 实例 app

# 全局变量用于保存 cloudflared 进程，以便清理
cloudflared_process = None

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
    global cloudflared_process
    print(f"[LAUNCH] Waiting for Flask app to start on {host}:{port}...")
    if not wait_for_port(host, port, timeout=60):
        print("[ERROR] Flask app did not start within the timeout period.", file=sys.stderr)
        return  # 线程退出，但主线程需感知失败

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
            text=True,  # ✅ 统一使用 text=True
            bufsize=1,
            # universal_newlines=True,  # ❌ 移除，与 text=True 冲突或冗余
        )
        cloudflared_process = process  # 保存全局引用，便于后续清理

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

def cleanup(signum=None, frame=None):
    """清理子进程"""
    global cloudflared_process
    if cloudflared_process and cloudflared_process.poll() is None:
        print("[CLEANUP] Terminating cloudflared process...")
        cloudflared_process.terminate()
        try:
            cloudflared_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            cloudflared_process.kill()
            print("[CLEANUP] Cloudflared process killed.")
    sys.exit(0 if signum is None else 1)

def main():
    """主函数：启动 Flask 应用和 cloudflared"""
    # 设置信号处理器，确保 Ctrl+C 能清理子进程
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    print("[LAUNCH] Starting Proxy Manager...")

    # 启动 cloudflared 监控线程（它会等待 Flask 启动）
    tunnel_thread = threading.Thread(target=cloudflared_thread, args=(FLASK_HOST, FLASK_PORT), daemon=True)
    tunnel_thread.start()

    # 设置 Flask 环境变量
    flask_env = os.environ.copy()
    flask_env["FLASK_APP"] = FLASK_APP_MODULE  # ✅ 使用修正后的模块:实例格式

    try:
        print(f"[LAUNCH] Launching Flask app: {FLASK_APP_MODULE} on {FLASK_HOST}:{FLASK_PORT}")
        # 使用 Popen 而非 run，以便能监控状态并支持中断
        flask_process = subprocess.Popen(
            [sys.executable, "-m", "flask", "run", "--host", FLASK_HOST, "--port", str(FLASK_PORT), "--no-reload"],
            env=flask_env
        )

        # 等待 Flask 启动（最多60秒），否则提前报错
        if not wait_for_port(FLASK_HOST, FLASK_PORT, timeout=60):
            print("[ERROR] Flask failed to start. Aborting.", file=sys.stderr)
            cleanup()  # ✅ 主动清理并退出

        # 等待 Flask 进程结束（用户 Ctrl+C 或崩溃）
        flask_process.wait()

    except KeyboardInterrupt:
        print("\n[LAUNCH] Received interrupt signal. Shutting down...")
    except Exception as e:
        print(f"[ERROR] Failed to launch Flask app: {e}", file=sys.stderr)
    finally:
        cleanup()  # ✅ 确保无论如何都尝试清理 cloudflared

if __name__ == "__main__":
    main()
