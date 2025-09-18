// script.js

// 假设 API 端点
const FETCH_STATUS_API = '/api/fetch_status';
const LOGS_API = '/api/logs';

// 获取 DOM 元素
const fetchButton = document.getElementById('fetchButton');
const logDisplay = document.getElementById('logDisplay');
const statusDisplay = document.getElementById('statusDisplay');

// 轮询状态标志
let isFetching = false;

// 轮询间隔 (毫秒)
const POLLING_INTERVAL = 2000;

let pollIntervalId = null;

// 映射后端状态到前端 CSS 类和显示文本
function mapStatus(fetchStatusData) {
    if (fetchStatusData.is_fetching) {
        // 如果仍在抓取，根据 sources 的状态判断是进行中还是部分失败
        const sources = fetchStatusData.sources || {};
        let hasFailure = false;
        let hasSuccess = false;

        for (let source in sources) {
            if (sources[source] === false) {
                hasFailure = true;
            } else if (sources[source] === true) {
                hasSuccess = true;
            }
            // 如果是 null 或 undefined，表示尚未处理或进行中，不改变 hasFailure/hasSuccess
        }

        if (hasFailure && hasSuccess) {
            return { cssClass: 'status-partial-failure', text: '部分失败' };
        } else if (hasFailure && !hasSuccess) {
            // 理论上如果 is_fetching 为 true，不太可能所有都失败就立即结束
            // 但根据逻辑，我们还是区分一下
            return { cssClass: 'status-updating', text: '正在进行中' };
        } else {
            return { cssClass: 'status-updating', text: '正在进行中' };
        }
    } else {
        // 如果抓取已停止
        if (fetchStatusData.success === true) {
             // 检查是否有任何源失败
            const sources = fetchStatusData.sources || {};
            let hasFailure = false;
            for (let source in sources) {
                if (sources[source] === false) {
                    hasFailure = true;
                    break;
                }
            }
            if(hasFailure) {
                 return { cssClass: 'status-partial-failure', text: '部分失败' };
            }
            return { cssClass: 'status-success', text: '已完成且成功' };
        } else if (fetchStatusData.success === false) {
            return { cssClass: 'status-failure', text: '已完成且失败' };
        } else {
            // success 为 null 或 undefined，理论上不太可能在 is_fetching false 时出现
            // 但为了健壮性，可以视为未知错误
            return { cssClass: 'status-failure', text: '未知错误' };
        }
    }
}


// 获取并更新日志
async function fetchLogs() {
    try {
        const response = await fetch(LOGS_API);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const logs = await response.text();
        logDisplay.textContent = logs;
        // 滚动到底部
        logDisplay.scrollTop = logDisplay.scrollHeight;
    } catch (error) {
        console.error('获取日志失败:', error);
        logDisplay.textContent = `获取日志失败: ${error.message}\n${logDisplay.textContent}`;
    }
}

// 获取并更新状态及控制轮询
async function fetchStatusAndControlPolling() {
    try {
        const response = await fetch(FETCH_STATUS_API);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const fetchStatusData = await response.json();

        // --- 状态显示逻辑 ---
        const statusInfo = mapStatus(fetchStatusData);
        statusDisplay.textContent = statusInfo.text;
        // 清除旧的类
        statusDisplay.classList.remove('status-updating', 'status-success', 'status-failure', 'status-partial-failure');
        // 添加新的类
        statusDisplay.classList.add(statusInfo.cssClass);

        // --- 轮询控制逻辑 ---
        if (isFetching) { // 只有在用户触发了获取操作后才考虑停止轮询
            if (fetchStatusData.is_fetching === false) {
                console.log("后端任务已完成，停止轮询。");
                stopPolling();
                fetchButton.disabled = false; // 重新启用按钮
                isFetching = false; // 重置标志位
            }
            // 如果 is_fetching 仍然是 true，则继续轮询，无需操作
        }


    } catch (error) {
        console.error('获取状态失败:', error);
        statusDisplay.textContent = `获取状态失败: ${error.message}`;
        statusDisplay.classList.remove('status-updating', 'status-success', 'status-failure', 'status-partial-failure');
        statusDisplay.classList.add('status-failure');
         if (isFetching) {
             stopPolling(); // 出错时也停止轮询
             fetchButton.disabled = false;
             isFetching = false;
         }
    }
}

// 启动轮询
function startPolling() {
    console.log("启动轮询...");
    // 立即执行一次，然后开始定时轮询
    fetchLogs();
    fetchStatusAndControlPolling();

    pollIntervalId = setInterval(() => {
        fetchLogs();
        fetchStatusAndControlPolling();
    }, POLLING_INTERVAL);
}

// 停止轮询
function stopPolling() {
    console.log("停止轮询。");
    if (pollIntervalId) {
        clearInterval(pollIntervalId);
        pollIntervalId = null;
    }
}

// 按钮点击事件处理器
fetchButton.addEventListener('click', async () => {
    if (isFetching) {
        console.log("获取代理操作已在进行中...");
        return; // 防止重复点击
    }

    isFetching = true;
    fetchButton.disabled = true; // 禁用按钮
    statusDisplay.textContent = '启动中...';
    statusDisplay.classList.remove('status-updating', 'status-success', 'status-failure', 'status-partial-failure');
    statusDisplay.classList.add('status-updating');
    logDisplay.textContent = '开始获取代理...\n';

    try {
        // 触发后端获取代理的操作
        const response = await fetch('/api/fetch_proxies', { method: 'POST' });
        if (!response.ok) {
            throw new Error(`启动失败: HTTP ${response.status}`);
        }
        console.log("已发送获取代理请求。");
        // 启动轮询
        startPolling();

    } catch (error) {
        console.error('发送获取代理请求失败:', error);
        statusDisplay.textContent = `启动失败: ${error.message}`;
        statusDisplay.classList.remove('status-updating', 'status-success', 'status-failure', 'status-partial-failure');
        statusDisplay.classList.add('status-failure');
        logDisplay.textContent = `启动失败: ${error.message}\n${logDisplay.textContent}`;
        fetchButton.disabled = false; // 失败时重新启用按钮
        isFetching = false; // 重置标志位
    }
});

// 页面加载完成后，尝试获取一次初始状态和日志
window.addEventListener('DOMContentLoaded', () => {
    console.log("页面加载完成，尝试获取初始状态和日志。");
    fetchLogs();
    fetchStatusAndControlPolling();
});



