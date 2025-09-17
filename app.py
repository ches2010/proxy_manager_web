import os
import json
import requests
import subprocess
import threading
from flask import Flask, render_template, jsonify, request

# --- 配置 ---
CONFIG_FILE = 'config.json'
OUTPUT_DIR = os.getcwd()
HTTP_FILE = os.path.join(OUTPUT_DIR, "http.txt")
SOCKS5_FILE = os.path.join(OUTPUT_DIR, "socks5.txt") # 更改文件名

# --- 代理源定义 (整合 hq.py 和 xdl.py 的源) ---
SOURCES = [
    # hq.py sources
    {"name": "TheSpeedX/PROXY-List (SOCKS5)", "url": "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt", "parser": "text", "protocol": "socks5"},
    {"name": "hookzof/socks5_list", "url": "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt", "parser": "text", "protocol": "socks5"},
    {"name": "ProxyScraper/ProxyScraper (SOCKS5)", "url": "https://raw.githubusercontent.com/ProxyScraper/ProxyScraper/main/socks5.txt", "parser": "text", "protocol": "socks5"},
    {"name": "proxifly/free-proxy-list (HTTP)", "url": "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/http/data.txt", "parser": "text", "protocol": "http"},
    {"name": "zloi-user/hideip.me (SOCKS5)", "url": "https://raw.githubusercontent.com/zloi-user/hideip.me/master/socks5.txt", "parser": "text", "protocol": "socks5"},
    {"name": "gfpcom/free-proxy-list (SOCKS5)", "url": "https://raw.githubusercontent.com/gfpcom/free-proxy-list/main/list/socks5.txt", "parser": "text", "protocol": "socks5"},
    {"name": "monosans/proxy-list (JSON)", "url": "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies.json", "parser": "json-list", "protocol": "socks5"},
    {"name": "fate0/proxylist (JSON)", "url": "https://raw.githubusercontent.com/fate0/proxylist/master/proxy.list", "parser": "json", "protocol": "dynamic"}, # Protocol in JSON
    
    # xdl.py sources (去重)
    # {"name": "TheSpeedX/PROXY-List", ...} # 已包含在上
    # {"name": "hookzof/socks5_list", ...}  # 已包含在上
    # {"name": "fate0/proxylist", ...}      # 已包含在上
    # {"name": "ProxyScraper/ProxyScraper (SOCKS5)", ...} # 已包含在上
]

# --- 辅助函数 (来自 hq.py) ---
def clean_proxy_line(line):
    line = line.strip()
    if "//" in line:
        line = line.split('//')[-1]
    if "@" in line:
        line = line.split('@')[-1]
    parts = line.split(':')
    if len(parts) > 2:
        line = f"{parts[0]}:{parts[1]}"
    if ':' in line and line.split(':')[0] and line.split(':')[1]:
        return line.strip()
    return None

def deduce_protocol(original_line, default_protocol):
    line_lower = original_line.lower()
    if 'socks5' in line_lower or 'socks' in line_lower:
        return 'socks5'
    if 'socks4' in line_lower:
        return 'socks4'
    if 'http' in line_lower:
        return 'http'
    return default_protocol

# --- 保存文件函数 (来自 hq.py/xdl.py) ---
def save_proxies_to_file(proxies_set, filename):
    if not proxies_set:
        print(f"\n[-] 代理列表 '{filename}' 为空，无需保存。")
        return False

    file_path = filename # Use full path
    try:
        sorted_proxies = sorted(list(proxies_set))
        with open(file_path, 'w', encoding='utf-8') as f:
            for proxy in sorted_proxies:
                f.write(f"{proxy}\n")
        print(f"\n[SUCCESS] {len(sorted_proxies)} 个代理已成功保存到: {file_path}")
        return True
    except Exception as e:
        print(f"\n[ERROR] 保存文件 '{filename}' 时出错: {e}")
        return False

# --- 核心获取函数 (整合 hq.py 和 xdl.py 的逻辑) ---
def fetch_proxies_task():
    """后台任务：获取并保存代理"""
    print("[*] 开始获取代理...")
    http_proxies = set()
    socks5_proxies = set()

    for source in SOURCES:
        print(f"[*] 正在从 {source['name']} 获取代理列表...")
        try:
            response = requests.get(source['url'], timeout=15)
            response.raise_for_status()

            initial_http_count = len(http_proxies)
            initial_socks5_count = len(socks5_proxies)

            content = response.text.strip()
            lines = content.split('\n')

            for line in lines:
                if not line.strip():
                    continue

                protocol = source['protocol']
                cleaned_proxy = None

                if source['parser'] == 'text':
                    # 使用 hq.py 的清理和协议推断逻辑
                    protocol = deduce_protocol(line, source['protocol'])
                    cleaned_proxy = clean_proxy_line(line)
                elif source['parser'] == 'json-list':
                     # monosans/proxy-list
                     try:
                         proxy_data = json.loads(line)
                         host = proxy_data.get('ip') or proxy_data.get('host') # Check both keys
                         port = proxy_data.get('port')
                         if host and port:
                             cleaned_proxy = f"{host}:{port}"
                             # Assume protocol from source for json-list if not explicitly in data
                             protocol = source.get('protocol', 'socks5') 
                     except json.JSONDecodeError:
                         continue
                elif source['parser'] == 'json':
                    # fate0/proxylist
                    try:
                        proxy_info = json.loads(line)
                        host = proxy_info.get("host")
                        port = proxy_info.get("port")
                        # Get protocol from JSON, default to source's if missing
                        proxy_type = proxy_info.get("type", source['protocol']).lower() 
                        if host and port:
                            cleaned_proxy = f"{host}:{port}"
                            protocol = proxy_type # Use protocol from JSON
                    except json.JSONDecodeError:
                        continue

                if not cleaned_proxy:
                    continue

                if 'http' in protocol: # Handles http and https
                    http_proxies.add(f"http://{cleaned_proxy}")
                elif 'socks5' in protocol:
                    socks5_proxies.add(f"socks5://{cleaned_proxy}")
                # 可以添加对 socks4 的处理

            new_http = len(http_proxies) - initial_http_count
            new_socks5 = len(socks5_proxies) - initial_socks5_count
            print(f"[+] 从此来源添加了 {new_http} 个HTTP代理, {new_socks5} 个SOCKS5代理。")

        except requests.exceptions.RequestException as e:
            print(f"[!] 从 {source['name']} 获取代理时出错: {e}")

        print("-" * 20)
    
    # 保存文件
    http_success = save_proxies_to_file(http_proxies, HTTP_FILE)
    socks5_success = save_proxies_to_file(socks5_proxies, SOCKS5_FILE)
    
    if http_success or socks5_success:
        print("[SUCCESS] 代理获取和保存完成。")
        return True
    else:
        print("[FAILURE] 代理获取或保存失败。")
        return False

# --- Flask App ---
app = Flask(__name__)

# 全局变量存储任务状态
fetch_status = {"running": False, "message": "空闲"}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/fetch', methods=['POST'])
def api_fetch_proxies():
    global fetch_status
    if fetch_status["running"]:
        return jsonify({"status": "error", "message": "任务已在运行"}), 400
    
    fetch_status["running"] = True
    fetch_status["message"] = "正在获取代理..."
    
    def run_fetch():
        global fetch_status
        try:
            success = fetch_proxies_task()
            fetch_status["message"] = "获取完成" if success else "获取失败"
        except Exception as e:
            fetch_status["message"] = f"获取出错: {str(e)}"
        finally:
            fetch_status["running"] = False
            
    thread = threading.Thread(target=run_fetch)
    thread.start()
    
    return jsonify({"status": "started", "message": "已启动获取任务"}), 202

@app.route('/api/status')
def api_get_status():
    global fetch_status
    return jsonify(fetch_status)

@app.route('/api/config', methods=['GET', 'POST'])
def api_config():
    if request.method == 'GET':
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
            return jsonify(config)
        except FileNotFoundError:
            return jsonify({"error": "配置文件未找到"}), 404
        except json.JSONDecodeError:
            return jsonify({"error": "配置文件格式错误"}), 500

    elif request.method == 'POST':
        try:
            new_config = request.get_json()
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(new_config, f, indent=4, ensure_ascii=False)
            return jsonify({"status": "success", "message": "配置已更新"})
        except Exception as e:
             return jsonify({"status": "error", "message": f"更新配置失败: {str(e)}"}), 500

@app.route('/api/proxies')
def api_get_proxies():
    protocol = request.args.get('type', 'socks5') # 默认获取 socks5
    filename = SOCKS5_FILE if protocol == 'socks5' else HTTP_FILE
    
    try:
        if not os.path.exists(filename):
            return jsonify({"proxies": [], "message": f"文件 {filename} 不存在"}), 404
            
        with open(filename, 'r', encoding='utf-8') as f:
            proxies = [line.strip() for line in f if line.strip()]
        return jsonify({"proxies": proxies, "count": len(proxies), "file": filename})
    except Exception as e:
        return jsonify({"proxies": [], "error": str(e)}), 500


if __name__ == '__main__':
    # 注意：实际部署时，应使用 WSGI 服务器如 Gunicorn
    # 这里为了简化，直接用 Flask 内置服务器，并允许外部访问
    app.run(host='0.0.0.0', port=5000, debug=False) 



