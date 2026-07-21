/**
 * Institutional Level 2 DOM Orderbook & Volume Profile Canvas Renderer
 * Inspired by GitHub js-orderbook-canvas & slick-ladder
 */

class OrderbookCanvasRenderer {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        if (!this.canvas) return;
        this.ctx = this.canvas.getContext('2d');
        this.bids = [];
        this.asks = [];
        this.maxVolume = 1.0;
        this.resize();
        window.addEventListener('resize', () => this.resize());
    }

    resize() {
        if (!this.canvas) return;
        this.canvas.width = this.canvas.parentElement.clientWidth || 400;
        this.canvas.height = 240;
        this.render();
    }

    updateData(bids, asks) {
        // bids/asks are arrays of [price, qty]
        this.bids = bids.slice(0, 10);
        this.asks = asks.slice(0, 10);
        
        let maxV = 0.001;
        this.bids.forEach(b => maxV = Math.max(maxV, parseFloat(b[1])));
        this.asks.forEach(a => maxV = Math.max(maxV, parseFloat(a[1])));
        this.maxVolume = maxV;
        this.render();
    }

    render() {
        if (!this.ctx) return;
        const width = this.canvas.width;
        const height = this.canvas.height;
        this.ctx.clearRect(0, 0, width, height);

        // Dark background
        this.ctx.fillStyle = 'rgba(8, 14, 26, 0.9)';
        this.ctx.fillRect(0, 0, width, height);

        const rowHeight = (height - 30) / 20; // 10 asks + 10 bids
        const halfHeight = height / 2;

        this.ctx.font = '11px monospace';

        // Render Asks (Top half, descending down to spread)
        for (let i = 0; i < this.asks.length; i++) {
            const [price, qty] = this.asks[i];
            const y = halfHeight - 15 - (i * rowHeight);
            const barWidth = (parseFloat(qty) / this.maxVolume) * (width * 0.6);

            // Ask depth bar
            this.ctx.fillStyle = 'rgba(255, 60, 100, 0.22)';
            this.ctx.fillRect(width - barWidth, y, barWidth, rowHeight - 2);

            // Ask price text
            this.ctx.fillStyle = '#ff4d6d';
            this.ctx.textAlign = 'left';
            this.ctx.fillText(Number(price).toLocaleString(), 10, y + rowHeight - 3);

            // Ask size text
            this.ctx.fillStyle = '#c0c8d8';
            this.ctx.textAlign = 'right';
            this.ctx.fillText(parseFloat(qty).toFixed(4), width - 10, y + rowHeight - 3);
        }

        // Render Spread Divider
        this.ctx.fillStyle = 'rgba(0, 240, 255, 0.15)';
        this.ctx.fillRect(0, halfHeight - 12, width, 24);
        this.ctx.fillStyle = '#00f0ff';
        this.ctx.textAlign = 'center';
        const bestAsk = this.asks[0] ? parseFloat(this.asks[0][0]) : 0;
        const bestBid = this.bids[0] ? parseFloat(this.bids[0][0]) : 0;
        const spread = (bestAsk - bestBid).toFixed(2);
        this.ctx.fillText(`SPREAD: ${spread} | LEVEL 2 DOM`, width / 2, halfHeight + 4);

        // Render Bids (Bottom half)
        for (let i = 0; i < this.bids.length; i++) {
            const [price, qty] = this.bids[i];
            const y = halfHeight + 15 + (i * rowHeight);
            const barWidth = (parseFloat(qty) / this.maxVolume) * (width * 0.6);

            // Bid depth bar
            this.ctx.fillStyle = 'rgba(0, 255, 170, 0.22)';
            this.ctx.fillRect(width - barWidth, y, barWidth, rowHeight - 2);

            // Bid price text
            this.ctx.fillStyle = '#00ffaa';
            this.ctx.textAlign = 'left';
            this.ctx.fillText(Number(price).toLocaleString(), 10, y + rowHeight - 3);

            // Bid size text
            this.ctx.fillStyle = '#c0c8d8';
            this.ctx.textAlign = 'right';
            this.ctx.fillText(parseFloat(qty).toFixed(4), width - 10, y + rowHeight - 3);
        }
    }
}

window.OrderbookCanvasRenderer = OrderbookCanvasRenderer;
