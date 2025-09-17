# Proxy Manager

一个集成了代理获取、配置管理和 Web 前端界面的工具，并通过 Cloudflare Tunnel 实现安全的远程访问。

## 功能

*   从多个 GitHub 源获取 HTTP 和 SOCKS5 代理列表。
*   通过 Web 界面触发代理获取任务、查看状态、加载/保存配置、查看获取到的代理列表。
*   使用 Cloudflare Tunnel 提供安全的 HTTPS 公网访问地址。

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/你的用户名/proxy_manager.git
cd proxy_manager
```

### 2. 安装依赖

确保你已安装 Python 3.7+ 和 pip。

```bash
# (推荐) 创建并激活虚拟环境
# python -m venv venv
# source venv/bin/activate (Linux/macOS) 或 venv\Scripts\activate (Windows)

pip install -r requirements.txt
```

### 3. 安装 Cloudflared (必需)

为了能从外部访问 Web 界面，你需要安装 `cloudflared` CLI 工具。它将自动为你创建一个临时的公网 URL (Quick Tunnel)。

*   **官方安装指南**: [https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/)
*   **macOS (Homebrew)**: `brew install cloudflare/cloudflare/cloudflared`
*   **Linux (Debian/Ubuntu)**:
    ```bash
    wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
    sudo dpkg -i cloudflared-linux-amd64.deb
    ```
*   **Windows (Chocolatey)**: `choco install cloudflared`
*   **Windows (Scoop)**: `scoop install cloudflared`
*   **手动下载**: 从 [GitHub Releases](https://github.com/cloudflare/cloudflared/releases) 下载对应平台的二进制文件，并将其放入系统 PATH。

**验证安装**: 在终端运行 `cloudflared --version`，应能看到版本号。

### 4. 运行应用

使用 launch.py 脚本一键启动 Flask 应用和 Cloudflare Quick Tunnel。

```bash
python launch.py
```

*   脚本启动后，Flask 应用将在 `http://localhost:5000` 运行。
*   `cloudflared` 会自动创建一个临时的公网 URL (格式通常是 `https://<random-subdomain>.trycloudflare.com`)，并在终端中打印出来。
*   **注意**: Quick Tunnel 生成的 URL 是临时的，每次重启 `cloudflared` 都会变化，并且可能在一段时间不活动后失效。

### 5. 访问界面

*   **本地访问**: 打开浏览器访问 `http://localhost:5000`。
*   **远程访问**: 打开浏览器访问终端中打印出的公网 URL (例如 `https://abc123.trycloudflare.com`)。
---

### 3. `app.py` (Flask 后端) - *确认绑定地址*

确保 `app.py` 在直接运行时绑定到 `127.0.0.1` 或 `0.0.0.0`。我们已经在 `run.py` 中通过 `--host 127.0.0.1` 参数确保了这一点。`app.py` 末尾的代码如下：

```python
# ... (省略前面的代码) ...

if __name__ == '__main__':
    # 当直接运行此文件时启动 Flask (例如 python -m app.app)
    # 注意：实际部署时，应使用 WSGI 服务器如 Gunicorn
    app.run(host='127.0.0.1', port=5000, debug=False) # <-- 这里确保绑定到 127.0.0.1
```

这个配置是正确的，`cloudflared` 会通过 `http://127.0.0.1:5000` 访问你的 Flask 应用。

---

### 4. 运行应用

**方法一：使用 run.py 脚本 (推荐)**

此脚本会尝试自动启动 Flask 应用和已配置的 Cloudflare Tunnel。

```bash
python run.py
```

*   脚本启动后，Flask 应用将在 `http://localhost:5000` 运行。
*   如果你已正确配置了 Cloudflare Tunnel，`cloudflared` 会自动连接并将流量转发到你的本地应用。终端会显示公网访问地址 (类似 `https://<your-subdomain>.cloudflare.com`)。

**方法二：手动运行**

1.  **启动 Flask 应用**:
    ```bash
    python -m app.app
    ```
    Flask 应用将在 `http://localhost:5000` 运行。

2.  **启动 Cloudflare Tunnel**:
    *   如果你使用了令牌方式配置隧道:
        ```bash
        cloudflared tunnel --no-autoupdate run --token <YOUR_TUNNEL_TOKEN>
        ```
    *   或者，如果你有配置文件:
        ```bash
        cloudflared tunnel --config /path/to/your/cloudflared/config.yml run
        ```

### 5. 访问界面

*   **本地访问**: 打开浏览器访问 `http://localhost:5000`。
*   **远程访问**: 打开浏览器访问你在 Cloudflare Tunnel 中配置的公网 URL。

## 文件说明

*   `config.json`: 应用的配置文件。
*   `app/app.py`: Flask Web 应用的核心代码。
*   `app/proxy_fetcher.py`: 代理获取和处理的逻辑。
*   `app/templates/index.html`: Web 前端页面。
*   `app/static/style.css`: Web 前端样式。
*   `run.py`: 一键启动脚本。
*   `requirements.txt`: Python 依赖。
*   `README.md`: 本文件。

## 注意

*   首次运行时，可能需要一些时间来获取所有代理源。
*   请确保你的网络可以访问 GitHub 和其他代理源。
*   `run.py` 脚本假设 `cloudflared` 已安装并在系统 PATH 中。它目前不直接启动 tunnel，你需要预先配置好。未来可以扩展为自动管理 tunnel 生命周期。

---
