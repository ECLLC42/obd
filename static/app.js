// Advanced OBD Diagnostic System - Frontend Application
class OBDDiagnosticApp {
    constructor() {
        this.ws = null;
        this.serialConnected = false;
        this.autoRefreshInterval = 1000;
        this.maxDataPoints = 100;
        this.autoScroll = true;
        this.soundNotifications = false;
        this.dataBuffer = [];
        this.charts = {};
        
        this.initializeApp();
    }

    initializeApp() {
        this.setupWebSocket();
        this.setupEventListeners();
        this.initializeTabs();
        this.refreshPorts();
        this.updateStatus();
        this.initializeCharts();
    }

    setupWebSocket() {
        const wsProtocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
        this.ws = new WebSocket(`${wsProtocol}://${window.location.host}/ws`);
        
        this.ws.onopen = () => {
            this.updateConnectionStatus(true);
            this.addTerminalLine('WebSocket connected', 'system');
        };
        
        this.ws.onmessage = (event) => {
            this.handleWebSocketMessage(event.data);
        };
        
        this.ws.onclose = () => {
            this.updateConnectionStatus(false);
            this.addTerminalLine('WebSocket disconnected', 'error');
            // Attempt to reconnect after 3 seconds
            setTimeout(() => this.setupWebSocket(), 3000);
        };
        
        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            this.addTerminalLine('WebSocket error occurred', 'error');
        };
    }

    handleWebSocketMessage(data) {
        try {
            const message = JSON.parse(data);
            
            switch (message.type) {
                case 'serial_data':
                    this.handleSerialData(message.data);
                    break;
                case 'chat_response':
                    this.addChatMessage(message.message, 'assistant');
                    break;
                case 'serial_response':
                    this.addTerminalLine(message.message, 'system');
                    break;
                case 'error':
                    this.addTerminalLine(message.message, 'error');
                    break;
                case 'pong':
                    // Handle ping response
                    break;
                default:
                    console.log('Unknown message type:', message.type);
            }
        } catch (e) {
            // Handle plain text messages (backwards compatibility)
            this.addChatMessage(data, 'assistant');
        }
    }

    handleSerialData(data) {
        this.dataBuffer.push(data);
        
        // Keep only the last maxDataPoints
        if (this.dataBuffer.length > this.maxDataPoints) {
            this.dataBuffer.shift();
        }
        
        // Update various UI elements
        this.updateRecentDataList();
        this.updateDataStats();
        this.updateRealtimeChart();
        this.addTerminalLine(`${data.timestamp}: ${data.data}`, 'output');
        
        // Play sound notification if enabled
        if (this.soundNotifications) {
            this.playNotificationSound();
        }
    }

    setupEventListeners() {
        // Serial connection controls
        document.getElementById('connectBtn').addEventListener('click', () => this.connectSerial());
        document.getElementById('disconnectBtn').addEventListener('click', () => this.disconnectSerial());
        document.getElementById('refreshPorts').addEventListener('click', () => this.refreshPorts());
        
        // Serial command input
        document.getElementById('sendCommand').addEventListener('click', () => this.sendSerialCommand());
        document.getElementById('serialInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                this.sendSerialCommand();
            }
        });
        
        // Quick command buttons
        document.querySelectorAll('.btn-command').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const command = e.target.getAttribute('data-command');
                this.sendSerialCommand(command);
            });
        });
        
        // Chat functionality
        document.getElementById('sendChat').addEventListener('click', () => this.sendChatMessage());
        document.getElementById('chatInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendChatMessage();
            }
        });
        
        // Data controls
        document.getElementById('exportBtn').addEventListener('click', () => this.exportData());
        document.getElementById('clearBtn').addEventListener('click', () => this.clearData());
        
        // Terminal controls
        document.getElementById('clearTerminal').addEventListener('click', () => this.clearTerminal());
        
        // Analysis controls
        document.getElementById('refreshChart').addEventListener('click', () => this.refreshAnalysisChart());
        document.getElementById('chartType').addEventListener('change', () => this.refreshAnalysisChart());
        
        // Settings
        document.getElementById('settingsBtn').addEventListener('click', () => this.showSettings());
        document.getElementById('closeSettings').addEventListener('click', () => this.hideSettings());
        document.getElementById('saveSettings').addEventListener('click', () => this.saveSettings());
        document.getElementById('cancelSettings').addEventListener('click', () => this.hideSettings());
        
        // Modal backdrop click
        document.getElementById('settingsModal').addEventListener('click', (e) => {
            if (e.target === document.getElementById('settingsModal')) {
                this.hideSettings();
            }
        });
    }

    initializeTabs() {
        const tabBtns = document.querySelectorAll('.tab-btn');
        const tabPanels = document.querySelectorAll('.tab-panel');
        
        tabBtns.forEach(btn => {
            btn.addEventListener('click', (e) => {
                const targetTab = e.target.getAttribute('data-tab');
                
                // Update active tab button
                tabBtns.forEach(b => b.classList.remove('active'));
                e.target.classList.add('active');
                
                // Update active tab panel
                tabPanels.forEach(panel => {
                    if (panel.id === targetTab) {
                        panel.classList.add('active');
                    } else {
                        panel.classList.remove('active');
                    }
                });
                
                // Initialize tab-specific functionality
                if (targetTab === 'dashboard') {
                    this.updateDashboard();
                } else if (targetTab === 'analysis') {
                    this.refreshAnalysisChart();
                }
            });
        });
    }

    async refreshPorts() {
        try {
            const response = await fetch('/api/ports');
            const data = await response.json();
            
            const portSelect = document.getElementById('portSelect');
            portSelect.innerHTML = '';
            
            data.ports.forEach(port => {
                const option = document.createElement('option');
                option.value = port.device;
                option.textContent = `${port.device} - ${port.description}`;
                portSelect.appendChild(option);
            });
            
            // Add default ttyUSB0 if not present
            if (!data.ports.find(p => p.device === '/dev/ttyUSB0')) {
                const option = document.createElement('option');
                option.value = '/dev/ttyUSB0';
                option.textContent = '/dev/ttyUSB0 - USB Serial Port';
                portSelect.appendChild(option);
            }
        } catch (error) {
            console.error('Error refreshing ports:', error);
            this.addTerminalLine('Error refreshing ports', 'error');
        }
    }

    async connectSerial() {
        const port = document.getElementById('portSelect').value;
        const baudRate = parseInt(document.getElementById('baudRate').value);
        
        try {
            const response = await fetch('/api/serial/connect', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ port, baud_rate: baudRate })
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.serialConnected = true;
                this.updateSerialStatus();
                this.addTerminalLine(data.message, 'system');
                
                document.getElementById('connectBtn').disabled = true;
                document.getElementById('disconnectBtn').disabled = false;
            } else {
                this.addTerminalLine(data.message, 'error');
            }
        } catch (error) {
            console.error('Error connecting to serial port:', error);
            this.addTerminalLine('Error connecting to serial port', 'error');
        }
    }

    async disconnectSerial() {
        try {
            const response = await fetch('/api/serial/disconnect', {
                method: 'POST'
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.serialConnected = false;
                this.updateSerialStatus();
                this.addTerminalLine(data.message, 'system');
                
                document.getElementById('connectBtn').disabled = false;
                document.getElementById('disconnectBtn').disabled = true;
            }
        } catch (error) {
            console.error('Error disconnecting from serial port:', error);
            this.addTerminalLine('Error disconnecting from serial port', 'error');
        }
    }

    sendSerialCommand(command = null) {
        const cmd = command || document.getElementById('serialInput').value.trim();
        
        if (!cmd) return;
        
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({
                type: 'serial_command',
                command: cmd
            }));
            
            this.addTerminalLine(`> ${cmd}`, 'input');
            
            if (!command) {
                document.getElementById('serialInput').value = '';
            }
        } else {
            this.addTerminalLine('WebSocket not connected', 'error');
        }
    }

    sendChatMessage() {
        const input = document.getElementById('chatInput');
        const message = input.value.trim();
        
        if (!message) return;
        
        this.addChatMessage(message, 'user');
        
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({
                type: 'chat',
                message: message
            }));
        } else {
            this.addChatMessage('WebSocket not connected', 'system');
        }
        
        input.value = '';
    }

    addChatMessage(message, type) {
        const chatMessages = document.getElementById('chatMessages');
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${type}`;
        messageDiv.textContent = message;
        
        chatMessages.appendChild(messageDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    addTerminalLine(text, type) {
        const terminal = document.getElementById('terminalOutput');
        const line = document.createElement('div');
        line.className = `terminal-line ${type}`;
        line.textContent = text;
        
        terminal.appendChild(line);
        
        if (this.autoScroll) {
            terminal.scrollTop = terminal.scrollHeight;
        }
    }

    clearTerminal() {
        document.getElementById('terminalOutput').innerHTML = '';
    }

    updateConnectionStatus(connected) {
        const statusIndicator = document.getElementById('connectionStatus');
        const wsStatus = document.getElementById('wsStatus');
        
        if (connected) {
            statusIndicator.classList.add('connected');
            statusIndicator.querySelector('span').textContent = 'Connected';
            wsStatus.textContent = 'Connected';
        } else {
            statusIndicator.classList.remove('connected');
            statusIndicator.querySelector('span').textContent = 'Disconnected';
            wsStatus.textContent = 'Disconnected';
        }
    }

    updateSerialStatus() {
        const serialStatus = document.getElementById('serialStatus');
        serialStatus.textContent = this.serialConnected ? 'Connected' : 'Disconnected';
    }

    updateStatus() {
        this.updateSerialStatus();
        // Update other status indicators
        setInterval(() => {
            this.updateDataStats();
        }, this.autoRefreshInterval);
    }

    updateDataStats() {
        document.getElementById('dataCount').textContent = this.dataBuffer.length;
        document.getElementById('bufferSize').textContent = this.dataBuffer.length;
    }

    updateRecentDataList() {
        const dataList = document.getElementById('recentData');
        dataList.innerHTML = '';
        
        // Show last 10 data points
        const recentData = this.dataBuffer.slice(-10);
        
        recentData.forEach(item => {
            const dataItem = document.createElement('div');
            dataItem.className = 'data-item';
            dataItem.innerHTML = `
                <div class="timestamp">${new Date(item.timestamp).toLocaleTimeString()}</div>
                <div>${item.data}</div>
            `;
            dataList.appendChild(dataItem);
        });
    }

    initializeCharts() {
        // Initialize real-time chart
        this.charts.realtime = {
            data: [{
                x: [],
                y: [],
                type: 'scatter',
                mode: 'lines+markers',
                line: { color: '#00ff88' },
                marker: { size: 4 }
            }],
            layout: {
                title: 'Real-time Data',
                xaxis: { title: 'Time' },
                yaxis: { title: 'Value' },
                paper_bgcolor: 'rgba(0,0,0,0)',
                plot_bgcolor: 'rgba(0,0,0,0)',
                font: { color: '#ffffff' },
                showlegend: false,
                margin: { l: 40, r: 40, t: 40, b: 40 }
            },
            config: { responsive: true }
        };
        
        Plotly.newPlot('realtimeChart', this.charts.realtime.data, this.charts.realtime.layout, this.charts.realtime.config);
    }

    updateRealtimeChart() {
        if (!this.dataBuffer.length) return;
        
        // Extract numeric values from data
        const chartData = this.dataBuffer.map(item => {
            const timestamp = new Date(item.timestamp);
            const numericMatch = item.data.match(/-?\d+\.?\d*/);
            const value = numericMatch ? parseFloat(numericMatch[0]) : 0;
            return { x: timestamp, y: value };
        });
        
        const times = chartData.map(d => d.x);
        const values = chartData.map(d => d.y);
        
        Plotly.restyle('realtimeChart', {
            x: [times],
            y: [values]
        });
    }

    async refreshAnalysisChart() {
        try {
            const response = await fetch('/api/data/chart');
            const data = await response.json();
            
            if (data.error) {
                document.getElementById('analysisChart').innerHTML = '<p>No data available for analysis</p>';
                return;
            }
            
            const chartData = JSON.parse(data.chart);
            Plotly.newPlot('analysisChart', chartData.data, chartData.layout, { responsive: true });
        } catch (error) {
            console.error('Error refreshing analysis chart:', error);
            document.getElementById('analysisChart').innerHTML = '<p>Error loading chart data</p>';
        }
    }

    updateDashboard() {
        this.updateRecentDataList();
        this.updateRealtimeChart();
    }

    async exportData() {
        try {
            const response = await fetch('/api/data/export');
            const data = await response.json();
            
            const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `obd_data_${new Date().toISOString().split('T')[0]}.json`;
            a.click();
            URL.revokeObjectURL(url);
            
            this.addTerminalLine(`Exported ${data.count} data points`, 'system');
        } catch (error) {
            console.error('Error exporting data:', error);
            this.addTerminalLine('Error exporting data', 'error');
        }
    }

    async clearData() {
        if (confirm('Are you sure you want to clear all data?')) {
            try {
                const response = await fetch('/api/data/clear', { method: 'POST' });
                const data = await response.json();
                
                if (data.success) {
                    this.dataBuffer = [];
                    this.updateRecentDataList();
                    this.updateDataStats();
                    this.addTerminalLine('All data cleared', 'system');
                }
            } catch (error) {
                console.error('Error clearing data:', error);
                this.addTerminalLine('Error clearing data', 'error');
            }
        }
    }

    showSettings() {
        document.getElementById('settingsModal').style.display = 'block';
        this.loadSettings();
    }

    hideSettings() {
        document.getElementById('settingsModal').style.display = 'none';
    }

    loadSettings() {
        document.getElementById('autoRefresh').value = this.autoRefreshInterval;
        document.getElementById('maxDataPoints').value = this.maxDataPoints;
        document.getElementById('autoScroll').checked = this.autoScroll;
        document.getElementById('soundNotifications').checked = this.soundNotifications;
    }

    saveSettings() {
        this.autoRefreshInterval = parseInt(document.getElementById('autoRefresh').value);
        this.maxDataPoints = parseInt(document.getElementById('maxDataPoints').value);
        this.autoScroll = document.getElementById('autoScroll').checked;
        this.soundNotifications = document.getElementById('soundNotifications').checked;
        
        // Save to localStorage
        localStorage.setItem('obdSettings', JSON.stringify({
            autoRefreshInterval: this.autoRefreshInterval,
            maxDataPoints: this.maxDataPoints,
            autoScroll: this.autoScroll,
            soundNotifications: this.soundNotifications
        }));
        
        this.hideSettings();
        this.addTerminalLine('Settings saved', 'system');
    }

    loadStoredSettings() {
        const stored = localStorage.getItem('obdSettings');
        if (stored) {
            const settings = JSON.parse(stored);
            this.autoRefreshInterval = settings.autoRefreshInterval || 1000;
            this.maxDataPoints = settings.maxDataPoints || 100;
            this.autoScroll = settings.autoScroll !== undefined ? settings.autoScroll : true;
            this.soundNotifications = settings.soundNotifications || false;
        }
    }

    playNotificationSound() {
        if (!this.soundNotifications) return;
        
        // Create a simple beep sound
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const oscillator = audioContext.createOscillator();
        const gainNode = audioContext.createGain();
        
        oscillator.connect(gainNode);
        gainNode.connect(audioContext.destination);
        
        oscillator.frequency.value = 800;
        oscillator.type = 'sine';
        gainNode.gain.value = 0.1;
        
        oscillator.start();
        oscillator.stop(audioContext.currentTime + 0.1);
    }
}

// Initialize the application when the page loads
document.addEventListener('DOMContentLoaded', () => {
    window.obdApp = new OBDDiagnosticApp();
});

// Handle page visibility changes
document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        console.log('Page hidden - reducing updates');
    } else {
        console.log('Page visible - resuming updates');
        if (window.obdApp) {
            window.obdApp.updateDashboard();
        }
    }
});

// Handle window resize
window.addEventListener('resize', () => {
    if (window.obdApp && window.obdApp.charts.realtime) {
        Plotly.Plots.resize('realtimeChart');
        if (document.getElementById('analysisChart')) {
            Plotly.Plots.resize('analysisChart');
        }
    }
});

// Periodic ping to keep connection alive
setInterval(() => {
    if (window.obdApp && window.obdApp.ws && window.obdApp.ws.readyState === WebSocket.OPEN) {
        window.obdApp.ws.send(JSON.stringify({ type: 'ping' }));
    }
}, 30000); // Send ping every 30 seconds