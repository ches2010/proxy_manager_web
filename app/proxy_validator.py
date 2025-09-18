# app/proxy_validator.py
import time
import random

def validate_proxies_task():
    """模拟代理验证任务"""
    print("[VALIDATOR] Starting proxy validation...")
    time.sleep(5)  # 模拟耗时
    print("[VALIDATOR] Proxy validation completed.")
    return True

def get_validation_status():
    return {
        "is_running": False,
        "progress": 100,
        "last_result": True
    }

def get_validated_proxies(protocol='all'):
    """返回模拟的已验证代理"""
    sample = {
        "http": {
            "1.1.1.1:8080": {"ping": 120, "speed_kbps": 512},
            "2.2.2.2:3128": {"ping": 89, "speed_kbps": 1024}
        },
        "socks5": {
            "3.3.3.3:1080": {"ping": 65, "speed_kbps": 2048},
            "4.4.4.4:1081": {"ping": 200, "speed_kbps": 256}
        }
    }
    if protocol == 'all':
        return sample
    return {protocol: sample.get(protocol, {})}
