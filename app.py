from flask import Flask, render_template, jsonify, request, send_file
import threading
import queue
import json
import os
import time
import logging
from datetime import datetime

# --- 导入您的核心模块 ---
# 为了简化，我们假设 hq.py 的功能被集成或调用
# 实际开发中，您需要将 main.py 中的逻辑（如 ProxyFetcher, ProxyChecker）适配为 Flask 可调用的函数
# 这里我们创建一个模拟的后端管理器

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this-in-production'

# --- 模拟全局状态和队列 ---
# 在真实应用中，这些应该由您的 ProxyFetcher, ProxyChecker 等类管理
global_state = {
    'is_running_task': False,
    'cancel_event': threading.Event(),
    'displayed_proxies': set(),
    'proxy_to_item_map': {}, # 简化为字典
    'current_proxy': "N/A",
    'is_server_running': False,
    'is_auto_rotating': False,
    'settings': {
        'general': {
            'validation_threads': 100,
            'failure_threshold': 3,
            'auto_retest_enabled': False,
            'auto_retest_interval': 10
        },
        'auto_fetch': {
            'fofa': {'enabled': True, 'key': '', 'query': 'protocol=="socks5" && country=="CN" && banner="Method:No"', 'size': 500},
            'hunter': {'enabled': False, 'key': '', 'query': 'app.name="SOCKS5"', 'size': 100},
        }
    }
}

# 日志队列，供前端轮询
log_queue = queue.Queue()

# --- 模拟日志函数 ---
def log_to_web(message):
    """将日志消息放入队列，供前端获取"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    formatted_message = f"[{timestamp}] {message}"
    log_queue.put(formatted_message)
    # 也可以同时打印到控制台
    print(formatted_message)

# --- 初始化设置 ---
def load_settings():
    """从文件加载配置"""
    try:
        if os.path.exists("config.json"):
            with open("config.json", 'r', encoding='utf-8') as f:
                loaded_settings = json.load(f)
                # Deep merge dictionaries
                for key, value in loaded_settings.items():
                    if isinstance(value, dict) and isinstance(global_state['settings'].get(key), dict):
                        global_state['settings'][key].update(value)
                    else:
                        global_state['settings'][key] = value
            log_to_web("已从 config.json 加载配置。")
    except Exception as e:
        log_to_web(f"[!] 加载配置文件失败: {e}")

def save_settings():
    """保存当前配置到文件"""
    try:
        with open("config.json", 'w', encoding='utf-8') as f:
            json.dump(global_state['settings'], f, indent=4, ensure_ascii=False)
        log_to_web("设置已保存到 config.json。")
    except Exception as e:
        log_to_web(f"[!] 保存配置文件失败: {e}")

load_settings()

# --- 模拟后台任务 ---
def mock_fetch_and_validate_task():
    """模拟获取和验证代理的任务"""
    global_state['cancel_event'].clear()
    global_state['is_running_task'] = True
    total_steps = 10
    for i in range(total_steps):
        if global_state['cancel_event'].is_set():
            log_to_web("任务已被用户取消。")
            break
        time.sleep(1) # 模拟耗时操作
        progress = int(((i + 1) / total_steps) * 100)
        log_to_web(f"正在获取和验证代理... {progress}%")
        # 模拟添加一些代理
        if i % 3 == 0:
            proxy_str = f"192.168.1.{i+1}:1080"
            global_state['displayed_proxies'].add(proxy_str)
            global_state['proxy_to_item_map'][proxy_str] = {
                'score': 80 + i,
                'anonymity': '高匿' if i % 2 == 0 else '普匿',
                'protocol': 'socks5',
                'delay': 150 + i*10,
                'speed': round(5.0 - i*0.2, 2),
                'region': '中国'
            }
    global_state['is_running_task'] = False
    log_to_web("代理获取与验证任务完成。")

def mock_start_proxy_server():
    """模拟启动代理服务器"""
    # 这里应该调用您 modules/server.py 中的 ProxyServer 类
    global_state['is_server_running'] = True
    log_to_web("代理服务 (SOCKS5:1800 / HTTP:1801) 已启动。")

def mock_stop_proxy_server():
    """模拟停止代理服务器"""
    global_state['is_server_running'] = False
    log_to_web("代理服务已停止。")

def mock_rotate_proxy():
    """模拟轮换代理"""
    if global_state['displayed_proxies']:
        new_proxy = list(global_state['displayed_proxies'])[0] # 简单取第一个
        global_state['current_proxy'] = new_proxy
        log_to_web(f"已轮换到代理: {new_proxy}")
    else:
        log_to_web("无可用代理进行轮换。")

# --- API Routes ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def get_status():
    """获取应用当前状态"""
    return jsonify({
        'is_running_task': global_state['is_running_task'],
        'is_server_running': global_state['is_server_running'],
        'is_auto_rotating': global_state['is_auto_rotating'],
        'current_proxy': global_state['current_proxy'],
        'proxy_count': len(global_state['displayed_proxies'])
    })

@app.route('/api/logs')
def get_logs():
    """获取最新的日志条目"""
    logs = []
    while not log_queue.empty():
        try:
            log_entry = log_queue.get_nowait()
            logs.append(log_entry)
        except queue.Empty:
            break
    return jsonify({'logs': logs})

@app.route('/api/proxies')
def get_proxies():
    """获取当前代理列表 (支持分页和过滤，这里简化)"""
    # 在真实应用中，这里应该从您的 ProxyRotator 或类似管理器获取数据
    proxies = []
    for proxy_str, details in global_state['proxy_to_item_map'].items():
        proxy_data = details.copy()
        proxy_data['proxy'] = proxy_str
        proxies.append(proxy_data)
    
    # 简单排序 (可根据请求参数改进)
    sort_by = request.args.get('sort_by', 'score')
    reverse = request.args.get('reverse', 'true').lower() == 'true'
    proxies.sort(key=lambda x: x.get(sort_by, 0), reverse=reverse)
    
    return jsonify({'proxies': proxies})

@app.route('/api/start_fetch', methods=['POST'])
def start_fetch():
    """开始获取代理任务"""
    if global_state['is_running_task']:
        return jsonify({'status': 'error', 'message': '已有任务正在运行'})
    
    threading.Thread(target=mock_fetch_and_validate_task, daemon=True).start()
    return jsonify({'status': 'success', 'message': '代理获取任务已启动'})

@app.route('/api/cancel_task', methods=['POST'])
def cancel_task():
    """取消当前任务"""
    if not global_state['is_running_task']:
        return jsonify({'status': 'error', 'message': '没有正在运行的任务'})
    
    global_state['cancel_event'].set()
    return jsonify({'status': 'success', 'message': '已请求取消任务'})

@app.route('/api/clear_proxies', methods=['POST'])
def clear_proxies():
    """清空代理列表"""
    global_state['displayed_proxies'].clear()
    global_state['proxy_to_item_map'].clear()
    global_state['current_proxy'] = "N/A"
    log_to_web("代理列表已清空。")
    return jsonify({'status': 'success', 'message': '代理列表已清空'})

@app.route('/api/start_server', methods=['POST'])
def start_server():
    """启动代理服务"""
    if global_state['is_server_running']:
        return jsonify({'status': 'error', 'message': '代理服务已在运行'})
    
    threading.Thread(target=mock_start_proxy_server, daemon=True).start()
    return jsonify({'status': 'success', 'message': '代理服务启动中...'})

@app.route('/api/stop_server', methods=['POST'])
def stop_server():
    """停止代理服务"""
    if not global_state['is_server_running']:
        return jsonify({'status': 'error', 'message': '代理服务未运行'})
    
    threading.Thread(target=mock_stop_proxy_server, daemon=True).start()
    return jsonify({'status': 'success', 'message': '代理服务停止中...'})

@app.route('/api/rotate_proxy', methods=['POST'])
def rotate_proxy():
    """手动轮换代理"""
    threading.Thread(target=mock_rotate_proxy, daemon=True).start()
    return jsonify({'status': 'success', 'message': '正在轮换代理...'})

@app.route('/api/settings', methods=['GET', 'POST'])
def handle_settings():
    """处理设置的获取和保存"""
    if request.method == 'GET':
        return jsonify(global_state['settings'])
    elif request.method == 'POST':
        new_settings = request.json
        global_state['settings'].update(new_settings)
        save_settings()
        log_to_web("设置已通过API更新并保存。")
        return jsonify({'status': 'success', 'message': '设置已保存'})

@app.route('/api/export_proxies')
def export_proxies():
    """导出代理列表到文件"""
    filename = "exported_proxies.txt"
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            for proxy in global_state['displayed_proxies']:
                f.write(f"{proxy}\n")
        log_to_web(f"代理列表已导出到 {filename}")
        return send_file(filename, as_attachment=True)
    except Exception as e:
        log_to_web(f"导出代理失败: {e}")
        return jsonify({'status': 'error', 'message': f'导出失败: {str(e)}'})

# --- 初始化日志 ---
log_to_web("代理池Web管理器已启动。")

if __name__ == '__main__':
    # 在生产环境中，应使用 Gunicorn 或 uWSGI
    app.run(host='0.0.0.0', port=5000, debug=True)
