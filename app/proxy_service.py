# app/proxy_service.py
"""
本地代理服务模块
功能：启动一个本地 HTTP/SOCKS5 代理服务器，将流量转发到用户选定的远程代理。
用途：让浏览器或其他不支持直接设置代理的应用，通过访问 localhost:8080 / 1080 来使用代理。
"""

import asyncio
import threading
import socket
import logging
from urllib.parse import urlparse
from typing import Dict, Optional

# aiohttp 用于 HTTP 代理转发
import aiohttp
from aiohttp import web
from aiohttp_socks import ProxyConnector, ProxyType

# 导入全局状态（假设在 app.py 中定义）
try:
    from .app import state
except ImportError:
    from app import state  # 用于直接运行或测试

# --- 配置 ---
LOCAL_HTTP_PORT = 8080
LOCAL_SOCKS5_PORT = 1080

# --- 全局服务管理器 ---
class ProxyServiceManager:
    def __init__(self):
        self.http_server: Optional[web.TCPSite] = None
        self.socks5_server = None  # asyncio.Server
        self.http_thread: Optional[threading.Thread] = None
        self.socks5_thread: Optional[threading.Thread] = None
        self.loop_http: Optional[asyncio.AbstractEventLoop] = None
        self.loop_socks5: Optional[asyncio.AbstractEventLoop] = None
        self._lock = threading.Lock()
        self.logger = logging.getLogger("ProxyService")

    async def http_proxy_handler(self, request: web.Request):
        """HTTP 代理处理器（支持 CONNECT 隧道）"""
        target_url = request.url
        method = request.method

        # 获取当前选中的 HTTP 代理
        current_proxy = getattr(state, 'current_proxy', {}).get('http')
        if not current_proxy:
            return web.Response(status=502, text="No HTTP proxy selected")

        try:
            # 创建代理连接器
            connector = ProxyConnector.from_url(current_proxy)

            async with aiohttp.ClientSession(connector=connector) as session:
                # 转发请求
                async with session.request(
                    method=method,
                    url=target_url,
                    headers=request.headers,
                    data=await request.read() if method not in ('GET', 'HEAD') else None,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    # 流式转发响应
                    response = web.StreamResponse(status=resp.status, headers=resp.headers)
                    await response.prepare(request)
                    async for chunk in resp.content.iter_any():
                        await response.write(chunk)
                    await response.write_eof()
                    return response

        except Exception as e:
            self.logger.error(f"HTTP Proxy Error: {e}")
            return web.Response(status=502, text=f"Proxy Error: {str(e)}")

    async def start_http_server(self, host='127.0.0.1', port=LOCAL_HTTP_PORT):
        """启动本地 HTTP 代理服务器"""
        app = web.Application()
        app.router.add_route('*', '/{tail:.*}', self.http_proxy_handler)  # 捕获所有路径

        runner = web.AppRunner(app)
        await runner.setup()
        self.http_server = web.TCPSite(runner, host, port)
        await self.http_server.start()
        self.logger.info(f"HTTP 代理服务已启动: http://{host}:{port}")

    async def socks5_proxy_handler(self, reader, writer):
        """简易 SOCKS5 代理处理器（仅支持 CONNECT）"""
        try:
            # 1. 握手
            data = await reader.read(2)
            if len(data) < 2 or data[0] != 0x05:
                writer.close()
                return

            nmethods = data[1]
            await reader.read(nmethods)  # 忽略方法列表
            writer.write(b'\x05\x00')  # 选择无认证
            await writer.drain()

            # 2. 请求
            data = await reader.read(4)
            if len(data) < 4 or data[0] != 0x05 or data[1] != 0x01:
                writer.close()
                return

            addr_type = data[3]
            target_host = ""
            target_port = 0

            if addr_type == 0x01:  # IPv4
                data = await reader.read(6)
                target_host = socket.inet_ntoa(data[:4])
                target_port = int.from_bytes(data[4:6], 'big')
            elif addr_type == 0x03:  # 域名
                domain_len = await reader.read(1)
                domain = await reader.read(domain_len[0])
                target_host = domain.decode()
                port_data = await reader.read(2)
                target_port = int.from_bytes(port_data, 'big')
            else:
                writer.close()
                return

            # 获取当前选中的 SOCKS5 代理
            current_proxy = getattr(state, 'current_proxy', {}).get('socks5')
            if not current_proxy:
                writer.close()
                return

            # 解析当前代理
            parsed = urlparse(current_proxy)
            proxy_host = parsed.hostname
            proxy_port = parsed.port

            # 连接到远程 SOCKS5 代理
            remote_reader, remote_writer = await asyncio.open_connection(proxy_host, proxy_port)

            # 发送相同的 SOCKS5 请求给远程代理
            remote_writer.write(data[:3] + bytes([addr_type]))
            await remote_writer.drain()

            if addr_type == 0x01:
                remote_writer.write(socket.inet_aton(target_host) + target_port.to_bytes(2, 'big'))
            elif addr_type == 0x03:
                remote_writer.write(bytes([len(target_host)]) + target_host.encode() + target_port.to_bytes(2, 'big'))

            await remote_writer.drain()

            # 转发响应
            resp = await remote_reader.read(2)
            writer.write(resp)
            await writer.drain()

            if resp[1] == 0x00:  # 成功
                # 开始双向转发
                async def forward(reader_in, writer_out):
                    try:
                        while True:
                            data = await reader_in.read(4096)
                            if not data:
                                break
                            writer_out.write(data)
                            await writer_out.drain()
                    except:
                        pass
                    finally:
                        writer_out.close()

                await asyncio.gather(
                    forward(reader, remote_writer),
                    forward(remote_reader, writer)
                )

        except Exception as e:
            self.logger.error(f"SOCKS5 Proxy Error: {e}")
        finally:
            writer.close()

    async def start_socks5_server(self, host='127.0.0.1', port=LOCAL_SOCKS5_PORT):
        """启动本地 SOCKS5 代理服务器"""
        self.socks5_server = await asyncio.start_server(
            self.socks5_proxy_handler, host, port
        )
        self.logger.info(f"SOCKS5 代理服务已启动: socks5://{host}:{port}")
        async with self.socks5_server:
            await self.socks5_server.serve_forever()

    def _run_http_server(self):
        """在独立线程中运行 HTTP 代理"""
        self.loop_http = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop_http)
        try:
            self.loop_http.run_until_complete(self.start_http_server())
            self.loop_http.run_forever()
        except Exception as e:
            self.logger.error(f"HTTP Server Error: {e}")

    def _run_socks5_server(self):
        """在独立线程中运行 SOCKS5 代理"""
        self.loop_socks5 = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop_socks5)
        try:
            self.loop_socks5.run_until_complete(self.start_socks5_server())
            self.loop_socks5.run_forever()
        except Exception as e:
            self.logger.error(f"SOCKS5 Server Error: {e}")

    def start_service(self, protocol: str):
        """启动指定协议的本地代理服务"""
        with self._lock:
            if protocol == 'http' and (not self.http_thread or not self.http_thread.is_alive()):
                self.http_thread = threading.Thread(target=self._run_http_server, daemon=True)
                self.http_thread.start()
                return True
            elif protocol == 'socks5' and (not self.socks5_thread or not self.socks5_thread.is_alive()):
                self.socks5_thread = threading.Thread(target=self._run_socks5_server, daemon=True)
                self.socks5_thread.start()
                return True
        return False

    def stop_service(self, protocol: str):
        """停止指定协议的本地代理服务"""
        with self._lock:
            if protocol == 'http' and self.loop_http:
                self.loop_http.call_soon_threadsafe(self.loop_http.stop)
                self.http_thread = None
                self.loop_http = None
                return True
            elif protocol == 'socks5' and self.loop_socks5:
                if self.socks5_server:
                    self.loop_socks5.call_soon_threadsafe(self.socks5_server.close)
                self.loop_socks5.call_soon_threadsafe(self.loop_socks5.stop)
                self.socks5_thread = None
                self.loop_socks5 = None
                return True
        return False

    def get_status(self) -> Dict[str, bool]:
        """获取服务状态"""
        return {
            "http": self.http_thread is not None and self.http_thread.is_alive(),
            "socks5": self.socks5_thread is not None and self.socks5_thread.is_alive()
        }

# --- 全局实例 ---
service_manager = ProxyServiceManager()

# --- 对外 API ---
def start_proxy_service(protocol: str) -> bool:
    """启动本地代理服务"""
    return service_manager.start_service(protocol)

def stop_proxy_service(protocol: str) -> bool:
    """停止本地代理服务"""
    return service_manager.stop_service(protocol)

def get_service_status() -> Dict[str, bool]:
    """获取服务状态"""
    return service_manager.get_status()
