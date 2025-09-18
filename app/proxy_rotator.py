# app/proxy_rotator.py
import time
import random
from collections import deque

rotation_history = deque(maxlen=50)

def rotate_proxy(protocol):
    new_proxy = f"{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}:8080"
    rotation_history.append({
        "timestamp": int(time.time()),
        "protocol": protocol,
        "old_proxy": "old_proxy_placeholder",
        "new_proxy": new_proxy
    })
    return f"{protocol}://{new_proxy}"

def set_auto_rotation(enabled, interval_seconds):
    if enabled:
        print(f"[ROTATOR] Auto rotation enabled every {interval_seconds} seconds.")
    else:
        print("[ROTATOR] Auto rotation disabled.")
    return "Auto rotation setting updated."

def get_rotation_history():
    return list(rotation_history)
