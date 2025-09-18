# app/app.py
import os
import json
import requests
import traceback
import logging
from collections import deque, OrderedDict
import threading
import time
import asyncio
import aiohttp
from aiohttp import web
import aiohttp_socks
from urllib.parse import urlparse
import ipaddress
import random
import concurrent.futures
from flask import Flask, render_template, jsonify, request, redirect
import socket
import subprocess # 用于检查端口是否被占用

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
VALIDATED_HTTP_FILE = os.path.join(OUTPUT_DIR, "validated_http.json")
VALIDATED_SOCKS5_FILE = os.path.join(OUTPUT_DIR, "validated_socks5.json")

# --- 本地代理服务器配置 ---
LOCAL_HTTP_PORT = 1801
LOCAL_SOCKS5_PORT = 1800

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

# --- 全局状态管理 ---
# 使用一个简单的类来管理状态，方便扩展
class ProxyManagerState:
    def __init__(self):
        self.fetch_status = {
            'is_running': False,
            'last_result': None,
            'last_run_timestamp': None
        }
        self.validation_status = {
            'is_running': False,
            'progress': 0,
            'last_run_timestamp': None
        }
        self.local_service_status = {
            'http_running': False,
            'socks5_running': False,
            'http_server': None,
            'socks5_server': None,
            'http_runner': None,
            'socks5_runner': None,
        }
        self.current_proxies = {
            'http': None,
            'socks5': None
        }
        self.validated_proxies = {
            'http': OrderedDict(), # 保持插入顺序，方便轮换
            'socks5': OrderedDict()
        }
        self.rotation_settings = {
            'auto_rotate': False,
            'interval_seconds': 300, # 默认5分钟
            'rotation_timer': None
        }
        self.rotation_history = deque(maxlen=100) # 记录轮换历史

state = ProxyManagerState()

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

def save_proxies_to_file(proxies_set, filename):
    if not proxies_set:
        app.logger.warning(f"代理列表 '{filename}' 为空，无需保存。")
        return False
    try:
        sorted_proxies = sorted(list(proxies_set))
        with open(filename, 'w', encoding='utf-8') as f:
            for proxy in sorted_proxies:
                f.write(f"{proxy}\n")
        app.logger.info(f"{len(sorted_proxies)} 个原始代理已成功保存到: {filename}")
        return True
    except Exception as e:
        app.logger.error(f"保存文件 '{filename}' 时出错: {e}")
        return False

def save_validated_proxies_to_file(validated_proxies_dict, filename):
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(validated_proxies_dict, f, indent=4)
        app.logger.info(f"已验证代理已成功保存到: {filename}")
        return True
    except Exception as e:
        app.logger.error(f"保存已验证代理文件 '{filename}' 时出错: {e}")
        return False

def load_validated_proxies_from_file(filename):
    if not os.path.exists(filename):
        return {}
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # 确保加载的数据是 OrderedDict
        return OrderedDict(data)
    except Exception as e:
        app.logger.error(f"加载已验证代理文件 '{filename}' 时出错: {e}")
        return {}

def is_port_in_use(port):
    """检查端口是否被占用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

# --- 核心获取函数 ---
def fetch_proxies_task():
    """后台任务：获取并保存代理"""
    start_time = time.time()
    app.logger.info("后台任务开始获取代理...")
    http_proxies = set()
    socks5_proxies = set()

    try:
        for source in SOURCES:
            if not state.fetch_status.get('is_running', False):
                app.logger.info("后台获取任务被标记为停止，正在退出...")
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
        
        end_time = time.time()
        duration = end_time - start_time
        if http_success or socks5_success:
            app.logger.info(f"代理获取和保存完成 (耗时 {duration:.2f} 秒)。")
            state.fetch_status['last_result'] = True
        else:
            app.logger.warning(f"代理获取或保存失败 (耗时 {duration:.2f} 秒)。")
            state.fetch_status['last_result'] = False
            
    except Exception as e:
        app.logger.error(f"后台获取任务执行过程中发生未捕获的异常: {e}")
        app.logger.error(traceback.format_exc())
        state.fetch_status['last_result'] = False
    finally:
        state.fetch_status['is_running'] = False
        state.fetch_status['last_run_timestamp'] = time.time()
        app.logger.info("后台获取任务已结束。")

# --- 高质量验证函数 ---
async def test_single_proxy(session, proxy_url, test_url="http://httpbin.org/ip", timeout=10):
    """异步测试单个代理的质量"""
    start_time = time.monotonic()
    result = {
        'url': proxy_url,
        'alive': False,
        'ping': None,
        'speed_kbps': None,
        'country': 'Unknown',
        'error': None
    }
    
    parsed_url = urlparse(proxy_url)
    proxy_type = parsed_url.scheme.lower()
    host_port = f"{parsed_url.hostname}:{parsed_url.port}"

    try:
        # 1. Ping 测试 (通过连接建立时间模拟)
        # 这已经在 aiohttp 的连接超时中体现
        
        # 2. 可用性 & 速度测试
        connector = None
        if proxy_type == 'http':
            connector = aiohttp.TCPConnector()
        elif proxy_type == 'socks5':
            connector = aiohttp_socks.ProxyConnector.from_url(proxy_url)
        else:
            result['error'] = f"Unsupported proxy type: {proxy_type}"
            return result

        async with aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=timeout)) as test_session:
            fetch_start = time.monotonic()
            async with test_session.get(test_url) as response:
                if response.status == 200:
                    content = await response.read()
                    fetch_end = time.monotonic()
                    
                    # 计算延迟 (连接+请求响应时间)
                    result['ping'] = int((fetch_end - start_time) * 1000) # ms
                    
                    # 计算速度 KB/s
                    content_length_kb = len(content) / 1024.0
                    download_time_s = fetch_end - fetch_start
                    if download_time_s > 0:
                        result['speed_kbps'] = int(content_length_kb / download_time_s)
                    else:
                        result['speed_kbps'] = 0 # 理论上极快或瞬时
                    
                    result['alive'] = True
                    
                    # 3. 简单的国家信息 (这里简化处理，实际可调用IP地理库)
                    # 这里我们只做基本验证，不包含国家信息
                    # 可以通过返回的IP信息进一步查询
                    
    except asyncio.TimeoutError:
        result['error'] = 'Timeout'
    except aiohttp.ClientError as e:
        result['error'] = str(e)
    except Exception as e:
        result['error'] = f"Unexpected error: {e}"
    finally:
        if 'connector' in locals() and connector:
            await connector.close()
    
    return result

async def validate_proxies_task():
    """后台任务：验证代理质量"""
    start_time = time.time()
    app.logger.info("后台任务开始验证代理质量...")
    state.validation_status['is_running'] = True
    state.validation_status['progress'] = 0

    try:
        # 加载原始代理列表
        http_proxies = set()
        socks5_proxies = set()
        
        if os.path.exists(HTTP_FILE):
            with open(HTTP_FILE, 'r', encoding='utf-8') as f:
                http_proxies = {line.strip() for line in f if line.strip()}
        if os.path.exists(SOCKS5_FILE):
            with open(SOCKS5_FILE, 'r', encoding='utf-8') as f:
                socks5_proxies = {line.strip() for line in f if line.strip()}

        total_proxies = len(http_proxies) + len(socks5_proxies)
        if total_proxies == 0:
            app.logger.warning("没有代理需要验证。")
            state.validation_status['last_result'] = False
            return

        validated_http = OrderedDict()
        validated_socks5 = OrderedDict()
        processed = 0

        # 使用 aiohttp 异步并发测试
        async with aiohttp.ClientSession() as session:
            # 创建所有测试任务
            tasks = []
            for proxy_url in http_proxies:
                tasks.append(test_single_proxy(session, proxy_url))
            for proxy_url in socks5_proxies:
                tasks.append(test_single_proxy(session, proxy_url))

            # 并发执行测试 (可以限制并发数)
            semaphore = asyncio.Semaphore(100) # 限制并发数为100

            async def sem_task(task):
                async with semaphore:
                    return await task

            for f in asyncio.as_completed([sem_task(t) for t in tasks]):
                result = await f
                processed += 1
                progress = int((processed / total_proxies) * 100)
                state.validation_status['progress'] = progress
                app.logger.debug(f"验证进度: {progress}% ({processed}/{total_proxies})")

                if result['alive']:
                    # 这里可以根据 ping 和 speed 进行筛选，例如只保留 ping < 1000ms 且 speed > 10kbps 的
                    # if result['ping'] and result['ping'] < 1000 and result['speed_kbps'] and result['speed_kbps'] > 10:
                    if result['ping'] and result['speed_kbps']: # 基本筛选
                        parsed_url = urlparse(result['url'])
                        key = f"{parsed_url.hostname}:{parsed_url.port}"
                        if parsed_url.scheme.lower() == 'http':
                            validated_http[key] = result
                        elif parsed_url.scheme.lower() == 'socks5':
                            validated_socks5[key] = result

        # 保存验证结果
        save_validated_proxies_to_file(dict(validated_http), VALIDATED_HTTP_FILE)
        save_validated_proxies_to_file(dict(validated_socks5), VALIDATED_SOCKS5_FILE)
        
        # 更新全局状态
        state.validated_proxies['http'] = validated_http
        state.validated_proxies['socks5'] = validated_socks5
        
        end_time = time.time()
        duration = end_time - start_time
        app.logger.info(f"代理验证完成 (耗时 {duration:.2f} 秒)。有效HTTP代理: {len(validated_http)}, 有效SOCKS5代理: {len(validated_socks5)}")
        state.validation_status['last_result'] = True

    except Exception as e:
        app.logger.error(f"后台验证任务执行过程中发生未捕获的异常: {e}")
        app.logger.error(traceback.format_exc())
        state.validation_status['last_result'] = False
    finally:
        state.validation_status['is_running'] = False
        state.validation_status['progress'] = 100
        state.validation_status['last_run_timestamp'] = time.time()
        app.logger.info("后台验证任务已结束。")

# --- 本地代理服务器逻辑 ---
async def create_forwarding_handler(upstream_proxy_url):
    """创建一个转发处理器，将请求转发到上游代理"""
    parsed_upstream = urlparse(upstream_proxy_url)
    if parsed_upstream.scheme.lower() not in ['http', 'socks5']:
        raise ValueError(f"Unsupported upstream proxy scheme: {parsed_upstream.scheme}")

    async def handler(request):
        try:
            # 构造目标URL
            target_url = str(request.url.with_scheme('http')) # aiohttp 默认处理 https

            # 根据上游代理类型创建连接器
            connector = None
            if parsed_upstream.scheme.lower() == 'http':
                connector = aiohttp.TCPConnector()
            elif parsed_upstream.scheme.lower() == 'socks5':
                connector = aiohttp_socks.ProxyConnector.from_url(upstream_proxy_url)

            # 转发请求
            async with aiohttp.ClientSession(connector=connector) as client_session:
                # 准备请求参数
                headers = {k: v for k, v in request.headers.items() if k.lower() != 'host'}
                data = await request.read()
                
                async with client_session.request(
                    method=request.method,
                    url=target_url,
                    headers=headers,
                    data=data,
                    allow_redirects=False # 让客户端处理重定向
                ) as proxy_response:
                    # 将上游响应返回给客户端
                    response_headers = {k: v for k, v in proxy_response.headers.items()}
                    body = await proxy_response.read()
                    return web.Response(
                        status=proxy_response.status,
                        headers=response_headers,
                        body=body
                    )
        except Exception as e:
            app.logger.error(f"转发请求时出错 ({upstream_proxy_url} -> {request.method} {request.path_qs}): {e}")
            return web.Response(status=502, text=f"Bad Gateway: {str(e)}")

    return handler

async def start_local_http_proxy(proxy_url, port):
    """启动本地 HTTP 代理服务器"""
    if is_port_in_use(port):
        app.logger.error(f"无法启动本地 HTTP 代理，端口 {port} 已被占用。")
        return None

    app_handler = await create_forwarding_handler(proxy_url)
    app_server = web.Application()
    app_server.router.add_route('*', '/{path:.*}', app_handler)
    
    runner = web.AppRunner(app_server)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', port)
    await site.start()
    app.logger.info(f"本地 HTTP 代理服务器已在 127.0.0.1:{port} 启动，使用上游代理: {proxy_url}")
    return runner

async def start_local_socks5_proxy(proxy_url, port):
    """启动本地 SOCKS5 代理服务器 (简化版，实际应使用专用库如 PySocks)"""
    # 注意：aiohttp 本身不提供 SOCKS5 服务器功能。
    # 这里为了演示，我们简化处理，实际部署时应使用专门的 SOCKS5 服务器库。
    # 一个常见的选择是使用 `aiosocks` 或 `proxy.py` 等。
    # 为保持一致性，我们这里也尝试用 aiohttp 简单模拟，但这不是标准的 SOCKS5 服务器。
    # 更推荐的做法是调用外部命令或集成一个成熟的 SOCKS5 服务器。
    
    # 由于 aiohttp 不直接支持 SOCKS5 server，我们在此仅做占位符说明。
    # 实际实现会复杂得多，需要处理 SOCKS5 协议握手等。
    # 为简化，我们在此不实现真实的 SOCKS5 服务器，而是记录日志。
    # 在生产环境中，你应该使用如 `proxy.py` 这样的库。
    app.logger.warning("本地 SOCKS5 代理服务器启动逻辑未实现。需要集成专门的 SOCKS5 服务器库。此处仅为占位。")
    # 模拟启动成功
    return "MockSocks5Runner"

def stop_local_http_proxy():
    """停止本地 HTTP 代理服务器"""
    if state.local_service_status['http_runner']:
        try:
            loop = asyncio.new_event_loop() # 在新线程中需要自己的事件循环
            asyncio.set_event_loop(loop)
            loop.run_until_complete(state.local_service_status['http_runner'].cleanup())
            app.logger.info("本地 HTTP 代理服务器已停止。")
        except Exception as e:
            app.logger.error(f"停止本地 HTTP 代理服务器时出错: {e}")
        finally:
            state.local_service_status['http_runner'] = None
            state.local_service_status['http_running'] = False

def stop_local_socks5_proxy():
    """停止本地 SOCKS5 代理服务器"""
    # 由于未实现真实服务器，这里也简化处理
    if state.local_service_status['socks5_runner']:
        app.logger.info("本地 SOCKS5 代理服务器已停止 (模拟)。")
        state.local_service_status['socks5_runner'] = None
        state.local_service_status['socks5_running'] = False

# --- IP 轮换逻辑 ---
def rotate_proxy(protocol):
    """手动轮换指定协议的代理"""
    validated_dict = state.validated_proxies.get(protocol, OrderedDict())
    if not validated_dict:
