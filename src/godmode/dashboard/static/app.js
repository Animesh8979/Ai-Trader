let socket = null;
let equityChart = null;
let previousStats = { equity: 0, pnl: 0, exposure: 0 };
let globalFills = [];

/* =========================================================================
   1. GENERATIVE DATA BACKGROUND (PARTICLE ENGINE)
   ========================================================================= */
const canvas = document.getElementById('bg-canvas');
const ctxBg = canvas.getContext('2d');
let particles = [];
let targetSpeedMultiplier = 1.0;
let currentSpeedMultiplier = 1.0;

function initCanvas() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    particles = [];
    const particleCount = 150; 
    for(let i=0; i<particleCount; i++) {
        particles.push({
            x: Math.random() * canvas.width,
            y: Math.random() * canvas.height,
            size: Math.random() * 1.5 + 0.5,
            vx: (Math.random() - 0.5) * 0.4,
            vy: (Math.random() - 0.5) * 0.4,
            baseColor: 'rgba(0, 229, 255, 0.15)'
        });
    }
}

function animateParticles() {
    ctxBg.clearRect(0, 0, canvas.width, canvas.height);
    currentSpeedMultiplier += (targetSpeedMultiplier - currentSpeedMultiplier) * 0.05;

    particles.forEach(p => {
        p.x += p.vx * currentSpeedMultiplier;
        p.y += p.vy * currentSpeedMultiplier;

        if(p.x < 0) p.x = canvas.width;
        if(p.x > canvas.width) p.x = 0;
        if(p.y < 0) p.y = canvas.height;
        if(p.y > canvas.height) p.y = 0;

        ctxBg.fillStyle = p.baseColor;
        ctxBg.beginPath();
        ctxBg.arc(p.x, p.y, p.size, 0, Math.PI * 2);
        ctxBg.fill();
    });
    requestAnimationFrame(animateParticles);
}

window.addEventListener('resize', () => {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
});

initCanvas();
animateParticles();

function updateEnvironment(exposure) {
    if(exposure > 10000) {
        targetSpeedMultiplier = 4.0;
        particles.forEach(p => p.baseColor = 'rgba(255, 51, 102, 0.25)'); // Red warning speed
    } else if(exposure > 1000) {
        targetSpeedMultiplier = 2.5;
        particles.forEach(p => p.baseColor = 'rgba(0, 255, 135, 0.25)'); // Green high trade speed
    } else if (exposure > 0) {
        targetSpeedMultiplier = 1.8;
        particles.forEach(p => p.baseColor = 'rgba(0, 229, 255, 0.2)'); // Cyan active trading
    } else {
        targetSpeedMultiplier = 1.0;
        particles.forEach(p => p.baseColor = 'rgba(255, 255, 255, 0.05)'); // Calm white standby
    }
}

/* =========================================================================
   2. SYSTEM HUD CLOCK & REAL-TIME UTILITIES
   ========================================================================= */
function startClock() {
    setInterval(() => {
        const clockEl = document.getElementById('hud-clock');
        if (clockEl) {
            const now = new Date();
            const utcStr = now.toISOString().substring(11, 19);
            clockEl.innerText = `${utcStr}`;
        }
    }, 1000);
}

/* =========================================================================
   3. CHART.JS DUAL-AXIS NEON LINE GRAPH
   ========================================================================= */
const ctxChart = document.getElementById('equityChart').getContext('2d');
let gradientFill = ctxChart.createLinearGradient(0, 0, 0, 400);
gradientFill.addColorStop(0, 'rgba(0, 255, 135, 0.2)');
gradientFill.addColorStop(1, 'rgba(0, 255, 135, 0.0)');

equityChart = new Chart(ctxChart, {
    type: 'line',
    data: {
        labels: [],
        datasets: [
            {
                label: 'Portfolio Value',
                data: [],
                borderColor: '#00ff87',
                backgroundColor: gradientFill,
                borderWidth: 2,
                fill: true,
                tension: 0.4, 
                pointRadius: 0,
                pointHoverRadius: 6,
            },
            {
                label: 'Gross Exposure',
                data: [],
                borderColor: 'rgba(0, 229, 255, 0.5)',
                backgroundColor: 'transparent',
                borderWidth: 1.5,
                borderDash: [4, 4],
                fill: false,
                tension: 0.4,
                pointRadius: 0,
            }
        ]
    },
    plugins: [{
        id: 'neonGlow',
        beforeDatasetsDraw(chart) {
            const ctx = chart.ctx;
            ctx.save();
            ctx.shadowColor = 'rgba(0, 255, 135, 0.35)';
            ctx.shadowBlur = 12;
            ctx.shadowOffsetX = 0;
            ctx.shadowOffsetY = 0;
        },
        afterDatasetsDraw(chart) {
            chart.ctx.restore();
        }
    }],
    options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { intersect: false, mode: 'index' },
        scales: {
            x: { grid: { display: false }, ticks: { color: '#94a3b8', font: { family: 'JetBrains Mono', size: 10 } } },
            y: { grid: { color: 'rgba(255, 255, 255, 0.015)' }, ticks: { color: '#94a3b8', font: { family: 'JetBrains Mono', size: 10 } } }
        },
        plugins: { legend: { display: false } }
    }
});

function runEntranceAnimations() {
    gsap.from(".gsap-reveal", {
        y: -30, opacity: 0, duration: 0.8, ease: "power3.out", stagger: 0.08
    });
    gsap.from(".gsap-stagger", {
        y: 40, opacity: 0, duration: 0.8, ease: "back.out(1.2)", stagger: 0.08, delay: 0.1
    });
}

function animateValue(id, start, end) {
    const el = document.getElementById(id);
    if(!el) return;
    gsap.to(el, {
        innerHTML: end,
        duration: 0.8,
        snap: { innerHTML: 0.01 },
        ease: "power2.out",
        onUpdate: function() {
            el.innerHTML = parseFloat(this.targets()[0].innerHTML).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        }
    });
}

/* =========================================================================
   4. MAGNETIC BUTTON HUD ACTIONS
   ========================================================================= */
document.querySelectorAll('.magnetic-btn').forEach(btn => {
    btn.addEventListener('mousemove', (e) => {
        const rect = btn.getBoundingClientRect();
        const x = e.clientX - rect.left - rect.width / 2;
        const y = e.clientY - rect.top - rect.height / 2;
        gsap.to(btn, {
            x: x * 0.25,
            y: y * 0.25,
            duration: 0.3,
            ease: "power2.out"
        });
    });
    btn.addEventListener('mouseleave', () => {
        gsap.to(btn, {
            x: 0,
            y: 0,
            duration: 0.6,
            ease: "elastic.out(1.1, 0.3)"
        });
    });
});

/* =========================================================================
   5. WEBSOCKET STATE HOOKS & HUD OVERLAYS
   ========================================================================= */
function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    
    socket = new WebSocket(wsUrl);

    socket.onopen = () => {
        const overlay = document.getElementById('severed-overlay');
        if (overlay) overlay.classList.remove('visible');
        addLogLine('SYS', 'Neural link established. Awaiting telemetry.', 'success');
        fetchInitialData();
    };

    socket.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            handleWebSocketMessage(data);
        } catch (exc) {
            console.error('Failed to parse WebSocket message:', exc);
        }
    };

    socket.onclose = () => {
        const overlay = document.getElementById('severed-overlay');
        if (overlay) overlay.classList.add('visible');
        addLogLine('SYS', 'Link severed. Reconnecting in 5s...', 'warn');
        setTimeout(connectWebSocket, 5000);
    };
}

function handleWebSocketMessage(data) {
    if (data.type === 'status') {
        updateStatusUI(data.payload);
    } else if (data.type === 'log') {
        addLogLine(data.source, data.text, data.level);
        if (data.text.includes('BACKTESTER') || data.text.includes('Backtest')) {
            addBacktestLogLine(data.source, data.text, data.level);
            if (data.text.includes('Backtest completed') || data.text.includes('failed')) {
                const btn = document.getElementById('btn-run-backtest');
                if (btn) { btn.disabled = false; btn.innerText = '[ INITIATE SIMULATION ]'; }
                fetchInitialData();
            }
        }
    } else if (data.type === 'chart_update') {
        addChartDataPoint(data.timestamp, data.equity, data.exposure);
    }
}

function flashElement(id, oldVal, newVal) {
    if (oldVal === newVal) return;
    const el = document.getElementById(id);
    if (!el) return;
    el.classList.remove('flash-up', 'flash-down');
    void el.offsetWidth;
    if (newVal > oldVal) el.classList.add('flash-up');
    else el.classList.add('flash-down');
}

function updateStatusUI(status) {
    document.getElementById('app-mode-subtitle').innerText = `MODE: ${status.mode.toUpperCase()} // BASE: ${status.base_currency}`;
    
    const badge = document.getElementById('status-badge');
    const statusText = document.getElementById('status-text');
    const btnStop = document.getElementById('btn-emergency-stop');
    const btnResume = document.getElementById('btn-emergency-resume');

    if (status.halted) {
        badge.className = 'status-badge halted';
        statusText.innerText = 'HALTED';
        btnStop.style.display = 'none';
        btnResume.style.display = 'flex';
    } else {
        badge.className = 'status-badge running';
        statusText.innerText = 'RUNNING';
        btnStop.style.display = 'flex';
        btnResume.style.display = 'none';
    }

    const newEquity = parseFloat(status.equity || 0);
    const newPnl = parseFloat(status.realized_pnl || 0);
    const newExposure = parseFloat(status.gross_exposure || 0);

    flashElement('box-total-value', previousStats.equity, newEquity);
    flashElement('box-realized-pnl', previousStats.pnl, newPnl);
    flashElement('box-gross-exposure', previousStats.exposure, newExposure);

    animateValue('stat-total-value', previousStats.equity, newEquity);
    animateValue('stat-gross-exposure', previousStats.exposure, newExposure);
    
    const pnlEl = document.getElementById('stat-realized-pnl');
    pnlEl.innerText = `${newPnl >= 0 ? '+' : ''}${parseFloat(newPnl).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    pnlEl.className = `stat-value ${newPnl >= 0 ? 'text-up' : 'text-down'}`;

    // Update background particle environment
    updateEnvironment(newExposure);

    // Update Risk Limits Gauges
    const exposureRatio = newEquity > 0 ? (newExposure / newEquity) * 100 : 0;
    const expBar = document.getElementById('risk-gauge-exposure-bar');
    const expVal = document.getElementById('risk-gauge-exposure-val');
    if (expBar && expVal) {
        expBar.style.width = `${Math.min(exposureRatio, 100)}%`;
        expVal.innerText = `${exposureRatio.toFixed(1)}%`;
        // Warn if exposure is too high
        if (exposureRatio > 80) expBar.className = "gauge-bar danger";
        else if (exposureRatio > 40) expBar.className = "gauge-bar warning";
        else expBar.className = "gauge-bar";
    }

    let peakEquity = newEquity;
    if (status.history && status.history.length > 0) {
        status.history.forEach(pt => {
            if (pt.equity > peakEquity) peakEquity = pt.equity;
        });
    }
    const drawdown = peakEquity > 0 ? ((peakEquity - newEquity) / peakEquity) * 100 : 0;
    const ddBar = document.getElementById('risk-gauge-dd-bar');
    const ddVal = document.getElementById('risk-gauge-dd-val');
    if (ddBar && ddVal) {
        // Drawdown limit is 5.0%
        const pct = (drawdown / 5.0) * 100;
        ddBar.style.width = `${Math.min(pct, 100)}%`;
        ddVal.innerText = `${drawdown.toFixed(2)}% / 5.00%`;
    }

    let consecutiveLosses = 0;
    if (globalFills && globalFills.length > 0) {
        for (let i = 0; i < globalFills.length; i++) {
            const p = parseFloat(globalFills[i].realized_pnl || 0);
            if (p < 0) {
                consecutiveLosses++;
            } else if (p > 0) {
                break;
            }
        }
    }
    const clBar = document.getElementById('risk-gauge-losses-bar');
    const clVal = document.getElementById('risk-gauge-losses-val');
    if (clBar && clVal) {
        clBar.style.width = `${Math.min(consecutiveLosses * 33.3, 100)}%`;
        clVal.innerText = `${consecutiveLosses} / 3`;
    }

    previousStats = { equity: newEquity, pnl: newPnl, exposure: newExposure };

    const tbody = document.getElementById('positions-table-body');
    if (!status.positions || status.positions.length === 0) {
        tbody.innerHTML = `<tr><td colspan="3" style="text-align: center; color: var(--text-secondary); padding: 24px;">[ NO OPEN POSITIONS ]</td></tr>`;
    } else {
        tbody.innerHTML = status.positions.map(pos => {
            const upnl = parseFloat(pos.unrealized_pnl || 0);
            return `
                <tr>
                    <td style="font-weight: 700; color: var(--text-primary);">${pos.symbol}</td>
                    <td class="${pos.qty >= 0 ? 'text-up' : 'text-down'}">${pos.qty >= 0 ? '+' : ''}${pos.qty}</td>
                    <td><span class="badge ${upnl >= 0 ? 'badge-up' : 'badge-down'}">${upnl >= 0 ? '+' : ''}${parseFloat(upnl).toFixed(2)}</span></td>
                </tr>
            `;
        }).join('');
    }
}

async function fetchInitialData() {
    const startFetch = performance.now();
    try {
        const resp = await fetch('/api/status');
        const latency = Math.round(performance.now() - startFetch);
        const latEl = document.getElementById('hud-latency');
        if (latEl) latEl.innerText = `${latency} ms`;
        
        const data = await resp.json();
        updateStatusUI(data);
        
        if (data.history && data.history.length > 0) {
            equityChart.data.labels = data.history.map(pt => pt.time);
            equityChart.data.datasets[0].data = data.history.map(pt => pt.equity);
            equityChart.data.datasets[1].data = data.history.map(pt => pt.exposure);
            equityChart.update();
        }
    } catch (exc) {
        console.error('Failed to load initial status:', exc);
    }
}

async function triggerEmergencyStop() {
    try {
        const resp = await fetch('/api/stop', { method: 'POST' });
        if (resp.ok) { addLogLine('USR', 'OVERRIDE: HALT SIGNAL SENT.', 'error'); fetchInitialData(); }
    } catch (exc) {}
}

async function triggerEmergencyResume() {
    try {
        const resp = await fetch('/api/resume', { method: 'POST' });
        if (resp.ok) { addLogLine('USR', 'OVERRIDE: RESUME SIGNAL SENT.', 'success'); fetchInitialData(); }
    } catch (exc) {}
}

function addLogLine(source, text, level) {
    const terminal = document.getElementById('log-terminal');
    if (!terminal) return;
    const line = document.createElement('div');
    line.className = `log-line ${level || 'info'}`;
    const time = new Date().toLocaleTimeString('en-US', { hour12: false, fractionalSecondDigits: 3 }).replace(' ', '');
    line.innerHTML = `<span class="log-time">[${time}]</span><span class="log-src">${source.substring(0,3).toUpperCase()}</span>${text}`;
    terminal.appendChild(line);
    if(terminal.childNodes.length > 200) terminal.removeChild(terminal.firstChild);
    terminal.scrollTop = terminal.scrollHeight;
}

function addChartDataPoint(timestamp, equity, exposure) {
    equityChart.data.labels.push(timestamp);
    equityChart.data.datasets[0].data.push(equity);
    equityChart.data.datasets[1].data.push(exposure);
    if (equityChart.data.labels.length > 60) {
        equityChart.data.labels.shift();
        equityChart.data.datasets[0].data.shift();
        equityChart.data.datasets[1].data.shift();
    }
    equityChart.update();
}

/* =========================================================================
   6. TABS NAVIGATION & MOTION CHOREOGRAPHY (GSAP STAGGER)
   ========================================================================= */
function switchTab(tabId) {
    const currentTab = document.querySelector('.tab-content.active');
    const nextTab = document.getElementById(`tab-${tabId}`);
    if (!nextTab || currentTab === nextTab) return;

    // 1. Highlight tab button
    document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
    const btn = Array.from(document.querySelectorAll('.tab-btn')).find(b => b.getAttribute('onclick').includes(tabId));
    if (btn) btn.classList.add('active');

    // 2. Animate transition
    if (currentTab) {
        gsap.to(currentTab, {
            opacity: 0,
            y: 12,
            duration: 0.15,
            ease: "power2.in",
            onComplete: () => {
                currentTab.classList.remove('active');
                
                // Set initial properties for next tab
                nextTab.style.opacity = 0;
                nextTab.style.transform = 'translateY(12px)';
                nextTab.classList.add('active');

                // Animate in next tab content
                gsap.to(nextTab, {
                    opacity: 1,
                    y: 0,
                    duration: 0.35,
                    ease: "power2.out"
                });

                // Stagger cards in the loaded tab
                gsap.from(nextTab.querySelectorAll('.gsap-stagger'), {
                    y: 20,
                    opacity: 0,
                    duration: 0.45,
                    stagger: 0.06,
                    ease: "back.out(1.1)"
                });
            }
        });
    } else {
        nextTab.classList.add('active');
    }

    // 3. Trigger endpoint fetches per tab
    if (tabId === 'overview') fetchInitialData();
    else if (tabId === 'agents') fetchAgentMessages();
    else if (tabId === 'risk') { fetchRiskDecisions(); fetchKillEvents(); }
    else if (tabId === 'execution') { fetchOrders(); fetchFills(); }
}

/* =========================================================================
   7. NEURAL AGENT STATE CONTROLLERS
   ========================================================================= */
function mapRoleToId(role) {
    const r = role.toLowerCase();
    if (r.includes('orchestrator')) return 'orchestrator';
    if (r.includes('analyst')) return 'analyst';
    if (r.includes('trader')) return 'trader';
    if (r.includes('risk')) return 'risk';
    return null;
}

function setAgentActiveState(role, stateText, infoText) {
    const key = mapRoleToId(role);
    if (!key) return;
    const card = document.getElementById(`monitor-${key}`);
    if (card) card.classList.add('active-thinking');
    const stateEl = document.getElementById(`state-${key}`);
    if (stateEl) stateEl.innerText = stateText;
    const infoEl = document.getElementById(`info-${key}`);
    if (infoEl) infoEl.innerText = infoText;
}

function setAgentIdleState(role) {
    const key = mapRoleToId(role);
    if (!key) return;
    const card = document.getElementById(`monitor-${key}`);
    if (card) card.classList.remove('active-thinking');
    const stateEl = document.getElementById(`state-${key}`);
    if (stateEl) stateEl.innerText = 'IDLE';
    const infoEl = document.getElementById(`info-${key}`);
    if (infoEl) infoEl.innerText = 'Standby';
}

async function fetchAgentMessages() {
    try {
        const resp = await fetch('/api/agent_messages');
        const msgs = await resp.json();
        const container = document.getElementById('agent-debate-container');
        if (!msgs || msgs.length === 0) {
            container.innerHTML = `<p style="text-align: center; color: var(--text-secondary); padding: 48px; font-family: var(--font-mono); font-size: 0.8rem;">[ NO SIGNAL DETECTED ]</p>`;
            return;
        }
        
        container.innerHTML = '';
        
        msgs.forEach((m, idx) => {
            const roleClass = `role-${m.role.toLowerCase().replace(' ', '')}`;
            const timeStr = new Date(m.ts).toLocaleString('en-US', {hour12: false});
            
            const card = document.createElement('div');
            card.className = `debate-card ${roleClass}`;
            card.innerHTML = `
                <div class="debate-header">
                    <span class="debate-role">:: ${m.role} ::</span>
                    <span style="font-size: 0.7rem; color: var(--text-secondary); font-family: var(--font-mono);">${timeStr}</span>
                </div>
                <div class="debate-meta">
                    <span class="meta-pill">TKN_IN:${m.tokens_in}</span>
                    <span class="meta-pill">TKN_OUT:${m.tokens_out}</span>
                    <span class="meta-pill">LAT:${m.latency_ms}ms</span>
                </div>
                ${m.input_summary ? `<div class="debate-summary">${m.input_summary}</div>` : ''}
                <div class="debate-text typing-active" id="debate-text-${idx}"></div>
            `;
            container.appendChild(card);
            
            // GSAP Typing Simulation & Neural Monitor State Bindings
            gsap.to(`#debate-text-${idx}`, {
                text: { value: m.output_text, speed: 2.5 },
                ease: "none",
                delay: idx * 0.15,
                onStart: () => {
                    setAgentActiveState(m.role, 'EMITTING', `${m.latency_ms}ms // ${m.tokens_out} tkn`);
                },
                onComplete: () => {
                    const textEl = document.getElementById(`debate-text-${idx}`);
                    if (textEl) textEl.classList.remove('typing-active');
                    setAgentIdleState(m.role);
                }
            });
        });
    } catch (err) {
        console.error('Failed to fetch agent messages:', err);
    }
}

/* =========================================================================
   8. ENDPOINT API QUERIES
   ========================================================================= */
async function fetchRiskDecisions() {
    try {
        const resp = await fetch('/api/decisions');
        const decisions = await resp.json();
        const tbody = document.getElementById('decisions-table-body');
        if (!decisions || decisions.length === 0) {
            tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-secondary); padding: 24px;">[ CLEAR ]</td></tr>`;
            return;
        }
        tbody.innerHTML = decisions.map(d => {
            const timeStr = new Date(d.ts).toLocaleTimeString('en-US', {hour12: false});
            const verdictClass = d.risk_verdict.toLowerCase() === 'approve' ? 'badge-up' : 'badge-down';
            return `<tr>
                    <td>${timeStr}</td>
                    <td style="color: var(--text-secondary);">${d.desk || 'N/A'}</td>
                    <td style="color: var(--text-primary); font-weight: 700;">${d.symbol || 'N/A'}</td>
                    <td><span class="badge ${verdictClass}">${d.risk_verdict.toUpperCase()}</span></td>
                    <td style="color: var(--text-secondary); font-size: 0.75rem;">${d.reason || 'N/A'}</td>
                </tr>`;
        }).join('');
    } catch (err) { console.error(err); }
}

async function fetchKillEvents() {
    try {
        const resp = await fetch('/api/kill_events');
        const events = await resp.json();
        const container = document.getElementById('kill-events-timeline');
        if (!events || events.length === 0) {
            container.innerHTML = `<p style="text-align: center; color: var(--text-secondary); padding: 24px; font-family: var(--font-mono); font-size: 0.8rem;">[ ZERO ANOMALIES ]</p>`;
            return;
        }
        container.innerHTML = `<table style="width:100%"><tbody>` + events.map(e => {
            const timeStr = new Date(e.ts).toLocaleTimeString('en-US', {hour12: false});
            const color = e.action === 'engage' ? 'var(--accent-danger)' : 'var(--accent-primary)';
            return `<tr>
                    <td style="color: var(--text-secondary); width: 80px;">${timeStr}</td>
                    <td style="color: ${color}; font-weight: 700;">${e.action.toUpperCase()}</td>
                    <td style="color: var(--text-secondary); font-size: 0.75rem;">${e.reason || ''}</td>
                </tr>`;
        }).join('') + `</tbody></table>`;
    } catch (err) { console.error(err); }
}

async function fetchOrders() {
    try {
        const resp = await fetch('/api/orders');
        const orders = await resp.json();
        const tbody = document.getElementById('orders-table-body');
        if (!orders || orders.length === 0) {
            tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-secondary); padding: 24px;">[ EMPTY ]</td></tr>`;
            return;
        }
        tbody.innerHTML = orders.map(o => {
            const timeStr = new Date(o.created_at).toLocaleTimeString('en-US', {hour12: false});
            const sideClass = o.side === 'buy' ? 'text-up' : 'text-down';
            return `<tr>
                    <td style="color: var(--text-secondary);">${timeStr}</td>
                    <td style="color: var(--text-primary); font-weight: 700;">${o.symbol}</td>
                    <td class="${sideClass}">${o.side.toUpperCase()} <span style="color:var(--text-secondary)">${o.type.substring(0,3).toUpperCase()}</span></td>
                    <td>${o.qty} @ ${o.price ? parseFloat(o.price).toFixed(2) : 'MKT'}</td>
                    <td><span class="badge ${o.status === 'filled' ? 'badge-up' : 'badge-down'}">${o.status.substring(0,4).toUpperCase()}</span></td>
                </tr>`;
        }).join('');
    } catch (err) { console.error(err); }
}

async function fetchFills() {
    try {
        const resp = await fetch('/api/fills');
        globalFills = await resp.json();
        const tbody = document.getElementById('fills-table-body');
        if (!globalFills || globalFills.length === 0) {
            tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-secondary); padding: 24px;">[ EMPTY ]</td></tr>`;
            return;
        }
        tbody.innerHTML = globalFills.map(f => {
            const timeStr = new Date(f.ts).toLocaleTimeString('en-US', {hour12: false});
            const sideClass = f.side === 'buy' ? 'text-up' : 'text-down';
            const pnl = parseFloat(f.realized_pnl || 0);
            return `<tr>
                    <td style="color: var(--text-secondary);">${timeStr}</td>
                    <td style="color: var(--text-primary); font-weight: 700;">${f.symbol}</td>
                    <td class="${sideClass}">${f.side.toUpperCase()}</td>
                    <td>${f.qty} @ ${parseFloat(f.price).toFixed(2)}</td>
                    <td><span class="badge ${pnl >= 0 ? 'badge-up' : 'badge-down'}">${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}</span></td>
                </tr>`;
        }).join('');
    } catch (err) { console.error(err); }
}

async function runBacktest(event) {
    event.preventDefault();
    const strategy = document.getElementById('backtest-strategy').value;
    const data_path = document.getElementById('backtest-data').value;
    const start = document.getElementById('backtest-start').value || null;
    const end = document.getElementById('backtest-end').value || null;

    const btn = document.getElementById('btn-run-backtest');
    btn.disabled = true;
    btn.innerText = '[ EXECUTING... ]';

    const consoleBox = document.getElementById('backtest-console');
    consoleBox.innerHTML = `<div class="log-line system"><span class="log-time">[INIT]</span><span class="log-src">SIM</span>Spawning strategy ${strategy}...</div>`;

    try {
        const resp = await fetch('/api/backtest/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ strategy, data_path, start, end })
        });
        const result = await resp.json();
        if (result.status === 'ok') addBacktestLogLine('SIM', 'Process attached.', 'success');
        else { addBacktestLogLine('SIM', `FATAL: ${result.message}`, 'error'); btn.disabled = false; btn.innerText = '[ INITIATE SIMULATION ]'; }
    } catch (err) { addBacktestLogLine('SIM', `NET_ERR: ${err}`, 'error'); btn.disabled = false; btn.innerText = '[ INITIATE SIMULATION ]'; }
}

function addBacktestLogLine(source, text, level) {
    const consoleBox = document.getElementById('backtest-console');
    if (!consoleBox) return;
    const line = document.createElement('div');
    line.className = `log-line ${level || 'info'}`;
    const time = new Date().toLocaleTimeString('en-US', {hour12: false, fractionalSecondDigits: 3}).replace(' ', '');
    line.innerHTML = `<span class="log-time">[${time}]</span><span class="log-src">${source.substring(0,3).toUpperCase()}</span>${text}`;
    consoleBox.appendChild(line);
    consoleBox.scrollTop = consoleBox.scrollHeight;
}

// Initial triggers
runEntranceAnimations();
connectWebSocket();
startClock();
