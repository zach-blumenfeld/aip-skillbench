/*
 * Linked sector bubble chart + data table (D3.js v6).
 *
 * Defaults chosen at build time (documented here per the determinism rules):
 * - Data is loaded with d3.csv from data/<descriptions file>; if that fetch fails
 *   (e.g. the page is opened from file://, where browsers block fetch), the same
 *   rows embedded below at build time are used, so the page always renders.
 * - Rows are sorted by sector then ticker before binding; sectors are sorted
 *   alphabetically with the no-market-cap group (ETF) last.
 * - Bubble area ~ market cap (d3.scaleSqrt); rows without a market cap (ETFs)
 *   get one uniform radius. Radii are auto-shrunk until the layout fits the SVG.
 * - Force layout is deterministic: sector anchors are packed with d3.packSiblings,
 *   nodes start on a fixed spiral around their sector's anchor, forceX/forceY pull them to the anchor, forceCollide
 *   prevents overlap, the simulation is stopped and ticked exactly N times, and
 *   the result is re-centred in the plot area. No Math.random, no transitions.
 */
(function () {
    'use strict';

    const CONFIG = __APP_CONFIG__;
    const EMBEDDED_ROWS = __EMBEDDED_ROWS__;
    // upper-cased ticker -> 'data/<price dir>/<file>.csv' (for custom price panels; unused by default)
    const PRICE_FILES = CONFIG.priceFiles || {};

    const WIDTH = CONFIG.width;
    const HEIGHT = CONFIG.height;
    const PAD = 8;
    const TICKS = 400;

    // ---------- data ----------

    function toNumber(v) {
        if (v === null || v === undefined) return null;
        const s = String(v).trim();
        if (s === '' || s.toLowerCase() === 'nan') return null;
        const n = +s;
        return Number.isFinite(n) && n > 0 ? n : null;
    }

    function normalize(raw) {
        const c = CONFIG.columns;
        return raw.map(r => {
            const marketCap = toNumber(r[c.marketCap]);
            const sector = (r[c.sector] || '').trim() || 'Unknown';
            return {
                ticker: (r[c.ticker] || '').trim(),
                name: (r[c.name] || '').trim(),
                sector: sector,
                marketCap: marketCap,
                country: c.country ? (r[c.country] || '').trim() : '',
                website: c.website ? (r[c.website] || '').trim() : '',
                // ETFs: no market cap / country / website -> uniform size, no tooltip
                isETF: sector.toUpperCase() === 'ETF' || marketCap === null
            };
        }).filter(d => d.ticker !== '');
    }

    function sortRows(rows, sectors) {
        const order = new Map(sectors.map((s, i) => [s, i]));
        return rows.slice().sort((a, b) =>
            (order.get(a.sector) - order.get(b.sector)) || d3.ascending(a.ticker, b.ticker));
    }

    function sectorOrder(rows) {
        const all = Array.from(new Set(rows.map(d => d.sector)));
        const isNoCap = s => rows.filter(d => d.sector === s).every(d => d.isETF);
        const regular = all.filter(s => !isNoCap(s)).sort(d3.ascending);
        const noCap = all.filter(isNoCap).sort(d3.ascending);
        return regular.concat(noCap);
    }

    // "1.64T", "193.22B", "5.93B", "850.00M"; missing -> "N/A"
    function formatMarketCap(num) {
        if (num === null || num === undefined || !Number.isFinite(num)) return 'N/A';
        const a = Math.abs(num);
        if (a >= 1e12) return (num / 1e12).toFixed(2) + 'T';
        if (a >= 1e9) return (num / 1e9).toFixed(2) + 'B';
        if (a >= 1e6) return (num / 1e6).toFixed(2) + 'M';
        if (a >= 1e3) return (num / 1e3).toFixed(2) + 'K';
        return num.toFixed(2);
    }

    // ---------- selection linking ----------

    function selectTicker(ticker, scrollRow) {
        d3.selectAll('.bubble')
            .classed('selected', d => d.ticker === ticker);
        d3.selectAll('#data-table tbody tr')
            .classed('selected', d => d.ticker === ticker);
        if (scrollRow) {
            const row = document.querySelector('#data-table tbody tr[data-ticker="' + CSS.escape(ticker) + '"]');
            if (row && row.scrollIntoView) row.scrollIntoView({block: 'nearest'});
        }
    }
    // exposed for the linking hooks used by the example scripts
    window.highlightTableRow = t => selectTicker(t, true);
    window.highlightBubble = t => selectTicker(t, false);

    // ---------- tooltip ----------

    const tooltip = d3.select('#tooltip');

    function showTooltip(event, d) {
        if (d.isETF) return;   // ETFs have no marketCap/country/website: no tooltip
        tooltip
            .classed('visible', true)
            .html('<strong>' + escapeHtml(d.ticker) + '</strong><br/>' +
                  escapeHtml(d.name || 'N/A') + '<br/>' +
                  'Sector: ' + escapeHtml(d.sector))
            .style('left', (event.pageX + 10) + 'px')
            .style('top', (event.pageY - 10) + 'px');
    }
    function moveTooltip(event, d) {
        if (d.isETF) return;
        tooltip.style('left', (event.pageX + 10) + 'px').style('top', (event.pageY - 10) + 'px');
    }
    function hideTooltip() { tooltip.classed('visible', false); }

    function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g, ch =>
            ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[ch]));
    }

    // ---------- legend (inside the SVG, own band at the top) ----------

    function drawLegend(svg, sectors, color) {
        const items = [];
        let x = PAD, y = PAD + 8, rowH = 20;
        sectors.forEach(s => {
            const w = 18 + s.length * 7 + 16;
            if (x + w > WIDTH - PAD && x > PAD) { x = PAD; y += rowH; }
            items.push({sector: s, x: x, y: y});
            x += w;
        });
        const g = svg.append('g').attr('class', 'legend');
        const item = g.selectAll('g.legend-item')
            .data(items)
            .join('g')
            .attr('class', 'legend-item')
            .attr('data-sector', d => d.sector)
            .attr('transform', d => 'translate(' + d.x + ',' + d.y + ')');
        item.append('circle').attr('r', 6).attr('cx', 6).attr('cy', 0).attr('fill', d => color(d.sector));
        item.append('text').attr('x', 18).attr('y', 0).text(d => d.sector);
        return y + rowH / 2 + 6;   // bottom of the legend band
    }

    // ---------- bubble layout ----------

    function layout(nodes, sectors, area) {
        const cx = area.x + area.w / 2, cy = area.y + area.h / 2;
        const caps = nodes.filter(d => !d.isETF).map(d => d.marketCap);
        const maxCap = d3.max(caps) || 1;

        // relative radii: area ~ market cap; no-cap rows (ETFs) share one uniform radius
        const base = d3.scaleSqrt().domain([0, maxCap]).range([0, 1]);
        const rel = nodes.map(d => d.isETF ? null : base(d.marketCap));
        const etfRel = d3.median(rel.filter(v => v !== null)) || 0.3;
        const minRel = 0.18;   // keeps the smallest bubbles big enough for a ticker label
        const relR = rel.map(v => v === null ? Math.max(etfRel, minRel) : Math.max(v, minRel));
        const sumSq = d3.sum(relR, r => r * r) || 1;
        // start with total bubble area ~ 32% of the plot area, then shrink until it fits
        let k = Math.sqrt(0.32 * area.w * area.h / (Math.PI * sumSq));

        // Sector anchors: one circle per sector, sized to that sector's packed cluster
        // (sum of its bubble areas at ~62% density) plus a small gap, tightly packed
        // with d3.packSiblings (deterministic: largest first, ties by name) and centred
        // on the plot centre. Neighbouring clusters touch without mixing, whatever the
        // number of sectors or how unequal they are.
        function anchorsFor(scale) {
            const gap = 8;
            const circles = sectors.map(s => {
                const sq = d3.sum(nodes, (d, i) => d.sector === s ? Math.pow(relR[i] * scale, 2) : 0);
                return {sector: s, r: Math.sqrt(sq / 0.62) + gap / 2};
            }).sort((a, b) => (b.r - a.r) || d3.ascending(a.sector, b.sector));
            d3.packSiblings(circles);
            const enc = d3.packEnclose(circles);
            return new Map(circles.map(c => [c.sector, {x: cx + c.x - enc.x, y: cy + c.y - enc.y}]));
        }

        for (let attempt = 0; attempt < 10; attempt++) {
            const anchor = anchorsFor(k);
            nodes.forEach((d, i) => {
                d.radius = relR[i] * k;
                const a = anchor.get(d.sector);
                const t = i * 2.399963;              // golden-angle spiral: distinct, deterministic starts
                const rr = 4 + 3 * Math.sqrt(i);
                d.x = a.x + Math.cos(t) * rr;
                d.y = a.y + Math.sin(t) * rr;
                d.vx = 0; d.vy = 0;
            });
            const sim = d3.forceSimulation(nodes)
                .force('x', d3.forceX(d => anchor.get(d.sector).x).strength(0.2))
                .force('y', d3.forceY(d => anchor.get(d.sector).y).strength(0.2))
                .force('collide', d3.forceCollide(d => d.radius + 1.5).strength(1).iterations(4))
                .stop();
            for (let i = 0; i < TICKS; i++) sim.tick();
            // final collision-only passes so no two bubbles overlap
            sim.force('x', null).force('y', null).alpha(0.3);
            for (let i = 0; i < 60; i++) sim.tick();

            const x0 = d3.min(nodes, d => d.x - d.radius), x1 = d3.max(nodes, d => d.x + d.radius);
            const y0 = d3.min(nodes, d => d.y - d.radius), y1 = d3.max(nodes, d => d.y + d.radius);
            const bw = x1 - x0, bh = y1 - y0;
            if (bw <= area.w && bh <= area.h) {
                // re-centre the whole cluster set in the plot area
                const dx = cx - (x0 + x1) / 2, dy = cy - (y0 + y1) / 2;
                nodes.forEach(d => { d.x += dx; d.y += dy; });
                return;
            }
            k *= 0.97 * Math.min(area.w / bw, area.h / bh);
        }
        // last resort: clamp into the plot area
        nodes.forEach(d => {
            d.x = Math.max(area.x + d.radius, Math.min(area.x + area.w - d.radius, d.x));
            d.y = Math.max(area.y + d.radius, Math.min(area.y + area.h - d.radius, d.y));
        });
    }

    function drawBubbles(rows, sectors) {
        const color = d3.scaleOrdinal()
            .domain(sectors)
            .range(CONFIG.palette.concat(d3.schemeTableau10));

        const svg = d3.select('#chart')
            .append('svg')
            .attr('id', 'bubble-chart')
            .attr('width', WIDTH)
            .attr('height', HEIGHT)
            .attr('viewBox', '0 0 ' + WIDTH + ' ' + HEIGHT);

        const legendBottom = drawLegend(svg, sectors, color);
        const area = {x: PAD, y: legendBottom + PAD, w: WIDTH - 2 * PAD, h: HEIGHT - legendBottom - 2 * PAD};

        const nodes = rows.map(d => Object.assign({}, d));
        layout(nodes, sectors, area);

        const node = svg.append('g').attr('class', 'bubbles')
            .selectAll('g.node')
            .data(nodes, d => d.ticker)
            .join('g')
            .attr('class', 'node')
            .attr('transform', d => 'translate(' + d.x.toFixed(2) + ',' + d.y.toFixed(2) + ')');

        node.append('circle')
            .attr('class', d => 'bubble' + (d.isETF ? ' etf' : ''))
            .attr('data-ticker', d => d.ticker)
            .attr('data-sector', d => d.sector)
            .attr('r', d => d.radius.toFixed(2))
            .attr('fill', d => color(d.sector))
            .on('mouseover', showTooltip)
            .on('mousemove', moveTooltip)
            .on('mouseout', hideTooltip)
            .on('click', (event, d) => selectTicker(d.ticker, true));

        node.append('text')
            .attr('class', 'bubble-label')
            .attr('font-size', d => Math.max(7, Math.min(16, d.radius * 1.7 / Math.max(2.2, d.ticker.length * 0.62))).toFixed(1) + 'px')
            .text(d => d.ticker);

        return color;
    }

    // ---------- table ----------

    function drawTable(rows, color) {
        const columns = [
            {label: 'Ticker symbol', value: d => d.ticker},
            {label: 'Full company name', value: d => d.name},
            {label: 'Sector', value: d => d.sector, swatch: true},
            {label: 'Market cap', value: d => formatMarketCap(d.marketCap), num: true}
        ];
        const container = d3.select('#table-container').style('max-height', (HEIGHT - 10) + 'px');
        const table = container.append('table').attr('id', 'data-table');
        table.append('thead').append('tr')
            .selectAll('th').data(columns).join('th')
            .attr('class', c => c.num ? 'num' : null)
            .text(c => c.label);

        const tr = table.append('tbody')
            .selectAll('tr').data(rows, d => d.ticker).join('tr')
            .attr('data-ticker', d => d.ticker)
            .on('click', (event, d) => selectTicker(d.ticker, false));

        tr.selectAll('td')
            .data(d => columns.map(c => ({c: c, d: d})))
            .join('td')
            .attr('class', x => x.c.num ? 'num' : null)
            .each(function (x) {
                const td = d3.select(this);
                if (x.c.swatch) td.append('span').attr('class', 'swatch').style('background', color(x.d.sector));
                td.append('span').text(x.c.value(x.d));
            });
    }

    // ---------- boot ----------

    function render(raw) {
        const rows0 = normalize(raw);
        const sectors = sectorOrder(rows0);
        const rows = sortRows(rows0, sectors);
        const color = drawBubbles(rows, sectors);
        drawTable(rows, color);
        document.body.setAttribute('data-rendered', 'true');
    }

    d3.csv(CONFIG.dataPath)
        .then(raw => {
            if (!raw || raw.length === 0) throw new Error('empty CSV');
            render(raw);
        })
        .catch(err => {
            console.warn('d3.csv(' + CONFIG.dataPath + ') failed (' + err + '); using embedded rows.');
            render(EMBEDDED_ROWS);
        });
})();
