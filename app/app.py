import os
import json
import requests

# --- 配置 ---
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__)) # 保存到 app 目录下
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
                     except json.JSONDecodeError:
                         continue
                elif source['parser'] == 'json':
                    try:
                        proxy_info = json.loads(line)
                        host = proxy_info.get("host")
                        port = proxy_info.get("port")
                        proxy_type = proxy_info.get("type", source['protocol']).lower()
                        if host and port:
                            cleaned_proxy = f"{host}:{port}"
                            protocol = proxy_type
                    except json.JSONDecodeError:
                        continue

                if not cleaned_proxy:
                    continue

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

# ... (app.py 的其他部分) ...

if __name__ == '__main__':
    # 当直接运行此文件时启动 Flask (例如 python -m app.app)
    # 注意：实际部署时，应使用 WSGI 服务器如 Gunicorn
    # 确保这里绑定的地址和端口与 launch.py 中的 FLASK_HOST, FLASK_PORT 一致
    app.run(host='127.0.0.1', port=5000, debug=False) 

