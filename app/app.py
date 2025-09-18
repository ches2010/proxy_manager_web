# app/app.py
import os
import sys
import json
import time
import signal
import asyncio
import aiohttp
import logging
import requests
import threading
import subprocess
from datetime import datetime, timedelta
from collections import OrderedDict
from flask import Flask, jsonify, render_template, request

# --- 导入项目内部模块 ---
# 使用相对导入，因为 proxy_fetcher.py 与 app.py 在同一目录 (app/)
# 注意：如果直接运行此脚本，相对导入会失败。应通过 `flask run` 或包方式运行。
# 如果遇到导入问题，请检查启动方式或调整导入路径。
try:
    from . import proxy_fetcher
except ImportError:
    # Fallback for direct execution or different structure
    import proxy_fetcher


# --- 配置 ---
# 从 config.json 加载配置
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config.json')
try:
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        CONFIG = json.load(f)
except FileNotFoundError:
    print(f"[ERROR] Configuration file not found at {CONFIG_PATH}. Using defaults.")
    CONFIG = {}
except json.JSONDecodeError as e:
    print(f"[ERROR] Error decoding config.json: {e}. Using defaults.")
    CONFIG = {}

# --- 全局状态管理 ---
class State:
    def __init__(self):
        self.validated_proxies = {'http': OrderedDict(), 'socks5': OrderedDict()}
        self.validation_in_progress = False
        self.fetching_in_progress = False
        self.last_validation_time = None
        self.failed_counts = {} # {proxy: count}
        self.failure_threshold = CONFIG.get("general", {}).get("failure_threshold", 3)
        self.auto_retest_enabled = CONFIG.get("general", {}).get("auto_retest_enabled", True)
        self.auto_retest_interval = CONFIG.get("general", {}).get("auto_retest_interval", 5) * 60 # Convert to seconds
        # --- 新增状态用于日志和轮换历史 ---
        self.logs = [] # 简单的日志列表
        self.rotation_history = [] # 简单的轮换历史列表

state = State()

# --- Flask App 初始化 ---
app = Flask(__name__, static_folder='static', template_folder='templates')

# --- 日志配置 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- 辅助函数 ---

def load_config():
    """重新加载配置文件"""
    global CONFIG
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            CONFIG = json.load(f)
        state.failure_threshold = CONFIG.get("general", {}).get("failure_threshold", 3)
        state.auto_retest_enabled = CONFIG.get("general", {}).get("auto_retest_enabled", True)
        state.auto_retest_interval = CONFIG.get("general", {}).get("auto_retest_interval", 5) * 60
        logger.info("Configuration reloaded.")
        state.logs.append(f"[INFO] {datetime.now().isoformat()} - Configuration reloaded.")
    except Exception as e:
        error_msg = f"[ERROR] Failed to reload configuration: {e}"
        logger.error(error_msg)
        state.logs.append(error_msg)


def load_proxies_from_files():
    """从本地文件加载代理"""
    logger.info("Loading proxies from local files...")
    state.logs.append(f"[INFO] {datetime.now().isoformat()} - Loading proxies from local files...")
    http_file = proxy_fetcher.HTTP_FILE
    socks5_file = proxy_fetcher.SOCKS5_FILE

    def read_proxies(filename, protocol):
        proxies = OrderedDict()
        if os.path.exists(filename):
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    for line in f:
                        proxy = line.strip()
                        if proxy:
                            # 初始化时，所有代理都放入 validated_proxies，等待验证
                            proxies[proxy] = {
                                'last_checked': None,
                                'response_time': None,
                                'status': 'unchecked'
                            }
                logger.info(f"Loaded {len(proxies)} {protocol} proxies from {filename}")
                state.logs.append(f"[INFO] {datetime.now().isoformat()} - Loaded {len(proxies)} {protocol} proxies from {filename}")
            except Exception as e:
                error_msg = f"[ERROR] Error reading {filename}: {e}"
                logger.error(error_msg)
                state.logs.append(error_msg)
        else:
            warning_msg = f"[WARNING] Proxy file {filename} not found."
            logger.warning(warning_msg)
            state.logs.append(warning_msg)
        return proxies

    state.validated_proxies['http'] = read_proxies(http_file, 'http')
    state.validated_proxies['socks5'] = read_proxies(socks5_file, 'socks5')
    logger.info("Finished loading proxies from files.")
    state.logs.append(f"[INFO] {datetime.now().isoformat()} - Finished loading proxies from files.")


async def test_single_proxy(session, proxy_url, test_url, timeout=5):
    """异步测试单个代理"""
    try:
        connector = None
        if proxy_url.startswith('http'):
            connector = aiohttp.TCPConnector(limit=0) # Disable connection pooling for proxies
            proxy_param = proxy_url
        elif proxy_url.startswith('socks5'):
            # aiohttp 需要 aiosocks 或类似库支持 socks5，这里简化处理
            # 实际应用中需要正确配置 socks 连接器
            # 为简化，我们假设 socks5 测试逻辑不同或在此处标记
            # 这里我们仍然尝试用 aiohttp，但实际可能需要特殊处理
            # 暂时按 http 方式处理，后续需根据实际需求调整
            connector = aiohttp.TCPConnector(limit=0)
            proxy_param = proxy_url
        else:
            return None, None

        start_time = time.time()
        async with session.get(test_url, proxy=proxy_param, timeout=timeout, connector=connector) as response:
            if response.status == 200:
                response_time = (time.time() - start_time) * 1000 # ms
                return response_time, 'working'
            else:
                return None, 'failed'
    except asyncio.TimeoutError:
        return None, 'timeout'
    except Exception as e:
        # logger.debug(f"Proxy {proxy_url} failed: {e}") # Debug level to avoid spam
        return None, 'error'


async def validate_proxies_async(protocol, test_url, num_threads=100):
    """异步验证指定协议的代理"""
    logger.info(f"Starting asynchronous validation for {protocol} proxies...")
    state.logs.append(f"[INFO] {datetime.now().isoformat()} - Starting asynchronous validation for {protocol} proxies...")
    proxies_to_test = list(state.validated_proxies.get(protocol, {}).keys())
    if not proxies_to_test:
        logger.info(f"No {protocol} proxies to validate.")
        state.logs.append(f"[INFO] {datetime.now().isoformat()} - No {protocol} proxies to validate.")
        return

    timeout = aiohttp.ClientTimeout(total=10) # Overall request timeout
    connector = aiohttp.TCPConnector(limit=num_threads, limit_per_host=10, ttl_dns_cache=300) # Limit concurrent connections

    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        semaphore = asyncio.Semaphore(num_threads)

        async def bound_test(proxy):
            async with semaphore:
                return await test_single_proxy(session, proxy, test_url)

        tasks = [bound_test(proxy) for proxy in proxies_to_test]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # Process results
    working_proxies = OrderedDict()
    failed_proxies = []
    for proxy, result in zip(proxies_to_test, results):
        if isinstance(result, Exception):
            error_msg = f"[ERROR] Exception during validation of {proxy}: {result}"
            logger.error(error_msg)
            state.logs.append(error_msg)
            failed_proxies.append(proxy)
            continue

        response_time, status = result
        details = state.validated_proxies[protocol].get(proxy, {})
        details['last_checked'] = datetime.now().isoformat()
        details['response_time'] = response_time
        details['status'] = status

        if status == 'working':
            # Add to working proxies, maintaining order (re-insert at end if exists)
            if proxy in working_proxies:
                 working_proxies.move_to_end(proxy)
            working_proxies[proxy] = details
        else:
            failed_proxies.append(proxy)
            # Handle failure counting
            current_failures = state.failed_counts.get(proxy, 0) + 1
            state.failed_counts[proxy] = current_failures
            if current_failures >= state.failure_threshold:
                info_msg = f"[INFO] Proxy {proxy} failed {current_failures} times, removing."
                logger.info(info_msg)
                state.logs.append(info_msg)
                state.failed_counts.pop(proxy, None) # Remove from failed count after removal
            # Note: In this async version, we don't immediately remove from state.validated_proxies
            # We rebuild it from working_proxies at the end.

    # Update global state
    # Rebuild validated_proxies for this protocol with only working ones, in order
    state.validated_proxies[protocol] = working_proxies
    success_msg = f"Validation complete for {protocol}. Working: {len(working_proxies)}, Failed: {len(failed_proxies)}"
    logger.info(success_msg)
    state.logs.append(f"[INFO] {datetime.now().isoformat()} - {success_msg}")
    state.last_validation_time = datetime.now()


def run_validation_task(protocol='all'):
    """运行代理验证任务"""
    if state.validation_in_progress:
        warning_msg = "Validation task is already running."
        logger.warning(warning_msg)
        state.logs.append(f"[WARNING] {datetime.now().isoformat()} - {warning_msg}")
        return jsonify({"status": "error", "message": "Validation already in progress"}), 429

    state.validation_in_progress = True
    try:
        logger.info("Proxy validation task started.")
        state.logs.append(f"[INFO] {datetime.now().isoformat()} - Proxy validation task started.")
        num_threads = CONFIG.get("general", {}).get("validation_threads", 100)
        
        # 确定要验证的协议
        protocols_to_validate = ['http', 'socks5'] if protocol == 'all' else [protocol]

        # 为每个协议创建并运行异步任务
        async def run_all_validations():
            tasks = [
                validate_proxies_async(proto, "http://httpbin.org/ip", num_threads)
                for proto in protocols_to_validate
            ]
            await asyncio.gather(*tasks)

        # 在新事件循环中运行（如果不在已有循环中）
        if sys.platform == 'win32':
             asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(run_all_validations())

        success_msg = "Proxy validation task completed successfully."
        logger.info(success_msg)
        state.logs.append(f"[INFO] {datetime.now().isoformat()} - {success_msg}")
        return jsonify({"status": "success", "message": "Validation completed"}), 200
    except Exception as e:
        error_msg = f"Proxy validation task failed: {e}"
        logger.error(error_msg)
        state.logs.append(f"[ERROR] {datetime.now().isoformat()} - {error_msg}")
        return jsonify({"status": "error", "message": f"Validation failed: {str(e)}"}), 500
    finally:
        state.validation_in_progress = False


def run_fetch_task():
    """运行代理获取任务"""
    if state.fetching_in_progress:
        warning_msg = "Fetching task is already running."
        logger.warning(warning_msg)
        state.logs.append(f"[WARNING] {datetime.now().isoformat()} - {warning_msg}")
        return jsonify({"status": "error", "message": "Fetching already in progress"}), 429

    state.fetching_in_progress = True
    try:
        logger.info("Proxy fetching task started.")
        state.logs.append(f"[INFO] {datetime.now().isoformat()} - Proxy fetching task started.")
        success = proxy_fetcher.fetch_proxies_task()
        if success:
            # 获取成功后，重新加载文件到内存
            load_proxies_from_files()
            success_msg = "Proxy fetching task completed and proxies reloaded."
            logger.info(success_msg)
            state.logs.append(f"[INFO] {datetime.now().isoformat()} - {success_msg}")
            return jsonify({"status": "success", "message": "Proxies fetched and reloaded"}), 200
        else:
            error_msg = "Proxy fetching task failed."
            logger.error(error_msg)
            state.logs.append(f"[ERROR] {datetime.now().isoformat()} - {error_msg}")
            return jsonify({"status": "error", "message": "Fetching failed"}), 500
    except Exception as e:
        error_msg = f"Proxy fetching task failed with exception: {e}"
        logger.error(error_msg)
        state.logs.append(f"[ERROR] {datetime.now().isoformat()} - {error_msg}")
        return jsonify({"status": "error", "message": f"Fetching failed: {str(e)}"}), 500
    finally:
        state.fetching_in_progress = False


# --- IP 轮换逻辑 (已修复) ---
def rotate_proxy(protocol):
    """手动轮换指定协议的代理"""
    validated_dict = state.validated_proxies.get(protocol, OrderedDict())
    
    # --- 修复部分：添加缩进的代码块 ---
    if not validated_dict:
        warning_msg = f"No validated proxies available to rotate for protocol: {protocol}"
        logger.warning(warning_msg)
        state.logs.append(f"[WARNING] {datetime.now().isoformat()} - {warning_msg}")
        # 根据应用逻辑，可以选择返回 None 或抛出异常
        return None # 表示轮换失败，因为没有代理可轮换

    try:
        # 使用 popitem(last=False) 获取并移除第一个键值对 (FIFO)
        proxy, details = validated_dict.popitem(last=False)
        # 将获取到的代理重新添加到字典末尾，实现轮换效果
        validated_dict[proxy] = details
        # 更新全局状态中的代理字典（如果 state.validated_proxies[protocol] 是直接引用，则此步可能非必需，但更安全）
        state.validated_proxies[protocol] = validated_dict 
        info_msg = f"Rotated proxy for {protocol}: {proxy}"
        logger.info(info_msg)
        # 记录轮换历史
        state.rotation_history.append({
            'timestamp': datetime.now().isoformat(),
            'protocol': protocol,
            'proxy': proxy
        })
         # 限制历史记录大小，例如只保留最后 100 条
        if len(state.rotation_history) > 100:
            state.rotation_history.pop(0) # 移除最旧的记录

        state.logs.append(f"[INFO] {datetime.now().isoformat()} - {info_msg}")
        # 返回刚刚被轮换（移动）的那个代理
        return proxy
    except Exception as e:
        error_msg = f"Error rotating proxy for {protocol}: {e}"
        logger.error(error_msg)
        state.logs.append(f"[ERROR] {datetime.now().isoformat()} - {error_msg}")
        # 轮换过程中出错也返回 None
        return None


# --- Flask 路由 (已修改以匹配前端) ---
@app.route('/')
def index():
    return render_template('index.html')


# --- 修改路由路径以匹配前端 ---
# 原来是 @app.route('/api/proxies')
@app.route('/api/validated_proxies') # 匹配前端 /api/validated_proxies
def get_proxies():
    protocol = request.args.get('protocol', 'all')
    if protocol == 'all':
        data = {
            'http': [{'proxy': k, **v} for k, v in state.validated_proxies.get('http', {}).items()],
            'socks5': [{'proxy': k, **v} for k, v in state.validated_proxies.get('socks5', {}).items()]
        }
    else:
        data = [{'proxy': k, **v} for k, v in state.validated_proxies.get(protocol, {}).items()]
    return jsonify(data)

# 原来是 @app.route('/api/proxy/rotate/<protocol>', methods=['POST'])
# 注意：前端可能通过 GET 请求轮换，或者这个路由可能不存在于前端。根据你的 app.py 逻辑，轮换是 POST。
# 如果前端是 GET，需要修改。这里假设前端是 POST。
@app.route('/api/proxy/rotate/<protocol>', methods=['POST']) # 保持原样，因为前端 JS 通常用 POST
def api_rotate_proxy(protocol):
    if protocol not in ['http', 'socks5']:
        return jsonify({"status": "error", "message": "Invalid protocol"}), 400

    rotated_proxy = rotate_proxy(protocol)
    if rotated_proxy:
        return jsonify({"status": "success", "rotated_proxy": rotated_proxy}), 200
    else:
        return jsonify({"status": "error", "message": f"Failed to rotate {protocol} proxy. No proxies available or error occurred."}), 400

# 原来是 @app.route('/api/tasks/fetch', methods=['POST'])
@app.route('/api/fetch_proxies', methods=['POST']) # 匹配前端 /api/fetch_proxies
def api_fetch_proxies():
    # 在后台线程运行，避免阻塞 Flask
    thread = threading.Thread(target=run_fetch_task)
    thread.start()
    return jsonify({"status": "started", "message": "Fetching task started"}), 202

# 原来是 @app.route('/api/tasks/validate', methods=['POST'])
@app.route('/api/validate_proxies', methods=['POST']) # 假设前端有这个调用，路径匹配
def api_validate_proxies():
    data = request.get_json()
    protocol = data.get('protocol', 'all')
    if protocol not in ['http', 'socks5', 'all']:
        return jsonify({"status": "error", "message": "Invalid protocol"}), 400

    # 在后台线程运行，避免阻塞 Flask
    thread = threading.Thread(target=lambda: run_validation_task(protocol))
    thread.start()
    return jsonify({"status": "started", "message": f"Validation task for {protocol} started"}), 202

# 原来是 @app.route('/api/status')
@app.route('/api/service_status') # 匹配前端 /api/service_status
def get_status():
    return jsonify({
        "validation_in_progress": state.validation_in_progress,
        "fetching_in_progress": state.fetching_in_progress,
        "last_validation_time": state.last_validation_time.isoformat() if state.last_validation_time else None,
        "http_proxy_count": len(state.validated_proxies.get('http', {})),
        "socks5_proxy_count": len(state.validated_proxies.get('socks5', {})),
        "auto_retest_enabled": state.auto_retest_enabled,
        "auto_retest_interval_minutes": state.auto_retest_interval / 60,
        "failure_threshold": state.failure_threshold
    })

# 原来是 @app.route('/api/config/reload', methods=['POST'])
# 前端可能没有直接调用这个，但保留以备后用
@app.route('/api/config/reload', methods=['POST'])
def reload_config():
    load_config()
    return jsonify({"status": "success", "message": "Configuration reloaded"}), 200

# --- 新增路由以匹配前端 ---
@app.route('/api/logs') # 匹配前端 /api/logs
def get_logs():
    # 返回存储在 state.logs 中的日志
    # 可以添加查询参数来限制返回的日志数量，例如 ?limit=50
    limit = request.args.get('limit', type=int)
    if limit and limit > 0:
        # 返回最后 limit 条日志
        logs_to_return = state.logs[-limit:]
    else:
        # 返回所有日志（注意：在生产环境中这可能不是好主意）
        logs_to_return = state.logs
    return jsonify(logs_to_return)

@app.route('/api/rotation_history') # 匹配前端 /api/rotation_history
def get_rotation_history():
     # 返回存储在 state.rotation_history 中的轮换历史
     # 同样可以添加查询参数限制
    limit = request.args.get('limit', type=int)
    if limit and limit > 0:
        history_to_return = state.rotation_history[-limit:]
    else:
        history_to_return = state.rotation_history
    return jsonify(history_to_return)

# --- 新增：修复问题的关键路由 ---
# 前端 JavaScript 正在轮询此端点以获取获取任务的状态
@app.route('/api/fetch_status')
def get_fetch_status():
    """
    返回获取代理任务的当前状态。
    """
    return jsonify({
        "fetching_in_progress": state.fetching_in_progress,
        # 可以根据需要添加更多状态信息
        # "last_fetch_time": state.last_fetch_time.isoformat() if hasattr(state, 'last_fetch_time') and state.last_fetch_time else None,
        # "fetch_error": getattr(state, 'fetch_error_message', None) # 如果有错误信息的话
    })


# --- 后台任务 ---
def auto_fetch_task():
    """自动获取代理的后台任务"""
    auto_fetch_config = CONFIG.get("auto_fetch", {})
    fofa_config = auto_fetch_config.get("fofa", {})
    hunter_config = auto_fetch_config.get("hunter", {})

    # 这里可以实现 FOFA/Hunter 的逻辑
    # 由于 proxy_fetcher.py 主要是从公开源获取，这部分逻辑需要你补充
    # 暂时只调用 proxy_fetcher 的任务
    if any([fofa_config.get("enabled"), hunter_config.get("enabled")]):
        logger.info("Auto-fetch from FOFA/Hunter is configured but logic needs implementation in proxy_fetcher.")
        state.logs.append(f"[INFO] {datetime.now().isoformat()} - Auto-fetch from FOFA/Hunter is configured but logic needs implementation in proxy_fetcher.")
    
    # 调用通用 fetch 任务
    run_fetch_task()


def auto_retest_task():
    """自动重新验证代理的后台任务"""
    while True:
        if state.auto_retest_enabled and not state.validation_in_progress:
            logger.info("Starting scheduled auto-retest...")
            state.logs.append(f"[INFO] {datetime.now().isoformat()} - Starting scheduled auto-retest...")
            run_validation_task('all')
        time.sleep(state.auto_retest_interval)


def start_background_tasks():
    """启动后台任务线程"""
    # Auto-fetch task (if needed, logic to be added to proxy_fetcher)
    # fetch_thread = threading.Thread(target=auto_fetch_task, daemon=True)
    # fetch_thread.start()

    # Auto-retest task
    retest_thread = threading.Thread(target=auto_retest_task, daemon=True)
    retest_thread.start()
    logger.info("Background tasks started.")
    state.logs.append(f"[INFO] {datetime.now().isoformat()} - Background tasks started.")


# --- 应用启动逻辑 ---
def main():
    """主函数"""
    logger.info("Starting Proxy Manager application...")
    state.logs.append(f"[INFO] {datetime.now().isoformat()} - Starting Proxy Manager application...")
    
    # 初始加载代理
    load_proxies_from_files()
    
    # 启动后台任务
    start_background_tasks()
    
    # 如果需要，可以在这里进行一次初始验证
    # thread = threading.Thread(target=lambda: run_validation_task('all'))
    # thread.start()
    
    logger.info("Proxy Manager application initialized.")
    state.logs.append(f"[INFO] {datetime.now().isoformat()} - Proxy Manager application initialized.")


if __name__ == '__main__':
    main()
    # 注意：当通过 `flask run` 启动时，不会直接执行到这里
    # 但如果你直接运行 `python app/app.py`，它会执行
    app.run(debug=True) # 通常由 Flask CLI 控制 debug 模式




