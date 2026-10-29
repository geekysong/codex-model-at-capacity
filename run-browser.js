(() => {
  const root = document.querySelector('#run-browser');
  if (!root) return;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  root.innerHTML = `<style>@media(min-width:1200px){body:has(#run-browser) main{max-width:none;width:100%;padding-inline:28px}}.run-comparisons{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,520px),1fr));gap:18px;align-items:start}.run-comparison{min-width:0}.run-comparison h3{margin:8px 0;font-size:14px}.run-comparison .run-pair{margin-bottom:0}@media(min-width:1800px){.run-comparisons{grid-template-columns:repeat(auto-fit,minmax(540px,1fr))}}.run-pair{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin:12px 0 24px}.run-pair .card{min-width:0}.run-pair .art{height:clamp(120px,27dvh,320px);aspect-ratio:auto}.run-pair img{width:100%;height:100%;object-fit:contain}#run-browser select{max-width:100%;min-width:0}#run-browser{scroll-margin-top:8px}#run-gallery{touch-action:pan-y}.run-pair figcaption{padding:7px 9px}.run-pair figcaption b{font-size:12px}.run-pair figcaption small{font-size:11px}.run-pair h3{margin:8px 0}#run-gallery>.run-pair:first-child{position:sticky;top:0;z-index:2;background:#121923;padding:8px 0;font-size:12px}@media(max-width:600px){#run-browser{padding:10px}.run-pair{gap:6px;margin:6px 0 12px}.run-pair .art{height:clamp(120px,24dvh,230px)}.run-pair figcaption div{flex-wrap:wrap}.run-pair figcaption{padding:6px}.run-pair figcaption b{font-size:10px}#run-browser .toolbar{gap:5px;margin-bottom:6px}#run-browser input{min-width:0;width:130px;flex:0 1 auto}#run-browser select{font-size:12px;padding:6px}#run-browser h2{font-size:17px}}</style><h2>双轮次并排比较 / Compare runs side by side</h2><p class="muted">左侧按账号区域和日期筛选轮次，右侧独立选择对照轮次；相同模型和挑战左右对齐。左右滑动 / 鼠标拖动 / 触控板横滑切换对应一侧；← → 切换左侧，Shift + ← → 切换右侧。点击图片放大。时间均为 SGT。</p><div class="toolbar"><select aria-label="账号区域" id="run-region"><option value="">全部账号区域 / All regions</option><option value="Singapore">新加坡 / Singapore</option><option value="Philippines">菲律宾 / Philippines</option></select><input type="date" aria-label="测试日期" id="run-date"><select aria-label="挑战" id="run-variant"><option value="">全部挑战 / All challenges</option><option value="pelican">鹈鹕 / Pelican</option><option value="daily">每日挑战 / Daily</option><option value="legacy">早期挑战 / Legacy</option></select></div><div class="toolbar"><button id="run-older">← 上一轮 / Older</button><select id="run-select" aria-label="选择轮次" style="flex:1;min-width:0"></select><button id="run-newer">下一轮 / Newer →</button><button id="run-latest">最新 / Latest</button></div><div class="toolbar"><label>右侧对照 / Compare with <select id="run-compare" aria-label="右侧对照轮次"></select></label></div><p id="run-summary" aria-live="polite"></p><div id="run-gallery" class="grid"></div>`;
  const $ = id => root.querySelector('#run-'+id);
  fetch('stats.json').then(r => { if (!r.ok) throw Error(r.status); return r.json(); }).then(records => {
    const groups = new Map();
    records.forEach(r => { const id=r.round.replace(/-(pelican|daily)$/, ''); if(!groups.has(id)) groups.set(id,[]); groups.get(id).push(r); });
    const region = rows => rows[0].account_region || (rows[0].time_sgt >= '2026-10-29 22:44' ? 'Singapore' : 'Philippines');
    const ids = [...groups.keys()].sort().reverse();
    let visible = [], selected = new URLSearchParams(location.hash.slice(1)).get('run');
    const params = new URLSearchParams(location.hash.slice(1));
    if (!groups.has(selected)) selected = ids[0];
    const initialLeft = groups.get(selected);
    let comparison = params.get('compare') || ids.find(id => region(groups.get(id)) !== region(initialLeft)) || ids[1] || ids[0];
    if (!groups.has(comparison)) comparison = ids[0];
    $('compare').innerHTML = ids.map(id=>`<option value="${esc(id)}">${esc(id)} · ${region(groups.get(id))}</option>`).join('');
    $('compare').value = comparison;
    const key = r => `${r.variant||'legacy'} / ${r.model}`;
    const card = r => !r ? '<div class="card noart">该轮无此模型或挑战 / No matching attempt</div>' : `<figure class="card"><div class="art">${r.svg ? `<a href="${esc(r.svg)}" target="_blank" rel="noopener" style="display:block;width:100%;height:100%"><img src="${esc(r.svg)}" alt="${esc(key(r))}" loading="lazy"></a>` : '<div class="noart">无图片 / No SVG</div>'}</div><figcaption><div><b>${esc(r.model)}</b><span class="${r.status==='ok'?'pass':'fail'}">${esc(r.status)}</span></div><small>${esc(r.duration_s??'—')}s · ${esc(r.total_tokens??'—')} tokens<br>${esc(r.time_sgt)} SGT</small>${r.error ? `<p class="fail errtxt" style="overflow-wrap:anywhere">${esc(r.error)}</p>`:''}</figcaption></figure>`;
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
      $('gallery').innerHTML = `<div class="run-pair"><b>左 / Left · ${esc(selected||'—')}<br>${rows.length?region(groups.get(selected)):''}</b><b>右 / Right · ${esc(comparison)}<br>${region(groups.get(comparison))}</b></div>` + '<div class="run-comparisons">' + keys.map(k => {
        const leftRow=rows.find(r=>key(r)===k), rightRow=right.find(r=>key(r)===k);
        const mismatch=leftRow && rightRow && leftRow.prompt_sha && rightRow.prompt_sha && leftRow.prompt_sha!==rightRow.prompt_sha;
        return `<article class="run-comparison"><h3>${esc(k)}</h3>${mismatch?'<p class="muted">两轮题目不同 / Different prompts in these runs</p>':''}<div class="run-pair">${card(leftRow)}${card(rightRow)}</div></article>`;
      }).join('') + '</div>';
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
    function step(delta, rightSide=false) {
      const list=rightSide?ids:visible, current=rightSide?comparison:selected;
      const next=list[list.indexOf(current)+delta];
      if(!next)return;
      if(rightSide){comparison=next;$('compare').value=next;}else selected=next;
      draw();
    }
    let gesture;
    $('gallery').addEventListener('touchstart',e=>{if(e.touches.length===1){const t=e.touches[0],box=$('gallery').getBoundingClientRect();gesture={x:t.clientX,y:t.clientY,right:t.clientX>box.left+box.width/2};}else gesture=null;},{passive:true});
    let suppressClickUntil=0;
    $('gallery').addEventListener('touchend',e=>{if(!gesture)return;const t=e.changedTouches[0],dx=t.clientX-gesture.x,dy=t.clientY-gesture.y;if(Math.abs(dx)>60&&Math.abs(dx)>Math.abs(dy)*1.5){suppressClickUntil=Date.now()+500;step(dx<0?-1:1,gesture.right);}gesture=null;},{passive:true});
    $('gallery').addEventListener('click',e=>{if(Date.now()<suppressClickUntil){e.preventDefault();e.stopPropagation();}},true);
    root.addEventListener('keydown',e=>{if(e.target.closest('input,select,button,a')||document.querySelector('dialog[open]'))return;if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();step(e.key==='ArrowLeft'?1:-1,e.shiftKey);}});
    root.tabIndex=0;
    let mouse;
    $('gallery').addEventListener('dragstart',e=>e.preventDefault());
    $('gallery').addEventListener('pointerdown',e=>{if(e.pointerType==='mouse'&&e.button===0){const box=$('gallery').getBoundingClientRect();mouse={x:e.clientX,y:e.clientY,right:e.clientX>box.left+box.width/2};}});
    window.addEventListener('pointerup',e=>{if(!mouse)return;const dx=e.clientX-mouse.x,dy=e.clientY-mouse.y;if(Math.abs(dx)>60&&Math.abs(dx)>Math.abs(dy)*1.5){suppressClickUntil=Date.now()+500;step(dx<0?-1:1,mouse.right);}mouse=null;});
    $('gallery').addEventListener('touchcancel',()=>{gesture=null;},{passive:true});
    let lastWheel=0;
    $('gallery').addEventListener('wheel',e=>{if(Math.abs(e.deltaX)>Math.abs(e.deltaY)&&Math.abs(e.deltaX)>12){e.preventDefault();if(Date.now()-lastWheel>650){const box=$('gallery').getBoundingClientRect();step(e.deltaX>0?-1:1,e.clientX>box.left+box.width/2);lastWheel=Date.now();}}},{passive:false});
    filter();
  }).catch(() => { root.innerHTML='<p>轮次数据加载失败，请刷新重试。Unable to load runs; please refresh.</p>'; });
})();
