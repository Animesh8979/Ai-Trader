/**
 * Interactive Swarm Debate Neural DAG Topology Visualizer
 * Renders glowing neural nodes (Bull, Bear, Risk, Macro Council) and real-time pulse edges.
 */

class SwarmDAGVisualizer {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        if (!this.canvas) return;
        this.ctx = this.canvas.getContext('2d');
        this.nodes = [
            { id: 'macro', label: 'MACRO REGIME', x: 0.5, y: 0.18, color: '#00f0ff', conf: 85 },
            { id: 'bull', label: 'BULL AGENT', x: 0.22, y: 0.55, color: '#00ffaa', conf: 60 },
            { id: 'bear', label: 'BEAR AGENT', x: 0.78, y: 0.55, color: '#ff4d6d', conf: 40 },
            { id: 'risk', label: 'RISK AEGIS', x: 0.5, y: 0.86, color: '#ffaa00', conf: 95 }
        ];
        this.edges = [
            { from: 'macro', to: 'bull', active: true },
            { from: 'macro', to: 'bear', active: true },
            { from: 'bull', to: 'risk', active: true },
            { from: 'bear', to: 'risk', active: true }
        ];
        this.pulse = 0;
        this.resize();
        window.addEventListener('resize', () => this.resize());
        this.startAnimation();
    }

    resize() {
        if (!this.canvas) return;
        this.canvas.width = this.canvas.parentElement.clientWidth || 400;
        this.canvas.height = 200;
    }

    updateDebateState(bullConf, bearConf, regimeLabel) {
        this.nodes[1].conf = bullConf || 50;
        this.nodes[2].conf = bearConf || 50;
        if (regimeLabel) this.nodes[0].label = `MACRO: ${regimeLabel.toUpperCase()}`;
    }

    startAnimation() {
        const drawFrame = () => {
            this.pulse = (this.pulse + 0.03) % (Math.PI * 2);
            this.render();
            requestAnimationFrame(drawFrame);
        };
        requestAnimationFrame(drawFrame);
    }

    render() {
        if (!this.ctx) return;
        const width = this.canvas.width;
        const height = this.canvas.height;
        this.ctx.clearRect(0, 0, width, height);

        // Background
        this.ctx.fillStyle = 'rgba(6, 10, 20, 0.95)';
        this.ctx.fillRect(0, 0, width, height);

        // Draw Edges
        this.edges.forEach(e => {
            const n1 = this.nodes.find(n => n.id === e.from);
            const n2 = this.nodes.find(n => n.id === e.to);
            if (!n1 || !n2) return;

            const x1 = n1.x * width;
            const y1 = n1.y * height;
            const x2 = n2.x * width;
            const y2 = n2.y * height;

            this.ctx.beginPath();
            this.ctx.moveTo(x1, y1);
            this.ctx.lineTo(x2, y2);
            this.ctx.strokeStyle = 'rgba(0, 240, 255, 0.25)';
            this.ctx.lineWidth = 2;
            this.ctx.stroke();

            // Animated pulse particle on edge
            const t = (Math.sin(this.pulse) + 1) / 2;
            const px = x1 + (x2 - x1) * t;
            const py = y1 + (y2 - y1) * t;
            this.ctx.beginPath();
            this.ctx.arc(px, py, 3, 0, Math.PI * 2);
            this.ctx.fillStyle = '#00f0ff';
            this.ctx.shadowBlur = 8;
            this.ctx.shadowColor = '#00f0ff';
            this.ctx.fill();
            this.ctx.shadowBlur = 0;
        });

        // Draw Nodes
        this.nodes.forEach(n => {
            const nx = n.x * width;
            const ny = n.y * height;

            // Glow circle
            this.ctx.beginPath();
            this.ctx.arc(nx, ny, 16, 0, Math.PI * 2);
            this.ctx.fillStyle = n.color;
            this.ctx.shadowBlur = 12;
            this.ctx.shadowColor = n.color;
            this.ctx.fill();
            this.ctx.shadowBlur = 0;

            // Inner circle
            this.ctx.beginPath();
            this.ctx.arc(nx, ny, 12, 0, Math.PI * 2);
            this.ctx.fillStyle = '#0a1120';
            this.ctx.fill();

            // Node Text
            this.ctx.font = '10px monospace';
            this.ctx.fillStyle = '#ffffff';
            this.ctx.textAlign = 'center';
            this.ctx.fillText(`${n.label} (${n.conf}%)`, nx, ny + 28);
        });
    }
}

window.SwarmDAGVisualizer = SwarmDAGVisualizer;
