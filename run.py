import subprocess
import sys
import os
import time
import signal
import requests
import re

# --- 配置 ---
FLASK_APP_MODULE = "app.app:app"  # Flask 应用模块和实例
FLASK_HOST = "127.0.0.1"          # 本地绑定地址
FLASK_PORT = 5000                 # 本地端口
CLOUDFLARED_EXECUTABLE = "cloudflared" # cloudflared 命令名

# --- 全局进程变量 ---
flask_process = None
cloudflared_process = None
cloudflared_url = None

def signal_handler(sig, frame):
    print("\n正在关闭应用...")
    if flask_process:
        flask_process.terminate()
        try:
            flask_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            flask_process.kill()
        print("Flask 应用已关闭。")

    if cloudflared_process:
        cloudflared_process.terminate()
        try:
            cloudflared_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            cloudflared_process.kill()
        print("Cloudflared Tunnel 已关闭。")
    
    sys.exit(0)

def start_flask():
    global flask_process
    print(f"正在启动 Flask 应用: {FLASK_APP_MODULE} on {FLASK_HOST}:{FLASK_PORT}")
    # 使用 'python -m flask run' 命令
    flask_process = subprocess.Popen([
        sys.executable, "-m", "flask", "run",
        "--host", FLASK_HOST,
        "--port", str(FLASK_PORT)
    ], cwd="app", env={**os.environ, "FLASK_APP": FLASK_APP_MODULE})
    
    # 等待 Flask 启动
    time.sleep(3)
    try:
        response = requests.get(f"http://{FLASK_HOST}:{FLASK_PORT}/", timeout=5)
        if response.status_code == 200:
            print("Flask 应用启动成功。")
            return True
        else:
            print(f"Flask 应用返回状态码: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"无法连接到 Flask 应用: {e}")
    return False

def start_cloudflared():
    global cloudflared_process, cloudflared_url
    print("正在启动 Cloudflared Quick Tunnel...")

    cmd = [
        CLOUDFLARED_EXECUTABLE,
        "tunnel", "--url", f"http://{FLASK_HOST}:{FLASK_PORT}"
    ]

    try:
        # 使用 subprocess.PIPE 捕获输出，以便提取 URL
        cloudflared_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1, # 行缓冲
            universal_newlines=True
        )
        print("Cloudflared Quick Tunnel 启动中... 请稍候...")

        # 实时读取 cloudflared 的输出，寻找 URL
        url_pattern = re.compile(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com')
        start_time = time.time()
        timeout = 30 # 30秒超时

        while cloudflared_process.poll() is None and (time.time() - start_time) < timeout:
            output_line = cloudflared_process.stdout.readline()
            if output_line:
                print(output_line.strip()) # 可选：打印 cloudflared 输出到控制台
                match = url_pattern.search(output_line)
                if match:
                    cloudflared_url = match.group(0)
                    print(f"\n[SUCCESS] Cloudflared Quick Tunnel 已启动!")
                    print(f"公网访问地址: {cloudflared_url}")
                    return True
            else:
                time.sleep(0.1) # 避免忙等待

        # 超时或进程退出
        if cloudflared_process.poll() is not None:
            print("错误: Cloudflared 进程意外退出。")
        else:
            print("错误: 等待 Cloudflared URL 超时。")
        return False

    except FileNotFoundError:
        print(f"错误: 未找到 '{CLOUDFLARED_EXECUTABLE}' 命令。请确保它已安装并添加到系统 PATH。")
        print("安装指南: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/")
        return False
    except Exception as e:
        print(f"启动 Cloudflared Quick Tunnel 时出错: {e}")
        return False

def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("=== Proxy Manager 启动器 (Quick Tunnels) ===")

    flask_ok = start_flask()
    if not flask_ok:
        print("Flask 应用启动失败，退出。")
        sys.exit(1)

    tunnel_ok = start_cloudflared()
    if not tunnel_ok:
        print("Cloudflared Quick Tunnel 启动失败。Flask 应用仍在运行在本地。")
        # 不退出，允许本地访问

    print("\n--- 应用已启动 ---")
    print(f"本地访问地址: http://{FLASK_HOST}:{FLASK_PORT}")
    if cloudflared_url:
        print(f"公网访问地址: {cloudflared_url}")
    else:
        print("公网访问地址: 未获取到 (请检查 cloudflared 输出)")
    print("按 Ctrl+C 停止所有服务。")
    print("------------------\n")

    try:
        # 等待任一子进程结束
        while True:
            if flask_process and flask_process.poll() is not None:
                print("Flask 应用已意外退出。")
                break
            if cloudflared_process and cloudflared_process.poll() is not None:
                print("Cloudflared Tunnel 已意外退出。")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        pass # signal_handler 会处理

    signal_handler(None, None) # 确保清理

if __name__ == "__main__":
    main()
