// --- 全局变量 ---
let logFetchInterval;
let fetchStatusInterval;
let validateStatusInterval;
let serviceStatusInterval;
let rotationHistoryInterval;

const statusClasses = {
    'info': 'status-info',
    'success': 'status-success',
    'warning': 'status-warning',
    'error': 'status-error'
};

// --- DOM 元素 ---
let fetchButton, fetchStatusDiv, fetchProgressContainer, fetchProgressBar;
let validateButton, validateStatusDiv, validateProgressContainer, validateProgressBar, httpCountSpan, socks5CountSpan, validatedProxyTableBody;
let selectedHttpProxySelect, selectedSocks5ProxySelect, startServiceButton, stopServiceButton, serviceStatusDiv, currentHttpProxySpan, currentSocks5ProxySpan;
let rotateHttpButton, rotateSocks5Button, rotationIntervalInput, startAutoRotateButton, stopAutoRotateButton, rotationStatusDiv, rotationHistoryTableBody;
let rawProxiesPre, logsContainer, clearLogButton;

// --- 通用辅助函数 ---
function updateStatus(element, text, type = 'info') {
    element.textContent = text;
    element.className = 'status ' + (statusClasses[type] || statusClasses['info']);
}

function getLogEntryClass(logLine) {
    const levelMatch = logLine.match(/\[.*?\]\s+(\w+)/);
    if (levelMatch && levelMatch[1]) {
        const level = levelMatch[1].toUpperCase();
        if (level === 'WARNING') return 'log-warning';
        else if (level === 'ERROR' || level === 'CRITICAL') return 'log-error';
        else if (level === 'DEBUG') return 'log-debug';
    }
    return 'log-info';
}

async function apiCall(url, options = {}) {
    try {
        const response = await fetch(url, {
            headers: { 'Content-Type': 'application/json' },
            ...options
        });
        let data;
        const contentType = response.headers.get("content-type");
        if (contentType && contentType.indexOf("application/json") !== -1) {
            data = await response.json();
        } else {
            data = { message: await response.text() };
        }
        if (!response.ok) {
            throw new Error(data.error || data.message || `HTTP ${response.status}`);
        }
        return { ok: true, data };
    } catch (error) {
        console.error(`API 调用失败 ${url}:`, error);
        return { ok: false, error: error.message };
    }
}

// --- 1. 获取代理 ---
async function fetchProxies() {
    fetchButton.disabled = true;
    updateStatus(fetchStatusDiv, '状态: 正在请求启动获取任务...', 'info');
    fetchProgressContainer.style.display = 'block';
    fetchProgressBar.style.width = '10%';
    fetchProgressBar.textContent = '10%';

    const { ok, data, error } = await apiCall('/api/fetch_proxies', { method: 'POST' });

    if (ok) {
        if (data.status === 'started') {
            updateStatus(fetchStatusDiv, '状态: 获取任务已启动', 'success');
            fetchProgressBar.style.width = '30%';
            fetchProgressBar.textContent = '30%';
            startFetchStatusPolling();
        } else if (data.status === 'already_running') {
            updateStatus(fetchStatusDiv, '状态: 获取任务已在运行', 'warning');
            fetchButton.disabled = false;
            fetchProgressContainer.style.display = 'none';
        }
    } else {
        updateStatus(fetchStatusDiv, `状态: 启动获取任务失败 (${error})`, 'error');
        fetchButton.disabled = false;
        fetchProgressContainer.style.display = 'none';
    }
}

function startFetchStatusPolling() {
    fetchStatusInterval = setInterval(async () => {
        const { ok, data } = await apiCall('/api/fetch_status');
        if (ok) {
            if (data.is_running) {
                updateStatus(fetchStatusDiv, '状态: 获取任务正在运行...', 'info');
                // 进度模拟
                let currentWidth = parseInt(fetchProgressBar.style.width) || 30;
                if (currentWidth < 90) {
                    currentWidth += 5;
                    fetchProgressBar.style.width = currentWidth + '%';
                    fetchProgressBar.textContent = currentWidth + '%';
                }
            } else {
                clearInterval(fetchStatusInterval);
                fetchButton.disabled = false;
                fetchProgressContainer.style.display = 'none';
                if (data.last_result) {
                    updateStatus(fetchStatusDiv, '状态: 获取任务完成成功', 'success');
                } else {
                    updateStatus(fetchStatusDiv, '状态: 获取任务完成但失败', 'error');
                }
            }
        } else {
            // 如果查询失败，也停止轮询
            clearInterval(fetchStatusInterval);
            fetchButton.disabled = false;
            fetchProgressContainer.style.display = 'none';
            updateStatus(fetchStatusDiv, '状态: 查询获取任务状态失败', 'error');
        }
    }, 2000);
}

// --- 2. 验证代理 ---
async function validateProxies() {
    validateButton.disabled = true;
    updateStatus(validateStatusDiv, '状态: 正在请求启动验证任务...', 'info');
    validateProgressContainer.style.display = 'block';
    validateProgressBar.style.width = '0%';
    validateProgressBar.textContent = '0%';

    const { ok, data, error } = await apiCall('/api/validate_proxies', { method: 'POST' });

    if (ok) {
        if (data.status === 'started') {
            updateStatus(validateStatusDiv, '状态: 验证任务已启动', 'success');
            startValidateStatusPolling();
        } else if (data.status === 'already_running') {
            updateStatus(validateStatusDiv, '状态: 验证任务已在运行', 'warning');
            validateButton.disabled = false;
            validateProgressContainer.style.display = 'none';
        }
    } else {
        updateStatus(validateStatusDiv, `状态: 启动验证任务失败 (${error})`, 'error');
        validateButton.disabled = false;
        validateProgressContainer.style.display = 'none';
    }
}

function startValidateStatusPolling() {
    validateStatusInterval = setInterval(async () => {
        const { ok, data } = await apiCall('/api/validation_status');
        if (ok) {
            if (data.is_running) {
                updateStatus(validateStatusDiv, `状态: 验证任务正在运行... (${data.progress}%)`, 'info');
                validateProgressBar.style.width = data.progress + '%';
                validateProgressBar.textContent = data.progress + '%';
            } else {
                clearInterval(validateStatusInterval);
                validateButton.disabled = false;
                validateProgressContainer.style.display = 'none';
                if (data.last_result) {
                    updateStatus(validateStatusDiv, '状态: 验证任务完成成功', 'success');
                } else {
                    updateStatus(validateStatusDiv, '状态: 验证任务完成但失败', 'error');
                }
                // 验证完成后，刷新代理列表和下拉框
                loadValidatedProxies('all');
                populateProxySelectors();
            }
        } else {
            clearInterval(validateStatusInterval);
            validateButton.disabled = false;
            validateProgressContainer.style.display = 'none';
            updateStatus(validateStatusDiv, '状态: 查询验证任务状态失败', 'error');
        }
    }, 2000);
}

async function loadValidatedProxies(protocol = 'all') {
    const { ok, data } = await apiCall(`/api/validated_proxies?protocol=${protocol}`);
    if (ok) {
        validatedProxyTableBody.innerHTML = '';
        let httpCount = 0, socks5Count = 0;

        function populateTable(proxies, proto) {
            for (const [key, info] of Object.entries(proxies)) {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${proto.toUpperCase()}</td>
                    <td>${key}</td>
                    <td>${info.ping !== null ? info.ping : 'N/A'}</td>
                    <td>${info.speed_kbps !== null ? info.speed_kbps : 'N/A'}</td>
                    <td>
                        <button onclick="setProxyForService('${proto}', '${key}')" title="设为服务代理">设为代理</button>
                        <button onclick="rotateToProxy('${proto}', '${key}')" title="立即轮换到此代理">轮换</button>
                    </td>
                `;
                validatedProxyTableBody.appendChild(row);
                if(proto === 'http') httpCount++;
                if(proto === 'socks5') socks5Count++;
            }
        }

        if (protocol === 'all' || protocol === 'http') {
            populateTable(data.http || {}, 'http');
            httpCount = Object.keys(data.http || {}).length;
        }
        if (protocol === 'all' || protocol === 'socks5') {
            populateTable(data.socks5 || {}, 'socks5');
            socks5Count = Object.keys(data.socks5 || {}).length;
        }
        
        httpCountSpan.textContent = ` (${httpCount})`;
        socks5CountSpan.textContent = ` (${socks5Count})`;
    } else {
        alert(`加载已验证代理失败: ${data.error}`);
    }
}

// --- 3. 启动/停止本地服务 ---
async function startLocalService() {
    const httpProxy = selectedHttpProxySelect.value;
    const socks5Proxy = selectedSocks5ProxySelect.value;

    if (!httpProxy || !socks5Proxy) {
        alert('请先选择 HTTP 和 SOCKS5 代理。');
        return;
    }

    startServiceButton.disabled = true;
    updateStatus(serviceStatusDiv, '状态: 正在启动本地服务...', 'info');

    const { ok, data, error } = await apiCall('/api/start_local_service', {
        method: 'POST',
        body: JSON.stringify({ http_proxy: httpProxy, socks5_proxy: socks5Proxy })
    });

    if (ok) {
        updateStatus(serviceStatusDiv, '状态: ' + data.message, 'success');
        // 更新当前代理显示
        currentHttpProxySpan.textContent = httpProxy;
        currentSocks5ProxySpan.textContent = socks5Proxy;
        startServiceStatusPolling(); // 开始轮询服务状态
    } else {
        updateStatus(serviceStatusDiv, `状态: 启动服务失败 (${error})`, 'error');
        startServiceButton.disabled = false;
    }
}

async function stopLocalService() {
    stopServiceButton.disabled = true;
    updateStatus(serviceStatusDiv, '状态: 正在停止本地服务...', 'info');

    const { ok, data, error } = await apiCall('/api/stop_local_service', { method: 'POST' });

    if (ok) {
        updateStatus(serviceStatusDiv, '状态: ' + data.message, 'success');
        currentHttpProxySpan.textContent = '-';
        currentSocks5ProxySpan.textContent = '-';
        clearInterval(serviceStatusInterval);
        // 更新按钮状态
        startServiceButton.disabled = false;
        stopServiceButton.disabled = false;
    } else {
        updateStatus(serviceStatusDiv, `状态: 停止服务失败 (${error})`, 'error');
        stopServiceButton.disabled = false;
    }
}

function startServiceStatusPolling() {
     // 立即查询一次
     checkServiceStatus();
     serviceStatusInterval = setInterval(checkServiceStatus, 5000); // 每5秒检查一次
}

async function checkServiceStatus() {
    const { ok, data } = await apiCall('/api/service_status');
    if (ok) {
        // 状态已经在 status div 中显示，这里可以更新更详细的信息
        // 例如，如果服务意外停止，可以更新UI
         if (!data.http_running && !data.socks5_running) {
             // 服务已停止
             clearInterval(serviceStatusInterval);
             updateStatus(serviceStatusDiv, '状态: 服务已停止', 'info');
             startServiceButton.disabled = false;
             stopServiceButton.disabled = false;
         }
    }
}

async function populateProxySelectors() {
    const { ok, data } = await apiCall('/api/validated_proxies?protocol=all');
    if (ok) {
        selectedHttpProxySelect.innerHTML = '<option value="">-- 请选择 --</option>';
        selectedSocks5ProxySelect.innerHTML = '<option value="">-- 请选择 --</option>';
        
        for (const key of Object.keys(data.http || {})) {
            const opt = document.createElement('option');
            opt.value = key;
            opt.textContent = `${key} (Ping: ${(data.http[key].ping||'N/A')}ms, Speed: ${(data.http[key].speed_kbps||'N/A')}KB/s)`;
            selectedHttpProxySelect.appendChild(opt);
        }
        for (const key of Object.keys(data.socks5 || {})) {
            const opt = document.createElement('option');
            opt.value = key;
            opt.textContent = `${key} (Ping: ${(data.socks5[key].ping||'N/A')}ms, Speed: ${(data.socks5[key].speed_kbps||'N/A')}KB/s)`;
            selectedSocks5ProxySelect.appendChild(opt);
        }
    }
}

// --- 4. IP 轮换 ---
async function rotateProxy(protocol) {
    const button = protocol === 'http' ? rotateHttpButton : rotateSocks5Button;
    const originalText = button.textContent;
    button.disabled = true;
    button.textContent = '轮换中...';

    const { ok, data, error } = await apiCall('/api/rotate_proxy', {
        method: 'POST',
        body: JSON.stringify({ protocol: protocol })
    });

    if (ok) {
        // 更新UI
        if(protocol === 'http') {
            currentHttpProxySpan.textContent = data.new_proxy.url.split('://')[1]; // 去掉协议头
        } else {
            currentSocks5ProxySpan.textContent = data.new_proxy.url.split('://')[1];
        }
        updateStatus(rotationStatusDiv, `状态: ${protocol.toUpperCase()} IP 已轮换`, 'success');
        loadRotationHistory(); // 刷新历史
    } else {
        updateStatus(rotationStatusDiv, `状态: 轮换 ${protocol.toUpperCase()} IP 失败 (${error})`, 'error');
    }
    button.disabled = false;
    button.textContent = originalText;
}

async function setAutoRotation(enabled) {
    const interval = parseInt(rotationIntervalInput.value);
    if (isNaN(interval) || interval <= 0) {
        alert('请输入有效的轮换间隔（秒）。');
        return;
    }

    const button = enabled ? startAutoRotateButton : stopAutoRotateButton;
    button.disabled = true;

    const { ok, data, error } = await apiCall('/api/set_auto_rotation', {
        method: 'POST',
        body: JSON.stringify({ enabled: enabled, interval_seconds: interval })
    });

    if (ok) {
        updateStatus(rotationStatusDiv, '状态: ' + data.message, 'success');
        if (enabled) {
            startAutoRotateButton.disabled = true;
            stopAutoRotateButton.disabled = false;
        } else {
            startAutoRotateButton.disabled = false;
            stopAutoRotateButton.disabled = true;
        }
    } else {
        updateStatus(rotationStatusDiv, `状态: 设置自动轮换失败 (${error})`, 'error');
        button.disabled = false;
    }
}

async function loadRotationHistory() {
    const { ok, data } = await apiCall('/api/rotation_history');
    if (ok) {
        rotationHistoryTableBody.innerHTML = '';
        data.slice().reverse().forEach(entry => { // 最新的在前面
            const row = document.createElement('tr');
            const date = new Date(entry.timestamp * 1000).toLocaleString();
            row.innerHTML = `
                <td>${date}</td>
                <td>${entry.protocol.toUpperCase()}</td>
                <td>${entry.old_proxy || 'None'}</td>
                <td>${entry.new_proxy}</td>
            `;
            rotationHistoryTableBody.appendChild(row);
        });
    }
}

// --- 5. 原始代理列表 ---
async function loadRawProxies(protocol) {
    rawProxiesPre.textContent = '正在加载...';
    const { ok, data } = await apiCall(`/api/get_proxies/${protocol}`);
    if (ok) {
        rawProxiesPre.textContent = data.proxies.join('\n') || '代理列表为空';
    } else {
        rawProxiesPre.textContent = `加载失败: ${data.error}`;
    }
}

// --- 6. 日志 ---
async function fetchAndDisplayLogs() {
    const { ok, data } = await apiCall('/api/logs');
    if (ok) {
        const logs = data.logs || [];
        logsContainer.innerHTML = '';
        logs.forEach(logLine => {
            const logEntry = document.createElement('div');
            logEntry.className = `log-entry ${getLogEntryClass(logLine)}`;
            logEntry.textContent = logLine;
            logsContainer.appendChild(logEntry);
        });
        logsContainer.scrollTop = logsContainer.scrollHeight;
    } else {
        logsContainer.innerHTML = `<div class="log-entry log-error">获取日志失败</div>`;
    }
}

function startLogFetching() {
    fetchAndDisplayLogs();
    logFetchInterval = setInterval(fetchAndDisplayLogs, 3000);
}

function stopLogFetching() {
    if (logFetchInterval) {
        clearInterval(logFetchInterval);
        logFetchInterval = null;
    }
}

// --- 页面加载和事件绑定 ---
function initializeElements() {
    fetchButton = document.getElementById('fetchButton');
    fetchStatusDiv = document.getElementById('fetchStatus');
    fetchProgressContainer = document.getElementById('fetchProgressContainer');
    fetchProgressBar = document.getElementById('fetchProgressBar');

    validateButton = document.getElementById('validateButton');
    validateStatusDiv = document.getElementById('validateStatus');
    validateProgressContainer = document.getElementById('validateProgressContainer');
    validateProgressBar = document.getElementById('validateProgressBar');
    httpCountSpan = document.getElementById('httpCount');
    socks5CountSpan = document.getElementById('socks5Count');
    validatedProxyTableBody = document.querySelector('#validatedProxyTable tbody');

    selectedHttpProxySelect = document.getElementById('selectedHttpProxy');
    selectedSocks5ProxySelect = document.getElementById('selectedSocks5Proxy');
    startServiceButton = document.getElementById('startServiceButton');
    stopServiceButton = document.getElementById('stopServiceButton');
    serviceStatusDiv = document.getElementById('serviceStatus');
    currentHttpProxySpan = document.getElementById('currentHttpProxy');
    currentSocks5ProxySpan = document.getElementById('currentSocks5Proxy');

    rotateHttpButton = document.getElementById('rotateHttpButton');
    rotateSocks5Button = document.getElementById('rotateSocks5Button');
    rotationIntervalInput = document.getElementById('rotationInterval');
    startAutoRotateButton = document.getElementById('startAutoRotateButton');
    stopAutoRotateButton = document.getElementById('stopAutoRotateButton');
    rotationStatusDiv = document.getElementById('rotationStatus');
    rotationHistoryTableBody = document.querySelector('#rotationHistoryTable tbody');

    rawProxiesPre = document.getElementById('rawProxiesPre');
    logsContainer = document.getElementById('logsContainer');
    clearLogButton = document.getElementById('clearLogButton');
}

window.addEventListener('load', () => {
    initializeElements(); // 确保DOM元素在绑定事件前被获取

    startLogFetching();
    // 初始加载已验证代理和下拉框
    loadValidatedProxies('all');
    populateProxySelectors();
    loadRotationHistory();
    
    // 初始检查服务状态
    checkServiceStatus();

    // 按钮事件绑定
    fetchButton.addEventListener('click', fetchProxies);
    validateButton.addEventListener('click', validateProxies);
    startServiceButton.addEventListener('click', startLocalService);
    stopServiceButton.addEventListener('click', stopLocalService);
    rotateHttpButton.addEventListener('click', () => rotateProxy('http'));
    rotateSocks5Button.addEventListener('click', () => rotateProxy('socks5'));
    startAutoRotateButton.addEventListener('click', () => setAutoRotation(true));
    stopAutoRotateButton.addEventListener('click', () => setAutoRotation(false));
    clearLogButton.addEventListener('click', () => { logsContainer.innerHTML = '<div class="log-entry log-info">日志已清空。</div>'; });
});

window.addEventListener('beforeunload', () => {
    stopLogFetching();
    clearInterval(fetchStatusInterval);
    clearInterval(validateStatusInterval);
    clearInterval(serviceStatusInterval);
    clearInterval(rotationHistoryInterval);
});

// 公共函数，供表格按钮调用
window.setProxyForService = function(protocol, key) {
    if (protocol === 'http') {
        selectedHttpProxySelect.value = key;
    } else if (protocol === 'socks5') {
        selectedSocks5ProxySelect.value = key;
    }
};

window.rotateToProxy = async function(protocol, key) {
     // 这个功能需要后端支持直接切换到指定代理
     // 当前实现是手动轮换，无法精确控制
     // 作为一个变通，我们可以先设置为该代理，然后手动点击轮换按钮
     // 或者增强后端API
     alert(`此功能需要后端增强。当前请手动选择代理并点击"轮换 ${protocol.toUpperCase()} IP"按钮。`);
     window.setProxyForService(protocol, key);
};



