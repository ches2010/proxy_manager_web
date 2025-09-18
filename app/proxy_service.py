# app/proxy_service.py
import subprocess
import threading

http_process = None
socks5_process = None

def start_service(http_proxy, socks5_proxy):
    global http_process, socks5_process
    # 这里可以启动 mitmproxy / privoxy / gost 等
    # 示例：使用 gost 做转发
    # gost -L=http://:8081 -F=http://target:port
    print(f"[SERVICE] Starting service with HTTP: {http_proxy}, SOCKS5: {socks5_proxy}")
    # 模拟启动
    http_process = "running"
    socks5_process = "running"
    return True, "Local service started successfully."

def stop_service():
    global http_process, socks5_process
    print("[SERVICE] Stopping local service...")
    http_process = None
    socks5_process = None
    return True, "Local service stopped."

def get_service_status():
    return {
        "http_running": http_process is not None,
        "socks5_running": socks5_process is not None
    }
