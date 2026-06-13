/**
 * WhatsApp + Gmail Agent Dashboard
 */

class Dashboard {
    constructor() {
        this.apiBase = '/api';
        this.syncInterval = 60000; // 1 minute
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.loadDashboardData();
        this.startAutoRefresh();
    }

    setupEventListeners() {
        const syncBtn = document.getElementById('syncBtn');
        if (syncBtn) {
            syncBtn.addEventListener('click', () => this.triggerSync());
        }
    }

    async loadDashboardData() {
        try {
            const response = await fetch(`${this.apiBase}/dashboard-data`);
            const data = await response.json();

            this.updateStatistics(data);
            this.updateMessages(data.recent_messages);
            this.updateTasks(data.open_tasks);
            this.updateAnalytics(data.analytics);
            this.updateTimestamp();

        } catch (error) {
            console.error('Error loading dashboard data:', error);
        }
    }

    updateStatistics(data) {
        // Count messages by platform
        const waMessages = data.recent_messages.filter(m => m.platform === 'whatsapp').length;
        const gmailMessages = data.recent_messages.filter(m => m.platform === 'gmail').length;

        document.getElementById('waMessageCount').textContent = waMessages;
        document.getElementById('gmailMessageCount').textContent = gmailMessages;
        document.getElementById('openTaskCount').textContent = data.open_tasks.length;
        document.getElementById('linkedTaskCount').textContent = '0'; // TODO: Calculate from DB
    }

    updateMessages(messages) {
        const container = document.getElementById('messagesList');

        if (!messages || messages.length === 0) {
            container.innerHTML = '<div class="empty-state">אין הודעות חדשות</div>';
            return;
        }

        const html = messages.slice(0, 10).map(msg => `
            <div class="message-item">
                <div class="message-sender">
                    📱 ${msg.platform === 'whatsapp' ? 'WhatsApp' : 'Gmail'} - ${msg.sender}
                </div>
                <div class="message-content">${this.escapeHtml(msg.content.substring(0, 150))}</div>
                <div class="message-time">${this.formatTime(msg.timestamp)}</div>
            </div>
        `).join('');

        container.innerHTML = html;
    }

    updateTasks(tasks) {
        const container = document.getElementById('tasksList');

        if (!tasks || tasks.length === 0) {
            container.innerHTML = '<div class="empty-state">אין משימות פתוחות 🎉</div>';
            return;
        }

        const html = tasks.slice(0, 15).map(task => `
            <div class="task-item">
                <div class="task-title">${this.escapeHtml(task.title)}</div>
                <div>
                    <span class="task-priority priority-${task.priority}">
                        ${this.getPriorityLabel(task.priority)}
                    </span>
                    <span class="task-status status-${task.status}">
                        ${this.getStatusLabel(task.status)}
                    </span>
                </div>
                <div style="margin-top: 8px; color: #999; font-size: 0.9em;">
                    ${task.platform === 'whatsapp' ? '📱 WhatsApp' : '📧 Gmail'}
                </div>
            </div>
        `).join('');

        container.innerHTML = html;
    }

    updateAnalytics(analytics) {
        const container = document.getElementById('analyticsList');

        const html = `
            <div class="analytics-item">
                <div class="analytics-label">סך הודעות</div>
                <div class="analytics-value">${analytics.total_messages}</div>
            </div>
            <div class="analytics-item">
                <div class="analytics-label">משימות פתוחות</div>
                <div class="analytics-value">${analytics.open_tasks}</div>
            </div>
            <div class="analytics-item">
                <div class="analytics-label">משימות דחופות</div>
                <div class="analytics-value">${analytics.high_priority_tasks}</div>
            </div>
            <div class="analytics-item">
                <div class="analytics-label">זמן מענה ממוצע</div>
                <div class="analytics-value">${analytics.avg_response_time_minutes.toFixed(1)}</div>
            </div>
            <div class="analytics-item">
                <div class="analytics-label">WhatsApp הודעות</div>
                <div class="analytics-value">${analytics.messages_by_platform.whatsapp}</div>
            </div>
            <div class="analytics-item">
                <div class="analytics-label">Gmail הודעות</div>
                <div class="analytics-value">${analytics.messages_by_platform.gmail}</div>
            </div>
        `;

        container.innerHTML = html;
    }

    async triggerSync() {
        const btn = document.getElementById('syncBtn');
        const statusEl = document.getElementById('syncStatus');

        btn.disabled = true;
        statusEl.className = 'status-message loading';
        statusEl.textContent = '🔄 סנכרון בעתיד...';

        try {
            const response = await fetch(`${this.apiBase}/sync-now`, {
                method: 'POST'
            });

            const data = await response.json();

            if (data.status === 'success') {
                statusEl.className = 'status-message success';
                statusEl.textContent = '✓ סנכרון הצליח! ' + (data.result.summary ? data.result.summary.substring(0, 100) : '');

                // Reload dashboard after sync
                setTimeout(() => this.loadDashboardData(), 1000);
            } else {
                statusEl.className = 'status-message error';
                statusEl.textContent = '❌ שגיאה בסנכרון: ' + data.message;
            }

        } catch (error) {
            statusEl.className = 'status-message error';
            statusEl.textContent = '❌ שגיאה בחיבור: ' + error.message;
        } finally {
            btn.disabled = false;
        }
    }

    updateTimestamp() {
        const lastUpdate = document.getElementById('lastUpdate');
        const now = new Date();
        lastUpdate.textContent = now.toLocaleString('he-IL');
    }

    startAutoRefresh() {
        setInterval(() => this.loadDashboardData(), this.syncInterval);
    }

    formatTime(timestamp) {
        if (!timestamp) return '-';
        try {
            const date = new Date(timestamp);
            return date.toLocaleString('he-IL');
        } catch {
            return timestamp;
        }
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    getPriorityLabel(priority) {
        const labels = {
            'urgent': '🔴 דחוף',
            'high': '🟠 חשוב',
            'normal': '🟡 רגיל',
            'low': '🟢 נמוך'
        };
        return labels[priority] || priority;
    }

    getStatusLabel(status) {
        const labels = {
            'open': '📖 פתוח',
            'in_progress': '⏳ בעבודה',
            'completed': '✅ הושלם'
        };
        return labels[status] || status;
    }
}

// Initialize dashboard when page loads
document.addEventListener('DOMContentLoaded', () => {
    new Dashboard();
});
