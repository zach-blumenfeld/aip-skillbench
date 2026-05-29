# Interactivity patterns

Load this when the task requires tooltips, click-to-select, hover highlights, or any other D3 interaction. The body of `SKILL.md` summarises *when* to apply each pattern; this file holds the canonical CSS/JS to paste.

## Tooltip pattern (recommended)

### 1. Markup

```html
<div id="tooltip" class="tooltip"></div>
```

### 2. CSS — class-based visibility

```css
.tooltip {
    position: absolute;
    padding: 10px;
    background: rgba(0, 0, 0, 0.8);
    color: white;
    border-radius: 4px;
    pointer-events: none;  /* Prevent mouse interference */
    opacity: 0;
    transition: opacity 0.2s;
    z-index: 1000;
}

.tooltip.visible {
    opacity: 1;  /* Show when .visible class is added */
}
```

### 3. JS — handlers on the D3 selection

```javascript
svg.selectAll('circle')
    .on('mouseover', function(event, d) {
        d3.select('#tooltip')
            .classed('visible', true)
            .html(`<strong>${d.name}</strong><br/>${d.value}`)
            .style('left', (event.pageX + 10) + 'px')
            .style('top', (event.pageY - 10) + 'px');
    })
    .on('mouseout', function() {
        d3.select('#tooltip').classed('visible', false);
    });
```

### Key points
- Use `opacity: 0` by default (not `display: none`) so the transition stays smooth.
- Toggle visibility with `.classed('visible', true/false)`.
- `pointer-events: none` keeps the tooltip from intercepting mouse events.
- Position relative to the mouse via `event.pageX/pageY`.

## Click handlers for selection / highlighting

```javascript
svg.selectAll('.bar')
    .on('click', function(event, d) {
        d3.selectAll('.bar').classed('selected', false);
        d3.select(this).classed('selected', true);
    });
```

```css
.bar.selected {
    stroke: #000;
    stroke-width: 3px;
}
```

## Conditional interactivity

Sometimes only certain elements should react. Early-return from the handler instead of attaching it selectively:

```javascript
.on('mouseover', function(event, d) {
    if (d.category === 'excluded') return;
    showTooltip(event, d);
})
```

## Reusable handler

For multi-chart pages or richer formatting, lift `TooltipHandler` from `scripts/tooltip_handler.js`. It accepts `selector`, `offsetX/Y`, `shouldShow(d)`, and `formatContent(d)` options, and exposes `.show(event, d)`, `.hide()`, `.move(event)`, and `.attach(selection)`.

## Worked examples in `scripts/`

- `scripts/bubble_chart_example.js` — clustered force-directed bubbles with conditional tooltips and click-driven selection.
- `scripts/interactive_table_example.js` — sortable table linked two-way to the chart via `selectRow` / `highlightTableRow`.
- `scripts/tooltip_handler.js` — the reusable `TooltipHandler` class and four usage patterns.
- `scripts/check_tooltip.js` — runtime sanity checks for tooltip wiring (element exists, `.visible` toggles, content matches data).
