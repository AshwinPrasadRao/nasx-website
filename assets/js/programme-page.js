/* Takshashila programme page — interactive bits
   Persona tabs · Curriculum tracks/modules · FAQ accordion */

(function () {
  // Scope to the page's own masthead, NOT the shared document header
  // (includes/title-block.html) which is also .programme-page but carries
  // .doc-hero and is hidden — it renders first in the DOM, so a bare
  // '.programme-page' selector would bind handlers to that empty header and
  // leave the curriculum / persona / FAQ controls dead.
  const root = document.querySelector('.programme-page:not(.doc-hero)');
  if (!root) return;

  /* ─── Persona tabs ─────────────────────────────────────────── */
  const personaTabs  = root.querySelectorAll('.persona-tab');
  const personaPanes = root.querySelectorAll('.persona-pane');

  personaTabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const idx = tab.dataset.target;
      personaTabs.forEach(t => t.classList.toggle('is-active', t === tab));
      personaPanes.forEach(p => p.classList.toggle('is-active', p.dataset.pane === idx));
    });
  });

  /* ─── Curriculum: track + module switch ────────────────────── */
  const currTabs   = root.querySelectorAll('.curr-tab');
  const currMods   = root.querySelectorAll('.curr-mod');
  const currPanes  = root.querySelectorAll('.curr-pane');

  function showCurr(track, mod) {
    currTabs.forEach(t => t.classList.toggle('is-active', t.dataset.track === track));
    currMods.forEach(m => {
      const isThisTrack = m.dataset.track === track;
      m.hidden = !isThisTrack;
      const isActive = isThisTrack && m.dataset.mod === String(mod);
      m.classList.toggle('is-active', isActive);
      const dot = m.querySelector('.dot');
      if (dot) dot.textContent = isActive ? '●' : '○';
    });
    currPanes.forEach(p => {
      p.classList.toggle('is-active', p.dataset.track === track && p.dataset.mod === String(mod));
    });
  }

  currTabs.forEach(t => t.addEventListener('click', () => showCurr(t.dataset.track, 0)));
  currMods.forEach(m => m.addEventListener('click', () => showCurr(m.dataset.track, m.dataset.mod)));

  /* ─── FAQ accordion ────────────────────────────────────────── */
  root.querySelectorAll('.faq-item').forEach(item => {
    const q = item.querySelector('.faq-q');
    const toggle = item.querySelector('.toggle');
    if (!q) return;
    q.addEventListener('click', () => {
      const open = item.classList.toggle('is-open');
      if (toggle) toggle.textContent = open ? '[−]' : '[+]';
    });
  });
})();
