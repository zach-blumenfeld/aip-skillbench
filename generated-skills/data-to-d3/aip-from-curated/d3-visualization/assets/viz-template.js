/* __HEADER_COMMENT__ */
(function () {
  'use strict';

  const CONFIG = __CONFIG__;
  const EMBEDDED_ROWS = __ROWS__;
  const EMBEDDED_SERIES = __SERIES__;

  const state = { selected: null, data: [] };

  // ---------- formatting ----------
  function formatAbbrev(num) {
    if (num === null || num === undefined || num === '' || isNaN(+num)) return CONFIG.table.missing_text;
    num = +num;
    const absNum = Math.abs(num);
    let formatted;
    if (absNum >= 1e12) formatted = (absNum / 1e12).toFixed(2) + 'T';
    else if (absNum >= 1e9) formatted = (absNum / 1e9).toFixed(2) + 'B';
    else if (absNum >= 1e6) formatted = (absNum / 1e6).toFixed(2) + 'M';
    else if (absNum >= 1e3) formatted = (absNum / 1e3).toFixed(2) + 'K';
    else formatted = absNum.toFixed(2);
    return num < 0 ? '-' + formatted : formatted;
  }

  function isMissing(v) {
    return v === null || v === undefined || (typeof v === 'string' && v.trim() === '') ||
      (typeof v === 'number' && isNaN(v));
  }

  function formatValue(v, fmt) {
    if (isMissing(v)) return CONFIG.table.missing_text;
    switch (fmt) {
      case 'abbrev': return formatAbbrev(v);
      case 'number': return d3.format(',.2f')(+v);
      case 'integer': return d3.format(',d')(Math.round(+v));
      case 'percent': return d3.format('.2%')(+v);
      case 'currency': return d3.format('$,.2f')(+v);
      case 'currency_abbrev': return (+v < 0 ? '-$' : '$') + formatAbbrev(Math.abs(+v));
      default: return String(v);
    }
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  // ---------- data ----------
  function prepare(rows) {
    const sizeField = CONFIG.bubble.size_field;
    return rows.map(r => {
      const d = Object.assign({}, r);
      d.key = String(r[CONFIG.key]);
      const v = r[sizeField];
      d.value = isMissing(v) || isNaN(+v) ? null : +v;
      d.hasValue = d.value !== null;
      return d;
    });
  }

  function excludedFromTooltip(d) {
    return (CONFIG.tooltip.exclude || []).some(rule => {
      const v = d[rule.field];
      if (rule.missing) return isMissing(v);
      if (Object.prototype.hasOwnProperty.call(rule, 'equals')) return String(v) === String(rule.equals);
      if (rule.in) return rule.in.map(String).includes(String(v));
      return false;
    });
  }

  // ---------- tooltip (CSS .visible class toggles opacity) ----------
  const tooltip = d3.select('#tooltip').empty()
    ? d3.select('body').append('div').attr('id', 'tooltip').attr('class', 'tooltip')
    : d3.select('#tooltip');

  function tooltipHtml(d) {
    return CONFIG.tooltip.fields.map((f, i) => {
      const val = escapeHtml(formatValue(d[f.field], f.format));
      const text = f.label ? `${escapeHtml(f.label)}: ${val}` : val;
      return (f.bold || (i === 0 && f.bold !== false)) ? `<strong>${text}</strong>` : text;
    }).join('<br/>');
  }

  function showTooltip(event, d) {
    if (excludedFromTooltip(d)) return;  // conditional interactivity: no tooltip for excluded rows
    tooltip.classed('visible', true)
      .html(tooltipHtml(d))
      .style('left', (event.pageX + 10) + 'px')
      .style('top', (event.pageY - 10) + 'px');
  }

  function moveTooltip(event) {
    if (tooltip.classed('visible')) {
      tooltip.style('left', (event.pageX + 10) + 'px').style('top', (event.pageY - 10) + 'px');
    }
  }

  function hideTooltip() {
    tooltip.classed('visible', false);
  }

  // ---------- bubble chart ----------
  function legendLayout(domain, width, margin) {
    const items = [];
    let x = margin.left, y = margin.top, rows = domain.length ? 1 : 0;
    domain.forEach(label => {
      const w = 22 + String(label).length * 7 + 14;
      if (x + w > width - margin.right && x > margin.left) { x = margin.left; y += 20; rows += 1; }
      items.push({ label, x, y });
      x += w;
    });
    return { items, height: rows ? rows * 20 + 8 : 0 };
  }

  function renderBubbles(data) {
    const B = CONFIG.bubble;
    const W = B.width, H = B.height, m = B.margin;
    const colorDomain = Array.from(new Set(data.map(d => String(d[B.color_field])))).sort();
    const palette = colorDomain.length <= 10 ? d3.schemeCategory10
      : d3.quantize(t => d3.interpolateRainbow(t * (colorDomain.length - 1) / colorDomain.length), colorDomain.length);
    const color = d3.scaleOrdinal().domain(colorDomain).range(palette);

    const legend = B.legend ? legendLayout(colorDomain, W, m) : { items: [], height: 0 };
    const plot = { x0: m.left, y0: m.top + legend.height, x1: W - m.right, y1: H - m.bottom };
    const pw = plot.x1 - plot.x0, ph = plot.y1 - plot.y0;

    // radius: sqrt scale on the size field; rows without a value get a uniform radius
    let range = B.radius_range.slice();
    let missingR = B.missing_radius;
    const maxV = d3.max(data, d => d.value || 0) || 1;
    const rScale = d3.scaleSqrt().domain([0, maxV]).range(range);
    data.forEach(d => { d.radius = d.hasValue ? rScale(d.value) : missingR; });
    // shrink everything if the bubbles cannot fit without overlap (packing density cap)
    const density = d3.sum(data, d => Math.PI * Math.pow(d.radius + B.padding, 2)) / (pw * ph);
    if (density > B.max_density) {
      const k = Math.sqrt(B.max_density / density);
      data.forEach(d => { d.radius = +(d.radius * k).toFixed(2); });
    }

    const clusters = Array.from(new Set(data.map(d => String(d[B.cluster_field])))).sort();
    const cx = plot.x0 + pw / 2, cy = plot.y0 + ph / 2;
    const ring = clusters.length > 1 ? Math.min(B.cluster_ring, 0.32 * Math.min(pw, ph)) : 0;
    const centers = {};
    clusters.forEach((c, i) => {
      const angle = -Math.PI / 2 + (i / clusters.length) * 2 * Math.PI;
      centers[c] = { x: cx + Math.cos(angle) * ring * (pw / Math.min(pw, ph)) * 0.95, y: cy + Math.sin(angle) * ring };
    });

    // deterministic node order and initial positions (no Math.random)
    const nodes = data.slice().sort((a, b) =>
      d3.ascending(String(a[B.cluster_field]), String(b[B.cluster_field])) ||
      d3.descending(a.radius, b.radius) || d3.ascending(a.key, b.key));
    const perCluster = {};
    nodes.forEach(n => {
      const c = String(n[B.cluster_field]);
      const i = perCluster[c] = (perCluster[c] || 0) + 1;
      const a = i * 2.39996323, r = 6 * Math.sqrt(i);
      n.x = centers[c].x + r * Math.cos(a);
      n.y = centers[c].y + r * Math.sin(a);
    });

    function bounds() {
      nodes.forEach(n => {
        n.x = Math.max(plot.x0 + n.radius, Math.min(plot.x1 - n.radius, n.x));
        n.y = Math.max(plot.y0 + n.radius, Math.min(plot.y1 - n.radius, n.y));
      });
    }

    const sim = d3.forceSimulation(nodes)
      .force('x', d3.forceX(d => centers[String(d[B.cluster_field])].x).strength(B.cluster_strength))
      .force('y', d3.forceY(d => centers[String(d[B.cluster_field])].y).strength(B.cluster_strength))
      .force('charge', d3.forceManyBody().strength(B.charge))
      .force('collide', d3.forceCollide(d => d.radius + B.padding).strength(1).iterations(3))
      .force('bounds', bounds)
      .stop();
    for (let i = 0; i < B.ticks; i++) sim.tick();
    // collision-only relaxation removes residual overlap; still a fixed number of ticks
    sim.force('x', d3.forceX(d => centers[String(d[B.cluster_field])].x).strength(0.02))
      .force('y', d3.forceY(d => centers[String(d[B.cluster_field])].y).strength(0.02))
      .force('charge', null).alpha(0.5);
    for (let i = 0; i < B.relax_ticks; i++) sim.tick();
    nodes.forEach(n => { n.x = +n.x.toFixed(2); n.y = +n.y.toFixed(2); });

    const svg = d3.select('#chart').append('svg')
      .attr('id', 'bubble-chart')
      .attr('width', W).attr('height', H)
      .attr('viewBox', `0 0 ${W} ${H}`)
      .attr('xmlns', 'http://www.w3.org/2000/svg');

    if (B.legend) {
      const lg = svg.append('g').attr('class', 'legend');
      const item = lg.selectAll('g.legend-item').data(legend.items).join('g')
        .attr('class', 'legend-item')
        .attr('transform', d => `translate(${d.x},${d.y})`);
      item.append('circle').attr('cx', 7).attr('cy', 8).attr('r', 7).attr('fill', d => color(d.label));
      item.append('text').attr('x', 20).attr('y', 12).attr('class', 'legend-label').text(d => d.label);
    }

    const g = svg.append('g').attr('class', 'bubbles');
    g.selectAll('circle.bubble')
      .data(nodes, d => d.key)
      .join('circle')
      .attr('class', 'bubble')
      .attr('data-key', d => d.key)
      .attr(`data-${CONFIG.key_attr}`, d => d.key)
      .attr('data-group', d => String(d[B.color_field]))
      .attr('cx', d => d.x)
      .attr('cy', d => d.y)
      .attr('r', d => d.radius)
      .attr('fill', d => color(String(d[B.color_field])))
      .attr('fill-opacity', 0.7)
      .on('mouseover', (event, d) => showTooltip(event, d))
      .on('mousemove', event => moveTooltip(event))
      .on('mouseout', hideTooltip)
      .on('click', (event, d) => selectKey(d.key));

    if (B.label_field) {
      g.selectAll('text.bubble-label')
        .data(nodes, d => d.key)
        .join('text')
        .attr('class', 'bubble-label')
        .attr('x', d => d.x)
        .attr('y', d => d.y)
        .attr('dy', '0.35em')
        .attr('text-anchor', 'middle')
        .style('font-size', d => Math.max(7, Math.min(14, d.radius / 2.1)).toFixed(1) + 'px')
        .text(d => d[B.label_field]);
    }
  }

  // ---------- table ----------
  function renderTable(data) {
    const T = CONFIG.table;
    const container = d3.select('#table-container');
    const table = container.append('table').attr('id', 'data-table');
    const headerRow = table.append('thead').append('tr');
    const tbody = table.append('tbody');
    let rows = data.slice();
    if (T.sort_by) rows.sort((a, b) => compare(a, b, T.sort_by, T.sort_ascending !== false));
    let sortKey = T.sort_by || null, sortAscending = T.sort_ascending !== false;

    function compare(a, b, key, asc) {
      const av = a[key], bv = b[key];
      const am = isMissing(av), bm = isMissing(bv);
      if (am || bm) return am && bm ? d3.ascending(a.key, b.key) : (am ? 1 : -1);  // missing last
      const r = (typeof av === 'number' && typeof bv === 'number') ? av - bv : String(av).localeCompare(String(bv), 'en');
      return (asc ? r : -r) || d3.ascending(a.key, b.key);
    }

    headerRow.selectAll('th').data(T.columns).join('th')
      .attr('data-field', d => d.field)
      .attr('class', T.sortable ? 'sortable' : null)
      .text(d => d.label)
      .on('click', (event, col) => {
        if (!T.sortable) return;
        if (sortKey === col.field) sortAscending = !sortAscending; else { sortKey = col.field; sortAscending = true; }
        rows.sort((a, b) => compare(a, b, sortKey, sortAscending));
        headerRow.selectAll('th').attr('aria-sort', c => c.field === sortKey ? (sortAscending ? 'ascending' : 'descending') : null);
        draw();
      });

    function draw() {
      const tr = tbody.selectAll('tr').data(rows, d => d.key).join('tr')
        .attr('data-key', d => d.key)
        .attr(`data-${CONFIG.key_attr}`, d => d.key)
        .classed('selected', d => d.key === state.selected)
        .classed('highlighted', d => d.key === state.selected)
        .on('click', (event, d) => selectKey(d.key));
      tr.order();
      tr.selectAll('td').data(d => T.columns.map(c => ({ value: d[c.field], col: c })))
        .join('td')
        .attr('class', d => (d.col.format && d.col.format !== 'text') ? 'num' : null)
        .text(d => formatValue(d.value, d.col.format));
    }
    draw();
  }

  // ---------- optional time-series detail ----------
  function renderSeries(key) {
    if (!CONFIG.series) return;
    const S = CONFIG.series;
    const host = d3.select('#series-chart');
    host.selectAll('*').remove();
    const pts = (EMBEDDED_SERIES || {})[key];
    if (!pts || !pts.length) {
      host.append('p').attr('class', 'series-empty').text(key ? `No ${S.value_column} history for ${key}` : S.placeholder);
      return;
    }
    const W = S.width, H = S.height, m = { top: 28, right: 20, bottom: 30, left: 56 };
    const parse = d3.timeParse('%Y-%m-%d');
    const series = pts.map(p => ({ date: parse(p[0]), value: p[1] }));
    const x = d3.scaleUtc().domain(d3.extent(series, d => d.date)).range([m.left, W - m.right]);
    const y = d3.scaleLinear().domain(d3.extent(series, d => d.value)).nice().range([H - m.bottom, m.top]);
    const svg = host.append('svg').attr('id', 'series-svg').attr('width', W).attr('height', H).attr('viewBox', `0 0 ${W} ${H}`);
    const col = (S.columns_used && S.columns_used[key]) || S.value_column;
    svg.append('text').attr('class', 'series-title').attr('x', m.left).attr('y', 16).text(`${key} — ${col}`);
    const spanYears = (x.domain()[1] - x.domain()[0]) / (365.25 * 864e5);
    const tickFmt = d3.utcFormat(spanYears > 4 ? '%Y' : '%b %Y');
    svg.append('g').attr('transform', `translate(0,${H - m.bottom})`).call(d3.axisBottom(x).ticks(6).tickFormat(tickFmt));
    svg.append('g').attr('transform', `translate(${m.left},0)`).call(d3.axisLeft(y).ticks(5));
    svg.append('path').datum(series).attr('class', 'series-line')
      .attr('d', d3.line().x(d => +x(d.date).toFixed(2)).y(d => +y(d.value).toFixed(2)));
  }

  // ---------- linking ----------
  function selectKey(key) {
    if (!CONFIG.link) return;
    state.selected = key;
    d3.selectAll('#bubble-chart circle.bubble')
      .classed('selected', d => d.key === key)
      .classed('highlighted', d => d.key === key);
    d3.selectAll('#data-table tbody tr')
      .classed('selected', d => d && d.key === key)
      .classed('highlighted', d => d && d.key === key);
    const row = d3.select(`#data-table tbody tr[data-key="${CSS.escape(key)}"]`);
    if (!row.empty() && row.node().scrollIntoView) row.node().scrollIntoView({ block: 'nearest' });
    renderSeries(key);
  }
  // names used by the original examples, exposed for external callers/tests
  window.selectBubble = selectKey;
  window.highlightBubble = selectKey;
  window.highlightTableRow = selectKey;
  window.selectRow = selectKey;

  function start(rows) {
    const data = prepare(rows);
    state.data = data;
    renderBubbles(data);
    renderTable(data);
    renderSeries(null);
    document.body.setAttribute('data-rendered', 'true');
  }

  if (EMBEDDED_ROWS && EMBEDDED_ROWS.length) {
    // embedded copy of CONFIG.data_url: renders synchronously and also works from file://
    start(EMBEDDED_ROWS);
  } else {
    d3.csv(CONFIG.data_url).then(rows => {
      rows.forEach(r => CONFIG.numeric_fields.forEach(f => { r[f] = isMissing(r[f]) ? null : +r[f]; }));
      start(rows);
    });
  }
})();
