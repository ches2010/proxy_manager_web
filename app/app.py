# app/app.py
import os
import json
import requests
import traceback
import logging
from collections import deque # 用于创建一个有最大长度的列表，作为日志缓冲区
from flask import Flask, render_template, jsonify, request, redirect

# --- 配置日志 ---
# 创建一个自定义的日志处理器，将日志存储在内存中
class InMemoryHandler(logging.Handler):
    def __init__(self, max_logs=1000):
        super().__init__()
        # 使用 deque 可以自动丢弃旧日志，保持列表大小
        self.log_buffer = deque(maxlen=max_logs)

    def emit(self, record):
        # 格式化日志记录
        log_entry = self.format(record)
        # 添加到缓冲区
        self.log_buffer.append(log_entry)

# 创建 Flask 应用实例
app = Flask(__name__)

# --- 设置日志记录 ---
# 创建自定义处理器实例
in_memory_handler = InMemoryHandler(max_logs=1000)
# 设置日志格式
formatter = logging.Formatter('[%(asctime)s] %(levelname)s in %(module)s: %(message)s')
in_memory_handler.setFormatter(formatter)
# 将处理器添加到 Flask 应用的日志记录器
app.logger.addHandler(in_memory_handler)
# 设置日志级别
app.logger.setLevel(logging.INFO)
# 也确保根日志记录器能捕获来自 requests 等库的日志
logging.getLogger().addHandler(in_memory_handler)
logging.getLogger().setLevel(logging.INFO)

# --- 配置 ---
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
HTTP_FILE = os.path.join(OUTPUT_DIR, "http.txt")
SOCKS5_FILE = os.path.join(OUTPUT_DIR, "socks5.txt")

# --- 代理源定义 ---
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

# --- 辅助函数 ---
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

# --- 保存文件函数 ---
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

# --- 核心获取函数 ---
def fetch_proxies_task():
    """后台任务：获取并保存代理"""
    app.logger.info("开始获取代理...")
    http_proxies = set()
    socks5_proxies = set()

    for source in SOURCES:
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
                         # 处理每行一个 JSON 对象的情况
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
                        # 处理整个响应是一个 JSON 数组的情况
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
                        # 处理完整个列表后跳出循环
                        break
                    except json.JSONDecodeError as e:
                         app.logger.error(f"解析 JSON 响应失败 ({source['name']}): {e}")
                         break # 解析失败则跳过此源

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
    
    if http_success or socks5_success:
        app.logger.info("代理获取和保存完成。")
        return True
    else:
        app.logger.warning("代理获取或保存失败。")
        return False

# --- Flask 路由 ---

# 根路径重定向到 /index
@app.route('/')
def home():
    return redirect('/index')

# 主页面
@app.route('/index')
def index():
    return render_template('index.html')

# API: 触发代理获取
@app.route('/api/fetch_proxies', methods=['POST'])
def fetch_proxies_api():
    try:
        app.logger.info("收到获取代理请求...")
        success = fetch_proxies_task()
        app.logger.info(f"代理获取任务完成, 结果: {success}")
        return jsonify({'success': success})
    except Exception as e:
        error_msg = f"处理 /api/fetch_proxies 时发生未预期错误: {str(e)}"
        app.logger.error(error_msg)
        app.logger.error(traceback.format_exc()) # 记录堆栈跟踪
        return jsonify({'success': False, 'error': error_msg}), 500

# API: 获取代理列表
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

# 新增 API: 获取后端日志
@app.route('/api/logs')
def get_logs():
    # 从内存处理器中获取日志
    logs = list(in_memory_handler.log_buffer)
    return jsonify({'logs': logs})

# --- 主程序入口 ---
if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False)




