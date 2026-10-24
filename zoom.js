(() => {
  const dialog = document.createElement('dialog');
  dialog.className = 'image-zoom';
  dialog.innerHTML = `<div class="zoom-toolbar"><span class="zoom-title"></span><a class="zoom-original" target="_blank" rel="noopener">原图 / Original ↗</a><button type="button" class="zoom-close" aria-label="关闭 / Close">×</button></div><img class="zoom-image" alt="">`;
  document.body.append(dialog);
  const preview = dialog.querySelector('.zoom-image');
  let trigger;
  const close = () => dialog.close();
  document.querySelectorAll('main img').forEach(img => {
    img.classList.add('zoomable');
    img.tabIndex = 0;
    img.setAttribute('role', 'button');
    img.setAttribute('aria-haspopup', 'dialog');
    img.setAttribute('aria-label', `${img.alt || 'SVG'} · 点击放大 / Zoom in`);
    const open = () => {
      trigger = img;
      preview.src = img.currentSrc || img.src;
      preview.alt = img.alt;
      dialog.querySelector('.zoom-title').textContent = img.alt || 'SVG';
      dialog.querySelector('.zoom-original').href = preview.src;
      dialog.showModal();
      document.documentElement.classList.add('zoom-open');
      dialog.querySelector('.zoom-close').focus();
    };
    img.addEventListener('click', open);
    img.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        open();
      }
    });
  });
  dialog.querySelector('.zoom-close').addEventListener('click', close);
  dialog.addEventListener('click', event => {
    if (event.target === dialog) close();
  });
  dialog.addEventListener('close', () => {
    preview.removeAttribute('src');
    document.documentElement.classList.remove('zoom-open');
    trigger?.focus({preventScroll: true});
  });
})();
