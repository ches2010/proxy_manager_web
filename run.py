import subprocess
import sys
import os
import time
import signal
import requests

# --- 配置 ---
FLASK_APP_MODULE = "app.app:app" # Flask 应用模块和实例
FLASK_HOST = "127.0.0.1" # 仅本地访问，Tunnel负责外部
FLASK_PORT = 5000
CLOUDFLARED_CONFIG_PATH = None # 如果使用配置文件，指定路径
CLOUDFLARED_TOKEN = None # 如果使用令牌，指定令牌

# --- 全局进程变量 ---
flask_process = None
cloudflared_process = None

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
    
    # 简单等待 Flask 启动
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
    global cloudflared_process
    print("正在启动 Cloudflared Tunnel...")
    
    cmd = ["cloudflared", "tunnel", "--no-autoupdate"]
    
    if CLOUDFLARED_TOKEN:
        cmd.extend(["run", "--token", CLOUDFLARED_TOKEN])
    elif CLOUDFLARED_CONFIG_PATH:
        cmd.extend(["--config", CLOUDFLARED_CONFIG_PATH, "run"])
    else:
        print("警告: 未配置 CLOUDFLARED_TOKEN 或 CLOUDFLARED_CONFIG_PATH。请手动启动 cloudflared 或在 run.py 中配置。")
        print("假设你已通过其他方式 (如 Cloudflare Dashboard) 启动了 tunnel 并指向 localhost:5000。")
        return True # 不启动，但不视为错误

    try:
        cloudflared_process = subprocess.Popen(cmd)
        print("Cloudflared Tunnel 启动命令已执行。请查看其输出以获取公网 URL。")
        return True
    except FileNotFoundError:
        print("错误: 未找到 'cloudflared' 命令。请确保它已安装并添加到系统 PATH。")
        return False
    except Exception as e:
        print(f"启动 Cloudflared Tunnel 时出错: {e}")
        return False

def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("=== Proxy Manager 启动器 ===")

    flask_ok = start_flask()
    if not flask_ok:
        print("Flask 应用启动失败，退出。")
        sys.exit(1)

    tunnel_ok = start_cloudflared()
    if not tunnel_ok:
        print("Cloudflared Tunnel 启动失败。Flask 应用仍在运行在本地。")
        # 不退出，允许本地访问

    print("\n--- 应用已启动 ---")
    print(f"本地访问地址: http://{FLASK_HOST}:{FLASK_PORT}")
    print("请查看 Cloudflared 的输出以获取公网访问地址 (如果已启动)。")
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



