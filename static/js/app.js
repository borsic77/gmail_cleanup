document.addEventListener('DOMContentLoaded', () => {
    fetchAccountInfo();
    // Start polling sync status immediately in case it's running
    pollSyncStatus();
    fetchStats(); // Initial load from cache
});

let currentStats = [];
let syncInterval = null;

async function fetchAccountInfo() {
    try {
        const res = await fetch('/api/account');
        const data = await res.json();
        if (data.email_address) {
            document.getElementById('account-card').classList.remove('hidden');
            document.getElementById('acc-email').textContent = data.email_address;
            document.getElementById('acc-total').textContent = data.total_messages.toLocaleString();
            document.getElementById('acc-threads').textContent = data.threads_total.toLocaleString();
        }
    } catch(e) {
        console.error("Account fetch failed", e);
    }
}

async function startSync() {
    try {
        await fetch('/api/sync/start', { method: 'POST' });
        pollSyncStatus();
    } catch (e) { alert("Failed to start sync"); }
}

async function stopSync() {
    try {
        await fetch('/api/sync/stop', { method: 'POST' });
    } catch (e) { alert("Failed to stop sync"); }
}

function pollSyncStatus() {
    if (syncInterval) clearInterval(syncInterval);
    
    syncInterval = setInterval(async () => {
        try {
            const res = await fetch('/api/sync/status');
            const data = await res.json();
            
            const statusText = document.getElementById('sync-status-text');
            const pBar = document.getElementById('sync-progress');
            const startBtn = document.getElementById('start-sync-btn');
            const stopBtn = document.getElementById('stop-sync-btn');
            
            statusText.textContent = `${data.status} (${data.scanned_count}/${data.total_to_scan || '?'})`;
            
            // Calc percentage
            let pct = 0;
            if (data.total_to_scan > 0) {
                pct = (data.scanned_count / 50000) * 100; // Relative to max goal? or found?
                // Better: Relative to total_to_scan if known, else relative to max 50k
                if (data.total_to_scan < 50000) {
                     pct = (data.scanned_count / data.total_to_scan) * 100;
                } else {
                     pct = (data.scanned_count / 50000) * 100;
                }
            }
            pBar.style.width = `${Math.min(pct, 100)}%`;
            
            if (data.is_running) {
                startBtn.classList.add('hidden');
                stopBtn.classList.remove('hidden');
            } else {
                startBtn.classList.remove('hidden');
                stopBtn.classList.add('hidden');
                
                // If just finished, refresh stats once
                if (data.status === 'Complete' && !statusText.dataset.refreshed) {
                    fetchStats();
                    statusText.dataset.refreshed = "true";
                }
            }
            
        } catch (e) {
            console.error("Poll failed", e);
        }
    }, 1000);
}

async function fetchStats() {
    const dashboard = document.getElementById('dashboard-content');
    dashboard.innerHTML = '<div class="flex justify-center items-center h-64"><div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div></div>';

    const beforeDate = document.getElementById('before-date').value;
    const category = document.getElementById('category-filter').value;
    
    let url = '/api/stats?max_results=2000'; 
    if (beforeDate) {
        url += `&before=${beforeDate}`;
    }
    if (category && category !== 'all') {
        url += `&category=${category}`;
    }

    try {
        const response = await fetch(url);
        const data = await response.json();
        
        if (data.error) {
            dashboard.innerHTML = `<div class="text-red-500 text-center">${data.error}</div>`;
            return;
        }

        currentStats = data.stats;
        // Reset selection
        selectedSenders = new Set();
        updateDeleteSelectedBtn();
        
        renderDashboard(data.stats);
        renderMetadata(data.meta);
    } catch (e) {
        dashboard.innerHTML = `<div class="text-red-500 text-center">Failed to load data. Please try again.</div>`;
    }
}

function renderMetadata(meta) {
    const metaDiv = document.getElementById('stats-metadata');
    if (meta && meta.total_scanned > 0) {
        document.getElementById('total-scanned').textContent = meta.total_scanned;
        document.getElementById('oldest-date').textContent = meta.oldest_date;
        metaDiv.classList.remove('hidden');
    } else {
        metaDiv.classList.add('hidden');
    }
}

async function refreshCache() {
    if (!confirm("Are you sure? This will delete the local cache and re-download headers from Gmail.")) return;
    
    try {
        await fetch('/api/cache/clear', { method: 'POST' });
        fetchStats();
    } catch (e) {
        alert("Failed to clear cache.");
    }
}

function renderDashboard(stats) {
    const dashboard = document.getElementById('dashboard-content');
    
    if (stats.length === 0) {
        dashboard.innerHTML = '<div class="text-gray-500 text-center p-8">No emails found matching criteria.</div>';
        return;
    }

    let html = `
        <div class="bg-white shadow overflow-hidden sm:rounded-lg">
            <div class="px-4 py-5 sm:px-6 flex justify-between items-center">
                <h3 class="text-lg leading-6 font-medium text-gray-900">Top Senders</h3>
                <span class="text-sm text-gray-500">Sorted by count</span>
            </div>
            <ul class="divide-y divide-gray-200">
    `;

    stats.forEach((sender, index) => {
        html += `
            <li class="px-4 py-4 sm:px-6 hover:bg-gray-50 transition duration-150 ease-in-out">
                <div class="flex items-center">
                    <div class="mr-4">
                        <input type="checkbox" onchange="toggleSender('${sender.email}')" class="sender-checkbox h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded">
                    </div>
                    <div class="flex-1 min-w-0">
                        <div class="flex items-center mb-1">
                            <p class="text-sm font-medium text-blue-600 truncate mr-2" title="${sender.email}">${sender.name}</p>
                            <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800">
                                ${sender.count} emails
                            </span>
                        </div>
                        <div class="flex text-sm text-gray-500">
                            <p class="truncate">${sender.email}</p>
                             <span class="ml-2 text-xs text-gray-400">Latest: ${new Date(sender.last_date).toLocaleDateString()}</span>
                        </div>
                    </div>
                    <div class="ml-4 flex-shrink-0 flex items-center space-x-4">
                        <button onclick="confirmDelete('${sender.email}')" class="inline-flex items-center px-3 py-2 border border-transparent text-sm leading-4 font-medium rounded-md text-red-700 bg-red-100 hover:bg-red-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500">
                            Delete
                        </button>
                    </div>
                </div>
            </li>
        `;
    });

    html += `</ul></div>`;
    dashboard.innerHTML = html;
}

// Keep track of selected emails
let selectedSenders = new Set();

function toggleSender(email) {
    if (selectedSenders.has(email)) {
        selectedSenders.delete(email);
    } else {
        selectedSenders.add(email);
    }
    updateDeleteSelectedBtn();
}

function updateDeleteSelectedBtn() {
    const btn = document.getElementById('delete-selected-btn');
    if (selectedSenders.size > 0) {
        btn.classList.remove('hidden');
        btn.textContent = `Delete Selected (${selectedSenders.size})`;
    } else {
        btn.classList.add('hidden');
    }
}

function confirmDelete(email) {
    const sender = currentStats.find(s => s.email === email);
    if (!sender) return;

    const modal = document.getElementById('delete-modal');
    
    document.getElementById('delete-count').textContent = sender.count;
    document.getElementById('delete-sender').textContent = email;
    
    // Store IDs to delete on the confirm button
    const confirmBtn = document.getElementById('confirm-delete-btn');
    confirmBtn.onclick = () => executeDelete(sender.ids);
    
    modal.classList.remove('hidden');
}

function confirmDeleteSelected() {
    if (selectedSenders.size === 0) return;

    let totalEmails = 0;
    let allIds = [];
    
    selectedSenders.forEach(email => {
        const sender = currentStats.find(s => s.email === email);
        if (sender) {
            totalEmails += sender.count;
            allIds = allIds.concat(sender.ids);
        }
    });

    const modal = document.getElementById('delete-modal');
    document.getElementById('delete-count').textContent = totalEmails;
    document.getElementById('delete-sender').textContent = `${selectedSenders.size} selected senders`;
    
    const confirmBtn = document.getElementById('confirm-delete-btn');
    confirmBtn.onclick = () => executeDelete(allIds);
    
    modal.classList.remove('hidden');
}

function closeModal() {
    document.getElementById('delete-modal').classList.add('hidden');
}

async function executeDelete(ids) {
    const confirmBtn = document.getElementById('confirm-delete-btn');
    const originalText = confirmBtn.textContent;
    confirmBtn.textContent = 'Deleting...';
    confirmBtn.disabled = true;

    try {
        const response = await fetch('/api/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ids: ids })
        });
        
        const result = await response.json();
        
        closeModal();
        // Refresh stats
        fetchStats();
        
        // Show success notification (could be better)
        alert(`Successfully deleted ${result.deleted} emails.`);
        
    } catch (e) {
        alert('Failed to delete emails.');
    } finally {
        confirmBtn.textContent = originalText;
        confirmBtn.disabled = false;
    }
}
