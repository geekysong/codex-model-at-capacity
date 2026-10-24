/* Subjective visual reviews, grouped by Singapore hour. Null is never a score. */
(() => {
  'use strict';
  const host = document.querySelector('#quality-monitor');
  if (!host) return;
  const colors = ['#6ee7f9', '#f7c66a', '#c9a7ff', '#73e2a3', '#ff7b86', '#ffac77', '#96b7ff', '#f1a6d6'];
  let data = null, selected = new Set(), range = '72', detailKey = null;
  const zh = () => document.body.classList.contains('zh');
  const t = (en, cn) => zh() ? cn : en;
  const el = (tag, text, cls) => {
    const n = document.createElement(tag);
    if (text != null) n.textContent = text;
    if (cls) n.className = cls;
    return n;
  };
  const hourOf = r => {
    const match = String(r.time_sgt || '').match(/^(\d{4}-\d{2}-\d{2})[ T](\d{2})/);
    return match ? `${match[1]}T${match[2]}:00:00+08:00` : null;
  };
  const scored = r => r.status === 'reviewed' && Number.isFinite(r.severity) && r.severity >= 0 && r.severity <= 4;
  const statusLabel = status => ({generation_error:t('Generation failed','生成失败'),render_error:t('SVG cannot render','SVG 无法渲染'),review_error:t('Review unavailable','评审未完成')})[status] || status;
  const labelHour = ms => new Intl.DateTimeFormat('en-GB', {timeZone:'Asia/Singapore', month:'2-digit', day:'2-digit', hour:'2-digit', hourCycle:'h23'}).format(new Date(ms));
  const sourceURL = value => {
    if (typeof value !== 'string' || !value) return null;
    try {
      const url = new URL(value, location.href);
      return url.origin === location.origin && /\.svg$/i.test(url.pathname) ? url.href : null;
    } catch { return null; }
  };
  const linkImage = (container, path, title) => {
    const href = sourceURL(path);
    if (!href) return;
    const link = el('a', title);
    link.href = href; link.target = '_blank'; link.rel = 'noopener';
    const img = el('img'); img.src = href; img.alt = title; img.loading = 'lazy';
    container.append(link, img);
  };
  function render() {
    host.replaceChildren();
    host.append(el('h2', t('Pelican quality over time', '鹈鹕绘图质量趋势'), 'quality-heading'));
    host.append(el('p', t('X = Singapore hour · Y = issue severity (0–4). Each point is the worst reviewed attempt for that model in that hour. Select a point to inspect every attempt.', 'X = 新加坡时间（小时）· Y = 问题程度（0–4）。每个点取该模型该小时内已评审结果的最高问题分。点击数据点查看每次尝试。'), 'quality-note'));
    host.append(el('p', t('0: matches the Astra reference · 1: minor flaws · 2: noticeable issues · 3: major issues · 4: unusable. This is a subjective visual check of bird shape, softness, cycling and overall clarity; it is not proof of model degradation. Missing reviews and generation failures have no visual score.', '0：符合 Astra 参考水平 · 1：轻微瑕疵 · 2：明显问题 · 3：严重问题 · 4：不可用。按鸟形、柔和度、骑车和整体清晰度进行主观视觉评审，分数不代表已证实模型降智。缺失评审和生成失败均不计作视觉分数。'), 'quality-note'));
    if (!data) { host.append(el('p', t('Quality reviews are not available yet.', '质量评审数据暂未就绪。'), 'muted')); return; }
    const baseline = data.baseline || {};
    const baselinePath = baseline.svg || baseline.path;
    if (sourceURL(baselinePath)) {
      const baselineLink = el('a', t('View fixed Astra reference ↗', '查看固定的 Astra 参考图 ↗'));
      baselineLink.href = sourceURL(baselinePath); baselineLink.target = '_blank'; baselineLink.rel = 'noopener'; host.append(baselineLink);
    }
    const raw = el('a', t('Review data (JSON)', '评审原始数据（JSON）'));
    raw.href = 'quality_reviews.json'; raw.style.marginLeft = '16px'; host.append(raw);
    if (data.updated_at) host.append(el('p', `${t('Updated','评审更新于')}: ${data.updated_at}`, 'quality-note'));
    const reviews = (data.reviews || []).filter(r => r.variant === 'pelican' && hourOf(r));
    if (!reviews.length) { host.append(el('p', t('No pelican reviews yet. Unreviewed images are not counted as healthy.', '暂无鹈鹕评审；未评审的图片不视为正常。'), 'muted')); return; }
    const models = [...new Set(reviews.map(r => r.model))].sort();
    const color = model => colors[models.indexOf(model) % colors.length];
    const controls = el('div', null, 'quality-controls');
    const rangeLabel = el('label', t('Show ', '显示 '));
    const rangeSelect = el('select');
    [['24', t('Last 24 hours','最近 24 小时')], ['72',t('Last 72 hours','最近 72 小时')], ['all',t('All hours','全部小时')]].forEach(([value, label]) => {const o = el('option', label); o.value = value; rangeSelect.append(o);});
    rangeSelect.value = range;
    rangeSelect.onchange = () => {range = rangeSelect.value; detailKey = null; render();};
    rangeLabel.append(rangeSelect); controls.append(rangeLabel); host.append(controls);
    const legend = el('div', null, 'quality-models');
    models.forEach(model => {
      const label = el('label'); label.style.setProperty('--series-color', color(model));
      const checkbox = el('input'); checkbox.type = 'checkbox'; checkbox.checked = selected.has(model);
      checkbox.onchange = () => {checkbox.checked ? selected.add(model) : selected.delete(model); detailKey = null; render();};
      label.append(checkbox, el('span', null, 'quality-swatch'), document.createTextNode(model)); legend.append(label);
    }); host.append(legend);
    const end = Math.max(...reviews.map(r => Date.parse(hourOf(r))));
    const first = Math.min(...reviews.map(r => Date.parse(hourOf(r))));
    const start = range === 'all' ? first : Math.max(first, end - (Number(range) - 1) * 3600000);
    const hours = Math.round((end - start) / 3600000) + 1;
    const groups = new Map();
    reviews.forEach(r => {
      const time = Date.parse(hourOf(r));
      if (time < start || !selected.has(r.model)) return;
      const key = `${time}|${r.model}`;
      if (!groups.has(key)) groups.set(key, {key, time, model:r.model, rows:[]});
      groups.get(key).rows.push(r);
    });
    groups.forEach(g => {g.scored = g.rows.filter(scored); g.severity = g.scored.length ? Math.max(...g.scored.map(r => r.severity)) : null;});
    const width = Math.max(680, host.clientWidth - 48, hours * 38 + 100), height = 310, left = 48, top = 22, bottom = 246;
    // Small horizontal offsets keep identical scores from hiding other models.
    const x = (time, model = null) => left + 15 + ((time - start) / 3600000) * ((width - left - 40) / Math.max(1, hours - 1)) + (model == null ? 0 : (models.indexOf(model) - (models.length - 1) / 2) * 3);
    const y = severity => bottom - severity * (bottom - top) / 4;
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`); svg.classList.add('quality-svg'); svg.style.minWidth = `${width}px`;
    svg.setAttribute('role','group'); svg.setAttribute('aria-label', t('Hourly pelican visual issue severity', '每小时鹈鹕视觉问题程度'));
    const shape = (tag, attrs, text) => {
      const n = document.createElementNS(svg.namespaceURI, tag);
      Object.entries(attrs).forEach(([key, value]) => n.setAttribute(key, value));
      if (text != null) n.textContent = text;
      svg.append(n); return n;
    };
    for (let s = 0; s <= 4; s++) {shape('line', {x1:left,y1:y(s),x2:width-15,y2:y(s),stroke:'#263241'});shape('text', {x:left-14,y:y(s)+4,'text-anchor':'end'}, s);}
    shape('line', {x1:left,y1:top,x2:left,y2:bottom,stroke:'#8b99a8'});
    for (let i = 0; i < hours; i++) {
      const time = start + i * 3600000;
      if (i % Math.max(1, Math.ceil(hours / 16)) === 0 || i === hours-1) shape('text', {x:x(time),y:bottom+23,transform:`rotate(-30 ${x(time)} ${bottom+23})`,'text-anchor':'end'}, labelHour(time));
    }
    const tooltip = el('p', t('Select a point to see SVGs and review reasons. × = no visual score.', '点击数据点查看 SVG 和评审理由。× = 无视觉评分。'), 'quality-tooltip');
    const summary = g => `${g.model} · ${labelHour(g.time)} SGT · ${g.severity == null ? t('no score','无评分') : `${g.severity}/4`} · ${g.scored.length}/${g.rows.length} ${t('reviewed','已评审')}`;
    models.filter(model => selected.has(model)).forEach(model => {
      let previous = null;
      [...groups.values()].filter(g => g.model === model).sort((a,b) => a.time-b.time).forEach(g => {
        if (g.severity != null && previous && g.time - previous.time === 3600000) shape('line', {x1:x(previous.time,model),y1:y(previous.severity),x2:x(g.time,model),y2:y(g.severity),stroke:color(model),'stroke-width':2});
        const dot = g.severity == null
          ? shape('path', {d:`M ${x(g.time,model)-4} ${bottom+51} l 8 8 m -8 0 l 8 -8`,stroke:color(model),'stroke-width':2,fill:'none'})
          : shape('circle', {cx:x(g.time,model),cy:y(g.severity),r:5,fill:color(model)});
        if (g.severity == null) dot.style.setProperty('--series-color',color(model));
        dot.classList.add('quality-point'); dot.setAttribute('tabindex','0'); dot.setAttribute('role','button'); dot.setAttribute('aria-label', summary(g));
        const title = document.createElementNS(svg.namespaceURI,'title'); title.textContent = summary(g); dot.append(title);
        dot.onmouseenter = dot.onfocus = () => {tooltip.textContent = summary(g);};
        dot.onclick = () => {detailKey=g.key; showDetails();};
        dot.onkeydown = e => {if (e.key === 'Enter' || e.key === ' ') {e.preventDefault(); dot.onclick();}};
        if (g.severity != null && g.rows.some(r => !scored(r))) {
          const missing = shape('path', {d:`M ${x(g.time,model)-4} ${bottom+51} l 8 8 m -8 0 l 8 -8`,stroke:color(model),'stroke-width':2,fill:'none'});
          missing.style.setProperty('--series-color',color(model));
          missing.classList.add('quality-point'); missing.setAttribute('tabindex','0'); missing.setAttribute('role','button');
          missing.setAttribute('aria-label', `${summary(g)} · ${t('Includes unscored attempt','包含无评分尝试')}`);
          missing.onclick = dot.onclick; missing.onkeydown = dot.onkeydown;
          missing.onmouseenter = missing.onfocus = () => {tooltip.textContent = missing.getAttribute('aria-label');};
        }
        previous = g.severity == null ? null : g;
      });
    });
    const scroll = el('div', null, 'quality-scroll'); scroll.append(svg); host.append(scroll, tooltip);
    const visible = [...groups.values()];
    const unscored = visible.reduce((n,g) => n + g.rows.filter(r => !scored(r)).length, 0);
    host.append(el('p', t(`${visible.length} model-hours · ${unscored} attempts without a visual score. Empty hours are gaps; lines do not bridge them.`, `${visible.length} 个模型小时记录 · ${unscored} 次尝试无视觉评分。空白小时保留为缺口，折线不跨越缺口。`), 'quality-note'));
    const accessible = el('details', null, 'quality-accessible'); accessible.append(el('summary', t('Hourly data table / keyboard alternative', '每小时数据表 / 键盘操作入口')));
    const tableScroll = el('div', null, 'table-wrap'), table = el('table'), head = el('thead'), row = el('tr');
    [t('Hour (SGT)','小时（SGT）'),t('Model','模型'),t('Worst issue score','最高问题分'),t('Reviewed / attempts','已评审 / 尝试'),t('Details','详情')].forEach(label => row.append(el('th',label)));
    head.append(row); table.append(head); const body = el('tbody');
    visible.sort((a,b) => b.time-a.time || a.model.localeCompare(b.model)).forEach(g => {
      const tr = el('tr'); [labelHour(g.time),g.model,g.severity == null ? '—' : g.severity,`${g.scored.length}/${g.rows.length}`].forEach(value=>tr.append(el('td',value)));
      const td = el('td'), button = el('button',t('Inspect','查看')); button.onclick=()=>{detailKey=g.key;showDetails();};td.append(button);tr.append(td);body.append(tr);
    }); table.append(body);tableScroll.append(table);accessible.append(tableScroll);host.append(accessible);
    const details = el('div', null, 'quality-details'); details.setAttribute('aria-live','polite'); host.append(details);
    function showDetails() {
      details.replaceChildren(); const group = groups.get(detailKey); if (!group) return;
      details.append(el('h3',summary(group)));
      const grid = el('div',null,'quality-reviews');
      group.rows.forEach(r => {
        const card = el('article',null,'quality-review');card.append(el('h4',`${r.model} · ${r.time_sgt}`));
        card.append(el('p',scored(r) ? t(`Issue severity: ${r.severity}/4 · confidence: ${Number.isFinite(r.confidence) ? Math.round(r.confidence*100)+'%' : '—'}`,`问题程度：${r.severity}/4 · 置信度：${Number.isFinite(r.confidence) ? Math.round(r.confidence*100)+'%' : '—'}`) : `${t('No visual score','无视觉评分')} · ${statusLabel(r.status)}`,scored(r)?null:'quality-missing'));
        const reasons=el('ul');(r.reasons||[]).forEach(reason=>reasons.append(el('li',reason)));card.append(reasons);
        if (r.dimensions) card.append(el('p',Object.entries(r.dimensions).map(([key,value]) => `${({bird_shape:t('Bird shape','鸟形'),softness:t('Softness','柔和度'),riding:t('Cycling','骑车'),readability:t('Clarity','清晰度')})[key] || key}: ${value == null ? '—' : value+'/4'}`).join(' · ')));
        linkImage(card,r.svg,t('Open source SVG ↗','打开原始 SVG ↗'));
        card.append(el('p',`${r.round} · ${r.judge || '—'}`));card.append(el('small',`${t('Review time','评审时间')}: ${r.reviewed_at || '—'} · ${data.rubric_version || '—'}`));grid.append(card);
      });details.append(grid);
    }
    showDetails();
  }
  render();
  fetch('quality_reviews.json', {cache:'no-cache'}).then(response => {
    if (!response.ok) throw new Error('reviews unavailable');return response.json();
  }).then(result => {
    if (result.schema_version !== 1 || !Array.isArray(result.reviews)) throw new Error('unsupported schema');
    data=result;selected=new Set(data.reviews.map(r=>r.model));render();
  }).catch(()=>{data=null;render();});
  new MutationObserver(render).observe(document.body,{attributes:true,attributeFilter:['class']});
  let resizeTimer;
  window.addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(render,100);});
})();
