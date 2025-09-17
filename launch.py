# launch.py
import subprocess
import threading
import time
import socket
import sys
import os

# --- Configuration ---
FLASK_HOST = "127.0.0.1"
FLASK_PORT = 5000
FLASK_APP_MODULE = "app.app:app"

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

def cloudflared_thread(host, port):
    """在后台线程中启动 cloudflared"""
    # 等待 Flask 应用启动
    print(f"[LAUNCH] Waiting for Flask app to start on {host}:{port}...")
    if not wait_for_port(host, port, timeout=60):
        print("[ERROR] Flask app did not start within the timeout period.", file=sys.stderr)
        return

    print(f"[LAUNCH] Flask app is running. Starting cloudflared tunnel...")
    print("[LAUNCH] If it gets stuck here, cloudflared might be having issues or taking time to connect.")

    try:
        # 启动 cloudflared 进程
        process = subprocess.Popen(
            ["cloudflared", "tunnel", "--url", f"http://{host}:{port}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )

        # 实时读取 stderr 输出以获取 URL
        for line in process.stderr:
            if ".trycloudflare.com " in line:
                # 提取并打印 URL
                url_start = line.find("http")
                if url_start != -1:
                    url = line[url_start:].split()[0]
                    print(f"\n[SUCCESS] Public URL: {url}\n")
            # 可选：打印其他 cloudflared 日志
            # print(line, end='')

    except FileNotFoundError:
        print("[ERROR] 'cloudflared' command not found. Please install it from https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/", file=sys.stderr)
    except Exception as e:
        print(f"[ERROR] Failed to start cloudflared: {e}", file=sys.stderr)


def main():
    """主函数：启动 Flask 应用和 cloudflared"""
    print("[LAUNCH] Starting Proxy Manager...")

    # 1. 在后台线程启动 cloudflared
    tunnel_thread = threading.Thread(target=cloudflared_thread, args=(FLASK_HOST, FLASK_PORT), daemon=True)
    tunnel_thread.start()

    # 2. 在主线程启动 Flask 应用
    # 构建 Flask 命令
    # 确保在 app 目录下运行，以便找到模板和静态文件
    flask_env = os.environ.copy()
    flask_env["FLASK_APP"] = FLASK_APP_MODULE

    try:
        print(f"[LAUNCH] Launching Flask app: {FLASK_APP_MODULE} on {FLASK_HOST}:{FLASK_PORT}")
        flask_process = subprocess.run(
            [sys.executable, "-m", "flask", "run", "--host", FLASK_HOST, "--port", str(FLASK_PORT)],
            cwd="app", # 在 app 目录下运行
            env=flask_env
        )
        # 如果 Flask 进程结束，脚本也应结束
        print("[LAUNCH] Flask app process finished.")
    except KeyboardInterrupt:
        print("\n[LAUNCH] Received interrupt signal. Shutting down...")
    except Exception as e:
        print(f"[ERROR] Failed to launch Flask app: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()



