(() => {
  const dialog = document.createElement('dialog');
  dialog.className = 'image-zoom';
  dialog.innerHTML = `<div class="zoom-toolbar"><span class="zoom-title"></span><button data-zoom="out" aria-label="缩小">−</button><button data-zoom="fit">适合屏幕</button><button data-zoom="in" aria-label="放大">＋</button><a class="zoom-original" target="_blank" rel="noopener">原图 ↗</a><button class="zoom-close" aria-label="关闭">×</button></div><div class="zoom-stage"><img class="zoom-image" alt="" draggable="false"></div><small>滚轮 / 双指缩放 · 拖动查看 · Esc 关闭</small>`;
  document.body.append(dialog);
  const preview = dialog.querySelector('img'), stage=dialog.querySelector('.zoom-stage');
  let trigger, scale=1, x=0, y=0, pinch;
  const pointers=new Map();
  const paint=()=>{preview.style.transform=`translate(${x}px,${y}px) scale(${scale})`;};
  const resize=value=>{scale=Math.min(8,Math.max(1,value));if(scale===1)x=y=0;paint();};
  const open=img=>{
    trigger=img; preview.src=img.currentSrc||img.src;preview.alt=img.alt;
    dialog.querySelector('.zoom-title').textContent=img.alt||'SVG';
    dialog.querySelector('a').href=preview.src;
    scale=1;x=y=0;paint();dialog.showModal();document.documentElement.classList.add('zoom-open');
    dialog.querySelector('.zoom-close').focus();
  };
  // Delegation also handles images inserted by the asynchronous run browser.
  document.addEventListener('click',e=>{const img=e.target.closest('main img');if(img){e.preventDefault();open(img);}});
  document.addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target.matches('main img')){e.preventDefault();open(e.target);}});
  const prepare=()=>document.querySelectorAll('main img:not(.zoomable)').forEach(img=>{img.classList.add('zoomable');img.tabIndex=0;img.setAttribute('role','button');img.setAttribute('aria-haspopup','dialog');img.setAttribute('aria-label',`${img.alt||'SVG'} · 点击放大`);});
  prepare();new MutationObserver(prepare).observe(document.querySelector('main'),{childList:true,subtree:true});
  dialog.querySelector('.zoom-close').onclick=()=>dialog.close();
  dialog.querySelector('[data-zoom="in"]').onclick=()=>resize(scale*1.4);
  dialog.querySelector('[data-zoom="out"]').onclick=()=>resize(scale/1.4);
  dialog.querySelector('[data-zoom="fit"]').onclick=()=>resize(1);
  stage.addEventListener('wheel',e=>{e.preventDefault();resize(scale*Math.exp(-e.deltaY*.002));},{passive:false});
  stage.addEventListener('dblclick',()=>resize(scale===1?2:1));
  stage.onpointerdown=e=>{stage.setPointerCapture(e.pointerId);pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});pinch=null;};
  stage.onpointermove=e=>{
    if(!pointers.has(e.pointerId))return;
    const old=pointers.get(e.pointerId);pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});
    if(pointers.size===2){const [a,b]=[...pointers.values()];const distance=Math.hypot(a.x-b.x,a.y-b.y);if(pinch)resize(scale*distance/pinch);pinch=distance;}
    else if(scale>1){x+=e.clientX-old.x;y+=e.clientY-old.y;paint();}
  };
  stage.onpointerup=stage.onpointercancel=e=>{pointers.delete(e.pointerId);pinch=null;};
  dialog.onclick=e=>{if(e.target===dialog)dialog.close();};
  dialog.addEventListener('close',()=>{preview.removeAttribute('src');pointers.clear();document.documentElement.classList.remove('zoom-open');if(trigger?.isConnected)trigger.focus({preventScroll:true});});
})();
