# app/app.py
import os
import json
import requests
import traceback
import logging
from collections import deque
from flask import Flask, render_template, jsonify, request, redirect
# --- 新增导入 ---
import threading
import time

# --- 配置日志 ---
class InMemoryHandler(logging.Handler):
    def __init__(self, max_logs=1000):
        super().__init__()
        self.log_buffer = deque(maxlen=max_logs)

    def emit(self, record):
        log_entry = self.format(record)
        self.log_buffer.append(log_entry)

app = Flask(__name__)

# --- 设置日志记录 ---
in_memory_handler = InMemoryHandler(max_logs=1000)
formatter = logging.Formatter('[%(asctime)s] %(levelname)s in %(module)s: %(message)s')
in_memory_handler.setFormatter(formatter)
app.logger.addHandler(in_memory_handler)
app.logger.setLevel(logging.INFO)
logging.getLogger().addHandler(in_memory_handler)
logging.getLogger().setLevel(logging.INFO)

# --- 配置 ---
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
HTTP_FILE = os.path.join(OUTPUT_DIR, "http.txt")
SOCKS5_FILE = os.path.join(OUTPUT_DIR, "socks5.txt")

# --- 新增：全局状态变量 (使用字典存储，方便扩展) ---
# 在生产环境中，建议使用数据库或 Redis 来存储这种状态，以支持多实例部署
fetch_status = {
    'is_running': False,
    'last_result': None, # None, True, False
    'last_run_timestamp': None
}

# --- 代理源定义 (保持不变) ---
SOURCES = [
    {"name": "TheSpeedX/PROXY-List (SOCKS5)", "url": "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt", "parser": "text", "protocol": "socks5"},
    {"name": "hookzof/socks5_list", "url": "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt", "parser": "text", "protocol": "socks5"},
    {"name": "ProxyScraper/ProxyScraper (SOCKS5)", "url": "https://raw.githubusercontent.com/ProxyScraper/ProxyScraper/main/socks5.txt", "parser": "text", "protocol": "socks5"},
    {"name": "proxifly/free-proxy-list (HTTP)", "url": "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/http/data.txt", "parser": "text", "protocol": "http"},
    {"name": "zloi-user/hideip.me (SOCKS5)", "url": "https://raw.githubusercontent.com/zloi-user/hideip.me/master/socks5.txt", "parser": "text", "protocol": "socks5"},
    {"name": "gfpcom/free-proxy-list (SOCKS5)", "url": "https://raw.githubusercontent.com/gfpcom/free-proxy-list/main/list/socks5.txt", "parser": "text", "protocol": "socks5"},
    {"name": "monosans/proxy-list (JSON)", "url": "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies.json", "parser": "json-list", "protocol": "socks5"},
    {"name": "fate0/proxylist (JSON)", "url": "https://raw.githubusercontent.com/fate0/proxylist/master/proxy.list", "parser": "json", "protocol": "dynamic"},
]

# --- 辅助函数 (保持不变或微调) ---
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

def save_proxies_to_file(proxies_set, filename):
    if not proxies_set:
        app.logger.warning(f"代理列表 '{filename}' 为空，无需保存。")
        return False

    try:
        sorted_proxies = sorted(list(proxies_set))
        with open(filename, 'w', encoding='utf-8') as f:
            for proxy in sorted_proxies:
                f.write(f"{proxy}\n")
        app.logger.info(f"{len(sorted_proxies)} 个代理已成功保存到: {filename}")
        return True
    except Exception as e:
        app.logger.error(f"保存文件 '{filename}' 时出错: {e}")
        return False

# --- 核心获取函数 (保持不变) ---
def fetch_proxies_task():
    """后台任务：获取并保存代理"""
    global fetch_status # 引用全局状态变量
    start_time = time.time()
    app.logger.info("后台任务开始获取代理...")
    http_proxies = set()
    socks5_proxies = set()

    try: # 在整个任务外层加 try-except
        for source in SOURCES:
            if not fetch_status.get('is_running', False): # 允许提前中断 (可选)
                 app.logger.info("后台任务被标记为停止，正在退出...")
                 break

            app.logger.info(f"正在从 {source['name']} 获取代理列表...")
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
                        protocol = deduce_protocol(line, source['protocol'])
                        cleaned_proxy = clean_proxy_line(line)
                    elif source['parser'] == 'json-list':
                         try:
                             proxy_data = json.loads(line)
                             host = proxy_data.get('ip') or proxy_data.get('host')
                             port = proxy_data.get('port')
                             if host and port:
                                 cleaned_proxy = f"{host}:{port}"
                                 protocol = source.get('protocol', 'socks5')
                         except json.JSONDecodeError as e:
                             app.logger.warning(f"解析 JSON 行失败 ({source['name']}): {e}")
                             continue
                    elif source['parser'] == 'json':
                        try:
                            proxies_list = json.loads(content)
                            for proxy_info in proxies_list:
                                host = proxy_info.get("host")
                                port = proxy_info.get("port")
                                proxy_type = proxy_info.get("type", source['protocol']).lower()
                                if host and port:
                                    cleaned_proxy = f"{host}:{port}"
                                    protocol = proxy_type
                                    if 'http' in protocol:
                                        http_proxies.add(f"http://{cleaned_proxy}")
                                    elif 'socks5' in protocol:
                                        socks5_proxies.add(f"socks5://{cleaned_proxy}")
                            break
                        except json.JSONDecodeError as e:
                             app.logger.error(f"解析 JSON 响应失败 ({source['name']}): {e}")
                             break

                    if not cleaned_proxy:
                        continue

                    if 'http' in protocol:
                        http_proxies.add(f"http://{cleaned_proxy}")
                    elif 'socks5' in protocol:
                        socks5_proxies.add(f"socks5://{cleaned_proxy}")

                new_http = len(http_proxies) - initial_http_count
                new_socks5 = len(socks5_proxies) - initial_socks5_count
                app.logger.info(f"从此来源添加了 {new_http} 个HTTP代理, {new_socks5} 个SOCKS5代理。")

            except requests.exceptions.RequestException as e:
                app.logger.error(f"从 {source['name']} 获取代理时出错: {e}")
            except Exception as e:
                app.logger.error(f"处理 {source['name']} 时发生未预期错误: {e}")

            app.logger.info("-" * 20)
        
        http_success = save_proxies_to_file(http_proxies, HTTP_FILE)
        socks5_success = save_proxies_to_file(socks5_proxies, SOCKS5_FILE)
        
        # 更新全局状态
        end_time = time.time()
        duration = end_time - start_time
        if http_success or socks5_success:
            app.logger.info(f"代理获取和保存完成 (耗时 {duration:.2f} 秒)。")
            fetch_status['last_result'] = True
        else:
            app.logger.warning(f"代理获取或保存失败 (耗时 {duration:.2f} 秒)。")
            fetch_status['last_result'] = False
            
    except Exception as e:
        app.logger.error(f"后台任务执行过程中发生未捕获的异常: {e}")
        app.logger.error(traceback.format_exc())
        fetch_status['last_result'] = False
    finally:
        fetch_status['is_running'] = False
        fetch_status['last_run_timestamp'] = time.time()
        app.logger.info("后台任务已结束。")


# --- Flask 路由 ---

@app.route('/')
def home():
    return redirect('/index')

@app.route('/index')
def index():
    return render_template('index.html')

# --- 修改：启动异步任务的 API ---
@app.route('/api/fetch_proxies', methods=['POST'])
def fetch_proxies_api():
    global fetch_status
    # 检查是否已有任务在运行
    if fetch_status.get('is_running', False):
        app.logger.info("收到获取代理请求，但任务已在运行中。")
        return jsonify({'status': 'already_running'}), 429 # 429 Too Many Requests

    # 启动后台线程
    app.logger.info("收到获取代理请求，正在启动后台任务...")
    fetch_status['is_running'] = True
    fetch_status['last_result'] = None
    fetch_status['last_run_timestamp'] = time.time()
    
    # 使用 threading.Thread 创建并启动后台线程
    thread = threading.Thread(target=fetch_proxies_task)
    thread.start()
    
    # 立即返回响应，不等待任务完成
    return jsonify({'status': 'started'})

# --- 新增：查询任务状态的 API ---
@app.route('/api/fetch_status')
def fetch_status_api():
    global fetch_status
    # 返回当前状态
    status_copy = fetch_status.copy() # 返回副本，避免直接暴露内部状态
    # 可以添加更多格式化信息
    if status_copy['last_run_timestamp']:
        status_copy['last_run_time'] = time.ctime(status_copy['last_run_timestamp'])
    else:
        status_copy['last_run_time'] = None
    return jsonify(status_copy)

# --- 其他路由 (保持不变) ---
@app.route('/api/get_proxies/<protocol>')
def get_proxies(protocol):
    filename = HTTP_FILE if protocol == 'http' else SOCKS5_FILE if protocol == 'socks5' else None
    if not filename or not os.path.exists(filename):
        return jsonify({'proxies': []})

    try:
        with open(filename, 'r', encoding='utf-8') as f:
            proxies = [line.strip() for line in f if line.strip()]
        return jsonify({'proxies': proxies})
    except Exception as e:
        error_msg = f"读取文件 '{filename}' 时出错: {e}"
        app.logger.error(error_msg)
        return jsonify({'proxies': [], 'error': error_msg}), 500

@app.route('/api/logs')
def get_logs():
    logs = list(in_memory_handler.log_buffer)
    return jsonify({'logs': logs})

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False)




