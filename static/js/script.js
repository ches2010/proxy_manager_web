$(document).ready(function() {
    let autoRefreshInterval;
    let logRefreshInterval;
    let proxyRefreshInterval;

    // 初始化设置表单
    loadSettings();

    // --- 事件绑定 ---
    $('#startFetchBtn').on('click', startFetchTask);
    $('#cancelTaskBtn').on('click', cancelCurrentTask);
    $('#clearProxiesBtn').on('click', clearAllProxies);
    $('#toggleServerBtn').on('click', toggleProxyServer);
    $('#rotateProxyBtn').on('click', rotateProxy);
    $('#exportProxiesBtn').on('click', exportProxies);
    $('#saveSettingsBtn').on('click', saveSettings);
    $('#saveAndSearchBtn').on('click', saveAndSearch);
    $('#copyCurrentProxyBtn').on('click', copyCurrentProxyToClipboard);

    // 表头排序
    $('#proxyTable thead th[data-sort]').on('click', function() {
        const sortKey = $(this).data('sort');
        let isAsc = $(this).hasClass('sorted-asc');
        // 移除所有排序类
        $('#proxyTable thead th').removeClass('sorted-asc sorted-desc');
        // 添加当前排序类
        if (isAsc) {
            $(this).addClass('sorted-desc');
            isAsc = false;
        } else {
            $(this).addClass('sorted-asc');
            isAsc = true;
        }
        loadProxies(sortKey, !isAsc); // reverse = !isAsc 因为后端默认可能是降序
    });

    // 启动定时刷新
    startAutoRefresh();

    // --- 函数定义 ---
    function startAutoRefresh() {
        // 每2秒刷新一次状态和日志
        logRefreshInterval = setInterval(updateLogs, 2000);
        // 每5秒刷新一次代理列表和状态
        proxyRefreshInterval = setInterval(function() {
            updateStatus();
            loadProxies(); // 不带参数使用默认排序
        }, 5000);
        // 页面加载时立即获取一次
        updateStatus();
        updateLogs();
        loadProxies();
    }

    function updateStatus() {
        $.get('/api/status', function(data) {
            // 更新按钮状态
            if (data.is_running_task) {
                $('#startFetchBtn').prop('disabled', true);
                $('#cancelTaskBtn').prop('disabled', false);
                $('#taskStatus').removeClass('bg-secondary bg-success').addClass('bg-warning').text('运行中');
            } else {
                $('#startFetchBtn').prop('disabled', false);
                $('#cancelTaskBtn').prop('disabled', true);
                $('#taskStatus').removeClass('bg-warning bg-success').addClass('bg-secondary').text('空闲');
            }

            if (data.is_server_running) {
                $('#toggleServerBtn').text('停止服务').prop('disabled', false);
                $('#serverStatus').removeClass('bg-secondary').addClass('bg-success').text('服务运行中');
                $('#rotateProxyBtn').prop('disabled', false);
                $('#autoRotateCheck').prop('disabled', false);
            } else {
                $('#toggleServerBtn').text('启动服务').prop('disabled', false);
                $('#serverStatus').removeClass('bg-success').addClass('bg-secondary').text('服务未启动');
                $('#rotateProxyBtn').prop('disabled', true);
                $('#autoRotateCheck').prop('disabled', true).prop('checked', false);
            }

            $('#currentProxyInput').val(data.current_proxy);
            $('#proxyCountBadge').text(data.proxy_count + ' 个');
        }).fail(function() {
            console.log('Failed to fetch status');
        });
    }

    function updateLogs() {
        $.get('/api/logs', function(data) {
            if (data.logs && data.logs.length > 0) {
                const logArea = $('#logArea');
                data.logs.forEach(log => {
                    logArea.append(log + '\n');
                });
                // 滚动到底部
                logArea.scrollTop(logArea[0].scrollHeight);
            }
        });
    }

    function loadProxies(sortBy = 'score', reverse = true) {
        let url = `/api/proxies?sort_by=${sortBy}&reverse=${reverse}`;
        $.get(url, function(data) {
            const tbody = $('#proxyTable tbody');
            tbody.empty(); // 清空现有数据

            if (!data.proxies || data.proxies.length === 0) {
                tbody.append('<tr id="noDataPlaceholder"><td colspan="7" class="text-center">暂无代理数据</td></tr>');
                $('#exportProxiesBtn').prop('disabled', true);
                return;
            }

            $('#exportProxiesBtn').prop('disabled', false);
            data.proxies.forEach(proxy => {
                const row = `
                    <tr data-proxy="${proxy.proxy}">
                        <td>${proxy.score || 'N/A'}</td>
                        <td>${proxy.anonymity || 'N/A'}</td>
                        <td>${proxy.protocol || 'N/A'}</td>
                        <td>${proxy.proxy || 'N/A'}</td>
                        <td>${proxy.delay || 'N/A'}</td>
                        <td>${proxy.speed || 'N/A'}</td>
                        <td>${proxy.region || 'N/A'}</td>
                    </tr>
                `;
                tbody.append(row);
            });

            // 为新行绑定双击复制事件
            $('#proxyTable tbody tr').off('dblclick').on('dblclick', function() {
                const proxyAddress = $(this).data('proxy');
                if (proxyAddress) {
                    navigator.clipboard.writeText(proxyAddress).then(() => {
                        alert(`已复制: ${proxyAddress}`);
                    }).catch(err => {
                        console.error('复制失败: ', err);
                    });
                }
            });
        }).fail(function() {
            console.log('Failed to load proxies');
        });
    }

    function startFetchTask() {
        $.post('/api/start_fetch', function(response) {
            if (response.status === 'success') {
                alert(response.message);
            } else {
                alert('错误: ' + response.message);
            }
        });
    }

    function cancelCurrentTask() {
        $.post('/api/cancel_task', function(response) {
            if (response.status === 'success') {
                alert(response.message);
            } else {
                alert('错误: ' + response.message);
            }
        });
    }

    function clearAllProxies() {
        if (confirm('确定要清空所有代理吗？')) {
            $.post('/api/clear_proxies', function(response) {
                if (response.status === 'success') {
                    alert(response.message);
                    loadProxies(); // 刷新列表
                } else {
                    alert('错误: ' + response.message);
                }
            });
        }
    }

    function toggleProxyServer() {
        const action = $('#toggleServerBtn').text().includes('启动') ? '/api/start_server' : '/api/stop_server';
        $.post(action, function(response) {
            if (response.status === 'success') {
                alert(response.message);
                updateStatus(); // 立即更新状态
            } else {
                alert('错误: ' + response.message);
            }
        });
    }

    function rotateProxy() {
        $.post('/api/rotate_proxy', function(response) {
            if (response.status === 'success') {
                // 状态会在定时刷新中更新
                console.log(response.message);
            } else {
                alert('错误: ' + response.message);
            }
        });
    }

    function exportProxies() {
        window.location.href = '/api/export_proxies';
    }

    function copyCurrentProxyToClipboard() {
        const currentProxy = $('#currentProxyInput').val();
        if (currentProxy && currentProxy !== 'N/A') {
            navigator.clipboard.writeText(currentProxy).then(() => {
                alert(`当前代理已复制: ${currentProxy}`);
            }).catch(err => {
                console.error('复制失败: ', err);
            });
        } else {
            alert('没有可复制的当前代理');
        }
    }

    function loadSettings() {
        $.get('/api/settings', function(data) {
            // 通用设置
            const general = data.general || {};
            $('#validationThreads').val(general.validation_threads || 100);
            $('#failureThreshold').val(general.failure_threshold || 3);
            $('#autoRetestEnabled').prop('checked', general.auto_retest_enabled || false);
            $('#autoRetestInterval').val(general.auto_retest_interval || 10);

            // FOFA设置
            const fofa = data.auto_fetch?.fofa || {};
            $('#fofaEnabled').prop('checked', fofa.enabled || true);
            $('#fofaSize').val(fofa.size || 500);
            $('#fofaKey').val(fofa.key || '');
            $('#fofaQuery').val(fofa.query || 'protocol=="socks5" && country=="CN" && banner="Method:No"');

            // Hunter设置
            const hunter = data.auto_fetch?.hunter || {};
            $('#hunterEnabled').prop('checked', hunter.enabled || false);
            $('#hunterSize').val(hunter.size || 100);
            $('#hunterKey').val(hunter.key || '');
            $('#hunterQuery').val(hunter.query || 'app.name="SOCKS5"');
        });
    }

    function collectSettings() {
        return {
            'general': {
                'validation_threads': parseInt($('#validationThreads').val()),
                'failure_threshold': parseInt($('#failureThreshold').val()),
                'auto_retest_enabled': $('#autoRetestEnabled').is(':checked'),
                'auto_retest_interval': parseInt($('#autoRetestInterval').val())
            },
            'auto_fetch': {
                'fofa': {
                    'enabled': $('#fofaEnabled').is(':checked'),
                    'key': $('#fofaKey').val().trim(),
                    'query': $('#fofaQuery').val().trim(),
                    'size': parseInt($('#fofaSize').val())
                },
                'hunter': {
                    'enabled': $('#hunterEnabled').is(':checked'),
                    'key': $('#hunterKey').val().trim(),
                    'query': $('#hunterQuery').val().trim(),
                    'size': parseInt($('#hunterSize').val())
                }
            }
        };
    }

    function saveSettings() {
        const settings = collectSettings();
        $.ajax({
            url: '/api/settings',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify(settings),
            success: function(response) {
                if (response.status === 'success') {
                    alert('设置已保存');
                    $('#settingsModal').modal('hide');
                } else {
                    alert('保存失败: ' + response.message);
                }
            },
            error: function() {
                alert('保存设置时发生网络错误');
            }
        });
    }

    function saveAndSearch() {
        saveSettings(); // 保存后，模态框会关闭
        // 这里可以添加一个模拟的“开始搜索”调用
        alert('设置已保存。搜索功能将在后续版本实现。');
        // $.post('/api/start_auto_search', ...); // 需要在后端实现此API
    }

    // 页面卸载时清理定时器
    $(window).on('beforeunload', function() {
        if (logRefreshInterval) clearInterval(logRefreshInterval);
        if (proxyRefreshInterval) clearInterval(proxyRefreshInterval);
    });
});
