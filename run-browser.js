(() => {
  const root = document.querySelector('#run-browser');
  if (!root) return;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  root.innerHTML = `<style>.run-pair{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin:12px 0 24px}.run-pair .card{min-width:0}.run-pair .art{height:clamp(180px,30vw,440px);aspect-ratio:auto}.run-pair img{width:100%;height:100%;object-fit:contain}#run-browser select{max-width:100%}</style><h2>双轮次并排比较 / Compare runs side by side</h2><p class="muted">左侧按账号区域和日期筛选轮次，右侧独立选择对照轮次；相同模型和挑战左右对齐。图片可点击查看原图；时间均为 SGT。</p><div class="toolbar"><select aria-label="账号区域" id="run-region"><option value="">全部账号区域 / All regions</option><option value="Singapore">新加坡 / Singapore</option><option value="Philippines">菲律宾 / Philippines</option></select><input type="date" aria-label="测试日期" id="run-date"><select aria-label="挑战" id="run-variant"><option value="">全部挑战 / All challenges</option><option value="pelican">鹈鹕 / Pelican</option><option value="daily">每日挑战 / Daily</option><option value="legacy">早期挑战 / Legacy</option></select></div><div class="toolbar"><button id="run-older">← 上一轮 / Older</button><select id="run-select" aria-label="选择轮次" style="flex:1;min-width:0"></select><button id="run-newer">下一轮 / Newer →</button><button id="run-latest">最新 / Latest</button></div><div class="toolbar"><label>右侧对照 / Compare with <select id="run-compare" aria-label="右侧对照轮次"></select></label></div><p id="run-summary" aria-live="polite"></p><div id="run-gallery" class="grid"></div>`;
  const $ = id => root.querySelector('#run-'+id);
  fetch('stats.json').then(r => { if (!r.ok) throw Error(r.status); return r.json(); }).then(records => {
    const groups = new Map();
    records.forEach(r => { const id=r.round.replace(/-(pelican|daily)$/, ''); if(!groups.has(id)) groups.set(id,[]); groups.get(id).push(r); });
    const region = rows => rows[0].account_region || (rows[0].time_sgt >= '2026-10-29 22:44' ? 'Singapore' : 'Philippines');
    const ids = [...groups.keys()].sort().reverse();
    let visible = [], selected = new URLSearchParams(location.hash.slice(1)).get('run');
    const params = new URLSearchParams(location.hash.slice(1));
    const initialLeft = groups.get(selected || ids[0]);
    let comparison = params.get('compare') || ids.find(id => region(groups.get(id)) !== region(initialLeft)) || ids[1] || ids[0];
    if (!groups.has(comparison)) comparison = ids[0];
    $('compare').innerHTML = ids.map(id=>`<option value="${esc(id)}">${esc(id)} · ${region(groups.get(id))}</option>`).join('');
    $('compare').value = comparison;
    const key = r => `${r.variant||'legacy'} / ${r.model}`;
    const card = r => !r ? '<div class="card noart">该轮无此模型或挑战 / No matching attempt</div>' : `<figure class="card"><div class="art">${r.svg ? `<a href="${esc(r.svg)}" target="_blank" rel="noopener" style="display:block;width:100%;height:100%"><img src="${esc(r.svg)}" alt="${esc(key(r))}" loading="lazy"></a>` : '<div class="noart">无图片 / No SVG</div>'}</div><figcaption><div><b>${esc(r.model)}</b><span class="${r.status==='ok'?'pass':'fail'}">${esc(r.status)}</span></div><small>${esc(r.duration_s??'—')}s · ${esc(r.total_tokens??'—')} tokens<br>${esc(r.time_sgt)} SGT</small>${r.error ? `<p class="fail" style="overflow-wrap:anywhere">${esc(r.error)}</p>`:''}</figcaption></figure>`;
    $('gallery').className = '';
    $('compare').onchange = () => { comparison=$('compare').value; draw(); };
    function draw() {
      const rows = (groups.get(selected)||[]).filter(r => !$('variant').value || (r.variant||'legacy')===$('variant').value);
      const i = visible.indexOf(selected);
      $('select').value = selected || '';
      $('older').disabled = i < 0 || i >= visible.length-1;
      $('newer').disabled = i <= 0;
      $('summary').textContent = rows.length ? `${selected} · ${region(groups.get(selected))} · ${rows.filter(r=>r.status==='ok').length}/${rows.length} 成功 / passed · ${rows[0].time_sgt} SGT` : '没有符合筛选条件的轮次 / No matching runs';
      const right = (groups.get(comparison)||[]).filter(r => !$('variant').value || (r.variant||'legacy')===$('variant').value);
      const keys = [...new Set([...rows,...right].map(key))].sort();
      $('gallery').innerHTML = `<div class="run-pair"><b>左 / Left · ${esc(selected||'—')}<br>${rows.length?region(groups.get(selected)):''}</b><b>右 / Right · ${esc(comparison)}<br>${region(groups.get(comparison))}</b></div>` + keys.map(k => {
        const leftRow=rows.find(r=>key(r)===k), rightRow=right.find(r=>key(r)===k);
        const mismatch=leftRow && rightRow && leftRow.prompt_sha && rightRow.prompt_sha && leftRow.prompt_sha!==rightRow.prompt_sha;
        return `<h3>${esc(k)}</h3>${mismatch?'<p class="muted">两轮题目不同 / Different prompts in these runs</p>':''}<div class="run-pair">${card(leftRow)}${card(rightRow)}</div>`;
      }).join('');
      if(selected) history.replaceState(null,'','#'+new URLSearchParams({run:selected,compare:comparison}));
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
