# app/proxy_rotator.py
import time
import random
import threading
from collections import deque

rotation_history = deque(maxlen=50)
auto_rotation_thread = None
auto_rotation_event = threading.Event()

# 假设从 app.py 导入全局状态（需确保 app.py 中 state 是模块级变量）
try:
    from .app import state
except ImportError:
    from app import state  # 用于直接运行

def get_random_proxy(protocol):
    """从已验证代理池中随机选取一个"""
    proxies = state.validated_proxies.get(protocol, {})
    if not proxies:
        return None
    return random.choice(list(proxies.keys()))

def rotate_proxy(protocol):
    global state
    current_proxy = getattr(state, 'current_proxy', {}).get(protocol)
    new_proxy = get_random_proxy(protocol)
    
    if not new_proxy:
        return None

    rotation_history.append({
        "timestamp": int(time.time()),
        "protocol": protocol,
        "old_proxy": current_proxy,
        "new_proxy": new_proxy
    })

    # 更新全局状态
    if not hasattr(state, 'current_proxy'):
        state.current_proxy = {}
    state.current_proxy[protocol] = new_proxy

    print(f"[ROTATOR] {protocol.upper()} 代理已轮换: {current_proxy} -> {new_proxy}")
    return new_proxy

def auto_rotation_worker(protocol, interval):
    while not auto_rotation_event.is_set():
        rotate_proxy(protocol)
        auto_rotation_event.wait(interval)

def set_auto_rotation(enabled, interval_seconds, protocol='http'):
    global auto_rotation_thread, auto_rotation_event

    if enabled:
        if auto_rotation_thread and auto_rotation_thread.is_alive():
            auto_rotation_event.set()
            auto_rotation_thread.join()

        auto_rotation_event.clear()
        auto_rotation_thread = threading.Thread(
            target=auto_rotation_worker,
            args=(protocol, interval_seconds),
            daemon=True
        )
        auto_rotation_thread.start()
        print(f"[ROTATOR] Auto rotation for {protocol} enabled every {interval_seconds} seconds.")
    else:
        if auto_rotation_thread and auto_rotation_thread.is_alive():
            auto_rotation_event.set()
            auto_rotation_thread.join()
        print(f"[ROTATOR] Auto rotation for {protocol} disabled.")

def get_rotation_history():
    return list(rotation_history)
