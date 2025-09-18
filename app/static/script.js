// script.js - 优化版

// ======================
// 🎯 全局状态 & 配置
// ======================
const API_BASE = '/api';
const REFRESH_INTERVAL = 5000; // 5秒自动刷新状态
let autoRefreshTimer = null;
let isRefreshing = false;

// ======================
// 🧩 DOM 缓存 & 工具函数
// ======================

// 获取元素
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => document.querySelectorAll(selector);

// 显示消息（成功/错误）
function showMessage(message, type = 'info') {
    const container = $('.messages');
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${type}`;
    msgDiv.textContent = message;
    msgDiv.style.opacity = '0';
    container.appendChild(msgDiv);

    // 动画出现
    setTimeout(() => {
        msgDiv.style.transition = 'opacity 0.3s ease';
        msgDiv.style.opacity = '1';
    }, 10);

    // 3秒后淡出并移除
    setTimeout(() => {
        msgDiv.style.opacity = '0';
        setTimeout(() => {
            if (msgDiv.parentNode) {
                container.removeChild(msgDiv);
            }
        }, 300);
    }, 3000);
}

// 设置按钮状态（加载中/禁用）
function setButtonState(button, isLoading = false, isDisabled = false) {
    if (isLoading) {
        button.disabled = true;
        button.innerHTML = `<span class="spinner"></span> ${button.dataset.loadingText || '处理中...'}`;
    } else {
        button.disabled = isDisabled;
        button.innerHTML = button.dataset.originalText || button.textContent;
    }
}

// 格式化时间戳
function formatTimestamp(ts) {
    if (!ts) return 'N/A';
    return new Date(ts * 1000).toLocaleString();
}

// ======================
// 🔄 数据获取与渲染
// ======================

async function fetchData(endpoint, method = 'GET', body = null) {
    const options = {
        method,
        headers: { 'Content-Type': 'application/json' }
    };
    if (body) options.body = JSON.stringify(body);

    try {
        const res = await fetch(`${API_BASE}${endpoint}`, options);
        const data = await res.json();

        if (!data.success) {
            throw new Error(data.message || '操作失败');
        }

        return data;
    } catch (error) {
        showMessage(error.message || '网络错误', 'error');
        throw error;
    }
}

async function refreshAllData() {
    if (isRefreshing) return;
    isRefreshing = true;

    try {
        await Promise.all([
            refreshProxyStatus(),
            refreshValidationStatus(),
            refreshServiceStatus(),
            refreshRotationHistory()
        ]);
    } catch (err) {
        console.error("刷新数据失败:", err);
    } finally {
        isRefreshing = false;
    }
}

// --- 刷新代理状态 ---
async function refreshProxyStatus() {
    try {
        const data = await fetchData('/status');
        $('#http-proxy-display').textContent = data.data.current_proxies?.http || '未设置';
        $('#socks5-proxy-display').textContent = data.data.current_proxies?.socks5 || '未设置';

        // 更新按钮状态
        const hasHttp = !!data.data.current_proxies?.http;
        const hasSocks5 = !!data.data.current_proxies?.socks5;

        $('#use-http-btn').disabled = !hasHttp;
        $('#use-socks5-btn').disabled = !hasSocks5;

        // 更新服务控制按钮状态
        if (hasHttp) {
            $('#start-http-service-btn').disabled = false;
            $('#start-http-service-btn').dataset.originalText = '启动 HTTP 服务';
        }
        if (hasSocks5) {
            $('#start-socks5-service-btn').disabled = false;
            $('#start-socks5-service-btn').dataset.originalText = '启动 SOCKS5 服务';
        }
    } catch (err) {
        console.error("刷新代理状态失败:", err);
    }
}

// --- 刷新验证状态 ---
async function refreshValidationStatus() {
    try {
        const data = await fetchData('/validation_status');
        $('#validation-status').textContent = data.data.status || '未知';
        $('#last-validation-time').textContent = data.data.last_validation_time ?
            new Date(data.data.last_validation_time * 1000).toLocaleString() : '从未';

        const httpCount = Object.keys(data.data.validated_proxies?.http || {}).length;
        const socks5Count = Object.keys(data.data.validated_proxies?.socks5 || {}).length;
        $('#validated-http-count').textContent = httpCount;
        $('#validated-socks5-count').textContent = socks5Count;

        // 启用/禁用验证按钮
        $('#validate-btn').disabled = data.data.status === 'running';
    } catch (err) {
        console.error("刷新验证状态失败:", err);
    }
}

// --- 刷新服务状态 ---
async function refreshServiceStatus() {
    try {
        const data = await fetchData('/service/status');
        const status = data.data;

        const httpServiceStatus = status.http ? '🟢 运行中' : '🔴 已停止';
        const socks5ServiceStatus = status.socks5 ? '🟢 运行中' : '🔴 已停止';

        $('#http-service-status').textContent = httpServiceStatus;
        $('#socks5-service-status').textContent = socks5ServiceStatus;

        // 更新按钮文本和状态
        const startHttpBtn = $('#start-http-service-btn');
        const stopHttpBtn = $('#stop-http-service-btn');
        const startSocks5Btn = $('#start-socks5-service-btn');
        const stopSocks5Btn = $('#stop-socks5-service-btn');

        if (status.http) {
            startHttpBtn.disabled = true;
            stopHttpBtn.disabled = false;
        } else {
            startHttpBtn.disabled = false;
            stopHttpBtn.disabled = true;
        }

        if (status.socks5) {
            startSocks5Btn.disabled = true;
            stopSocks5Btn.disabled = false;
        } else {
            startSocks5Btn.disabled = false;
            stopSocks5Btn.disabled = true;
        }
    } catch (err) {
        console.error("刷新服务状态失败:", err);
    }
}

// --- 刷新轮换历史 ---
async function refreshRotationHistory() {
    try {
        const data = await fetchData('/rotation_history');
        const history = data.data || [];
        const container = $('#rotation-history-list');
        container.innerHTML = '';

        if (history.length === 0) {
            container.innerHTML = '<div class="empty-state">暂无轮换记录</div>';
            return;
        }

        history.slice(-10).reverse().forEach(item => {
            const div = document.createElement('div');
            div.className = 'history-item';
            div.innerHTML = `
                <div><strong>${item.protocol.toUpperCase()}</strong> | ${formatTimestamp(item.timestamp)}</div>
                <div>🔄 ${item.old_proxy || '无'} → ${item.new_proxy}</div>
            `;
            container.appendChild(div);
        });
    } catch (err) {
        console.error("刷新轮换历史失败:", err);
    }
}

// ======================
// 🎛️ 事件处理器
// ======================

// --- 获取并设置代理 ---
async function handleFetchAndSetProxy(protocol) {
    const btn = $(`#fetch-${protocol}-btn`);
    try {
        setButtonState(btn, true);

        const data = await fetchData('/fetch_and_set_proxy', 'POST', { protocol });

        showMessage(`✅ ${protocol.toUpperCase()} 代理已设置: ${data.data.proxy}`, 'success');
        await refreshProxyStatus();
    } catch (err) {
        showMessage(`❌ 设置 ${protocol} 代理失败: ${err.message}`, 'error');
    } finally {
        setButtonState(btn, false);
    }
}

// --- 手动轮换代理 ---
async function handleRotateProxy(protocol) {
    const btn = $(`#rotate-${protocol}-btn`);
    try {
        setButtonState(btn, true);

        const data = await fetchData('/rotate_proxy', 'POST', { protocol });

        showMessage(`🔄 ${protocol.toUpperCase()} 代理已轮换: ${data.data.new_proxy}`, 'info');
        await refreshProxyStatus();
        await refreshRotationHistory();
    } catch (err) {
        showMessage(`❌ 轮换 ${protocol} 代理失败: ${err.message}`, 'error');
    } finally {
        setButtonState(btn, false);
    }
}

// --- 启动本地代理服务 ---
async function handleStartService(protocol) {
    const btn = $(`#start-${protocol}-service-btn`);
    try {
        setButtonState(btn, true, true);

        const data = await fetchData('/service/start', 'POST', { protocol });

        showMessage(data.message, 'success');
        await refreshServiceStatus();
    } catch (err) {
        showMessage(err.message, 'error');
    } finally {
        setButtonState(btn, false);
    }
}

// --- 停止本地代理服务 ---
async function handleStopService(protocol) {
    const btn = $(`#stop-${protocol}-service-btn`);
    try {
        setButtonState(btn, true, true);

        const data = await fetchData('/service/stop', 'POST', { protocol });

        showMessage(data.message, 'success');
        await refreshServiceStatus();
    } catch (err) {
        showMessage(err.message, 'error');
    } finally {
        setButtonState(btn, false);
    }
}

// --- 开始验证 ---
async function handleStartValidation() {
    const btn = $('#validate-btn');
    try {
        setButtonState(btn, true, true);

        const data = await fetchData('/validate', 'POST');

        showMessage('✅ 验证任务已启动', 'success');
        $('#validation-status').textContent = 'running';
        btn.disabled = true;
    } catch (err) {
        showMessage(`❌ 启动验证失败: ${err.message}`, 'error');
    } finally {
        setButtonState(btn, false);
    }
}

// ======================
// 🚀 初始化 & 绑定事件
// ======================

function initEventListeners() {
    // 获取并设置代理
    $('#fetch-http-btn').addEventListener('click', () => handleFetchAndSetProxy('http'));
    $('#fetch-socks5-btn').addEventListener('click', () => handleFetchAndSetProxy('socks5'));

    // 手动轮换
    $('#rotate-http-btn').addEventListener('click', () => handleRotateProxy('http'));
    $('#rotate-socks5-btn').addEventListener('click', () => handleRotateProxy('socks5'));

    // 启动/停止服务
    $('#start-http-service-btn').addEventListener('click', () => handleStartService('http'));
    $('#stop-http-service-btn').addEventListener('click', () => handleStopService('http'));
    $('#start-socks5-service-btn').addEventListener('click', () => handleStartService('socks5'));
    $('#stop-socks5-service-btn').addEventListener('click', () => handleStopService('socks5'));

    // 开始验证
    $('#validate-btn').addEventListener('click', handleStartValidation);

    // 刷新按钮
    $('#refresh-btn').addEventListener('click', () => {
        showMessage('🔄 正在刷新...', 'info');
        refreshAllData();
    });
}

function startAutoRefresh() {
    refreshAllData(); // 立即刷新一次
    autoRefreshTimer = setInterval(refreshAllData, REFRESH_INTERVAL);
}

function stopAutoRefresh() {
    if (autoRefreshTimer) {
        clearInterval(autoRefreshTimer);
        autoRefreshTimer = null;
    }
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
    // 保存按钮原始文本
    $$('.btn').forEach(btn => {
        btn.dataset.originalText = btn.innerHTML;
    });

    initEventListeners();
    startAutoRefresh();

    // 页面卸载时停止自动刷新
    window.addEventListener('beforeunload', stopAutoRefresh);
});
