(() => {
  const root = document.querySelector('#run-browser');
  if (!root) return;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  root.innerHTML = `<h2>浏览测试轮次 / Browse runs</h2><p class="muted">选择账号区域、日期和挑战，查看每轮各模型的实际输出。图片可点击查看原图；时间均为 SGT。</p><div class="toolbar"><select aria-label="账号区域" id="run-region"><option value="">全部账号区域 / All regions</option><option value="Singapore">新加坡 / Singapore</option><option value="Philippines">菲律宾 / Philippines</option></select><input type="date" aria-label="测试日期" id="run-date"><select aria-label="挑战" id="run-variant"><option value="">全部挑战 / All challenges</option><option value="pelican">鹈鹕 / Pelican</option><option value="daily">每日挑战 / Daily</option><option value="legacy">早期挑战 / Legacy</option></select></div><div class="toolbar"><button id="run-older">← 上一轮 / Older</button><select id="run-select" aria-label="选择轮次" style="flex:1;min-width:0"></select><button id="run-newer">下一轮 / Newer →</button><button id="run-latest">最新 / Latest</button></div><p id="run-summary" aria-live="polite"></p><div id="run-gallery" class="grid"></div>`;
  const $ = id => root.querySelector('#run-'+id);
  fetch('stats.json').then(r => { if (!r.ok) throw Error(r.status); return r.json(); }).then(records => {
    const groups = new Map();
    records.forEach(r => { const id=r.round.replace(/-(pelican|daily)$/, ''); if(!groups.has(id)) groups.set(id,[]); groups.get(id).push(r); });
    const region = rows => rows[0].account_region || (rows[0].time_sgt >= '2026-10-29 22:44' ? 'Singapore' : 'Philippines');
    const ids = [...groups.keys()].sort().reverse();
    let visible = [], selected = new URLSearchParams(location.hash.slice(1)).get('run');
    function draw() {
      const rows = (groups.get(selected)||[]).filter(r => !$('variant').value || (r.variant||'legacy')===$('variant').value);
      const i = visible.indexOf(selected);
      $('select').value = selected || '';
      $('older').disabled = i < 0 || i >= visible.length-1;
      $('newer').disabled = i <= 0;
      $('summary').textContent = rows.length ? `${selected} · ${region(groups.get(selected))} · ${rows.filter(r=>r.status==='ok').length}/${rows.length} 成功 / passed · ${rows[0].time_sgt} SGT` : '没有符合筛选条件的轮次 / No matching runs';
      $('gallery').innerHTML = rows.map(r => `<figure class="card"><div class="art">${r.svg ? `<a href="${esc(r.svg)}" target="_blank" rel="noopener" style="display:block;width:100%;height:100%"><img src="${esc(r.svg)}" alt="${esc(r.model)} · ${esc(r.variant||'legacy')}" loading="lazy"></a>` : '<div class="noart">无图片 / No SVG</div>'}</div><figcaption><div><b>${esc(r.model)}</b><span class="${r.status==='ok'?'pass':'fail'}">${esc(r.status)}</span></div><small>${esc(r.variant||'legacy')} · ${esc(r.duration_s??'—')}s · ${esc(r.total_tokens??'—')} tokens<br>${esc(r.time_sgt)} SGT</small>${r.error ? `<p class="fail" style="overflow-wrap:anywhere">${esc(r.error)}</p>`:''}</figcaption></figure>`).join('');
      if(selected) history.replaceState(null,'','#'+new URLSearchParams({run:selected}));
    }
    function filter() {
      visible=ids.filter(id => {const rows=groups.get(id); return (!$('region').value||region(rows)===$('region').value)&&(!$('date').value||rows[0].time_sgt.startsWith($('date').value))&&(!$('variant').value||rows.some(r=>(r.variant||'legacy')===$('variant').value));});
      $('select').innerHTML=visible.map(id=>`<option value="${esc(id)}">${esc(id)} · ${region(groups.get(id))}</option>`).join('');
      if(!visible.includes(selected)) selected=visible[0];
      draw();
    }
    ['region','date','variant'].forEach(k=>$(k).onchange=filter);
    $('select').onchange=()=>{selected=$('select').value;draw();};
    $('older').onclick=()=>{selected=visible[visible.indexOf(selected)+1];draw();};
    $('newer').onclick=()=>{selected=visible[visible.indexOf(selected)-1];draw();};
    $('latest').onclick=()=>{selected=visible[0];draw();};
    filter();
  }).catch(() => { root.innerHTML='<p>轮次数据加载失败，请刷新重试。Unable to load runs; please refresh.</p>'; });
})();
