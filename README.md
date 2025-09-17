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

### 3. 配置 Cloudflare Tunnel (可选但推荐)

为了能从外部访问 Web 界面，你需要设置 Cloudflare Tunnel。

1.  注册并登录 [Cloudflare](https://www.cloudflare.com/)。
2.  在 Cloudflare 仪表板中，导航到 **Zero Trust** > **Access** > **Tunnels**。
3.  **创建隧道** (Create a tunnel)。
4.  选择 **Cloudflared** 客户端，并按照指示下载 `cloudflared` CLI 工具（如果尚未安装）。
5.  按照 Cloudflare 提供的命令安装 Connector (这通常涉及运行一个 `cloudflared` 命令来关联你的机器和隧道)。
6.  在隧道配置中，添加一个 **Public Hostname**：
    *   **Subdomain**: (可选，留空则生成随机子域)
    *   **Domain**: 选择你的 Cloudflare 域名。
    *   **Path**: `/`
    *   **Type**: `HTTP`
    *   **URL**: `localhost:5000` (这是 Flask 应用的本地地址)
7.  保存配置。

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
