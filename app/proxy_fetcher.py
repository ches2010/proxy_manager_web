import os
import json
import requests
import re
import time  # ✅ 修复：导入 time 模块以支持 time.sleep
from pathlib import Path

# --- 配置 ---
OUTPUT_DIR = Path(__file__).parent
HTTP_FILE = OUTPUT_DIR / "http.txt"
SOCKS5_FILE = OUTPUT_DIR / "socks5.txt"

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

# --- 辅助函数：IP:PORT 格式校验 ---
def is_valid_ip_port(proxy_str):
    if not isinstance(proxy_str, str):
        return False
    pattern = r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{1,5}$'
    if re.match(pattern, proxy_str):
        try:
            ip, port_str = proxy_str.split(':')
            port = int(port_str)
            if not (1 <= port <= 65535):
                return False
            octets = list(map(int, ip.split('.')))
            if len(octets) != 4:
                return False
            if all(0 <= o <= 255 for o in octets):
                return True
        except (ValueError, IndexError):
            return False
    return False

# --- 清洗代理行 ---
def clean_proxy_line(line):
    line = line.strip()
    if not line:
        return None
    for proto in ['http://', 'https://', 'socks4://', 'socks5://']:
        if line.startswith(proto):
            line = line[len(proto):]
    if '@' in line:
        line = line.split('@')[-1]
    parts = line.split(':', 1)
    if len(parts) == 2:
        ip = parts[0].strip()
        port_part = parts[1].split()[0].strip()
        if ip and port_part.isdigit():
            candidate = f"{ip}:{port_part}"
            if is_valid_ip_port(candidate):
                return candidate
    return None

# --- 协议推断 ---
def deduce_protocol(original_line, default_protocol):
    line_lower = original_line.lower()
    if 'socks5' in line_lower:
        return 'socks5'
    if 'socks4' in line_lower:
        return 'socks4'
    if 'https' in line_lower:
        return 'http'  # https 代理也走 http:// 前缀
    if 'http' in line_lower:
        return 'http'
    return default_protocol

# --- 保存文件 ---
def save_proxies_to_file(proxies_set, filename):
    if not proxies_set:
        print(f"\n[-] 代理列表 '{filename}' 为空，无需保存。")
        return False
    try:
        sorted_proxies = sorted(list(proxies_set))
        with open(filename, 'w', encoding='utf-8') as f:
            for proxy in sorted_proxies:
                f.write(f"{proxy}\n")
        print(f"\n[SUCCESS] {len(sorted_proxies)} 个代理已成功保存到: {filename}")
        return True
    except Exception as e:
        print(f"\n[ERROR] 保存文件 '{filename}' 时出错: {e}")
        return False

# --- 核心获取函数 ---
def fetch_proxies_task():
    print("[*] 开始获取代理...")
    http_proxies = set()
    socks5_proxies = set()

    for source in SOURCES:
        print(f"[*] 正在从 {source['name']} 获取代理列表...")
        try:
            # 添加重试机制
            for attempt in range(3):
                try:
                    response = requests.get(source['url'], timeout=15)
                    response.raise_for_status()
                    break
                except Exception as e:
                    if attempt == 2:
                        raise e
                    print(f"  [!] 尝试 {attempt + 1} 失败: {e}. 正在重试...")
                    time.sleep(1) # ✅ 修复：现在 time.sleep 可以正常工作
            
            initial_http_count = len(http_proxies)
            initial_socks5_count = len(socks5_proxies)
            content = response.text.strip()

            # ✅ 修复：json-list 解析
            if source['parser'] == 'json-list':
                try:
                    proxy_list = json.loads(content)
                    if not isinstance(proxy_list, list):
                        raise ValueError("Expected JSON array")
                    for item in proxy_list:
                        if not isinstance(item, dict):
                            continue
                        host = item.get('ip') or item.get('host')
                        port = item.get('port')
                        if host and port:
                            port_str = str(port).split()[0]
                            candidate = f"{host}:{port_str}"
                            if is_valid_ip_port(candidate):
                                # ✅ 修复：根据源配置的 protocol 判断
                                protocol = source.get('protocol', 'socks5')
                                if 'http' in protocol:
                                    http_proxies.add(f"http://{candidate}")
                                elif 'socks5' in protocol:
                                    socks5_proxies.add(f"socks5://{candidate}")
                    new_http = len(http_proxies) - initial_http_count
                    new_socks5 = len(socks5_proxies) - initial_socks5_count
                    print(f"[+] 从此来源添加了 {new_http} 个HTTP代理, {new_socks5} 个SOCKS5代理。")
                    print("-" * 20)
                    continue
                except (json.JSONDecodeError, ValueError, TypeError) as e:
                    print(f"[!] JSON 解析失败 ({source['name']}): {e}")
                    print("-" * 20)
                    continue

            lines = content.split('\n')
            for line in lines:
                if not line.strip():
                    continue
                protocol = source['protocol']
                cleaned_proxy = None

                if source['parser'] == 'text':
                    protocol = deduce_protocol(line, source['protocol'])
                    cleaned_proxy = clean_proxy_line(line)
                elif source['parser'] == 'json':
                    try:
                        proxy_info = json.loads(line)
                        if not isinstance(proxy_info, dict):
                            continue
                        host = proxy_info.get("host")
                        port = proxy_info.get("port")
                        proxy_type = proxy_info.get("type", source['protocol']).lower()
                        if host and port:
                            port_str = str(port).split()[0]
                            candidate = f"{host}:{port_str}"
                            if is_valid_ip_port(candidate):
                                cleaned_proxy = candidate
                                protocol = proxy_type
                    except (json.JSONDecodeError, TypeError):
                        continue

                if cleaned_proxy and is_valid_ip_port(cleaned_proxy):
                    if 'http' in protocol:
                        http_proxies.add(f"http://{cleaned_proxy}")
                    elif 'socks5' in protocol:
                        socks5_proxies.add(f"socks5://{cleaned_proxy}")

            new_http = len(http_proxies) - initial_http_count
            new_socks5 = len(socks5_proxies) - initial_socks5_count
            print(f"[+] 从此来源添加了 {new_http} 个HTTP代理, {new_socks5} 个SOCKS5代理。")
        except requests.exceptions.RequestException as e:
            print(f"[!] 从 {source['name']} 获取代理时出错: {e}")
        print("-" * 20)

    http_success = save_proxies_to_file(http_proxies, HTTP_FILE)
    socks5_success = save_proxies_to_file(socks5_proxies, SOCKS5_FILE)

    if http_success or socks5_success:
        print("[SUCCESS] 代理获取和保存完成。")
        return True
    else:
        print("[FAILURE] 代理获取或保存失败。")
        return False

# --- 脚本入口点 ---
if __name__ == "__main__":
    fetch_proxies_task()

