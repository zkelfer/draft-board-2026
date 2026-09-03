/* Draft Board Sync — Yahoo draft room content script.
   Scrapes the pick list every 5s and stores it in chrome.storage.local as
   {draft: {picks:[{pick,name,pos,team,mine}], league, updated, url}}.
   board.js (on the Draft Board tab) forwards that to the page.

   The Yahoo draft-room DOM is not documented, so scrape() uses several
   defensive strategies. If the board shows 0 picks during a live draft, open
   DevTools on this tab and copy the "[draft-board-sync] probe" console line —
   it lists the page's repeated class names and visible text, enough to tune
   the selectors below in minutes. */
(function () {
  if (!/draft|mock/i.test(location.href)) return;

  const POS   = /\b(QB|RB|WR|TE|K|DEF|DST)\b/;
  const TEAMS = /\b(ARI|ATL|BAL|BUF|CAR|CHI|CIN|CLE|DAL|DEN|DET|GB|HOU|IND|JAX|JAC|KC|LAC|LAR|LV|MIA|MIN|NE|NO|NYG|NYJ|PHI|PIT|SEA|SF|TB|TEN|WAS|WSH)\b/;
  const MINE  = /(^|[\s_-])(mine|owner|self|you|yours|my-?team)([\s_-]|$)/i;
  const cls = (el) => (el && el.getAttribute && el.getAttribute('class')) || '';

  const rowOf = (el) => {
    let n = el;
    for (let i = 0; n && n !== document.body && i < 8; i++) {
      if (n.tagName === 'TR' || n.tagName === 'LI') return n;
      if (/(^|[\s_-])(pick|player|row|result|selection)/i.test(cls(n))) return n;
      n = n.parentElement;
    }
    n = el;
    for (let i = 0; n && n.parentElement && n.parentElement !== document.body && i < 8; i++) {
      if (n.parentElement.children.length >= 3) return n;
      n = n.parentElement;
    }
    return el.parentElement || el;
  };

  const isMine = (row) => {
    let n = row;
    for (let i = 0; n && i < 4; i++) {
      if (MINE.test(cls(n))) return true;
      if (n.attributes)
        for (const a of n.attributes)
          if (MINE.test(a.name) || (a.name.indexOf('data-') === 0 && MINE.test(a.value))) return true;
      n = n.parentElement;
    }
    if (row.querySelectorAll)
      for (const el of row.querySelectorAll('[class]')) if (MINE.test(cls(el))) return true;
    return false;
  };

  const parse = (row, name) => {
    const text = ((row.innerText || row.textContent) || '').replace(/\s+/g, ' ').trim();
    let pick = 0, pos = '', team = '', m;
    m = text.match(/(?:Pick|#)\s*0*(\d{1,3})\b/i) || text.match(/^0*(\d{1,3})[.):\s]/);
    if (m) pick = parseInt(m[1], 10);
    m = text.match(/\b([A-Za-z]{2,3})\s*[-–—]\s*(QB|RB|WR|TE|K|DEF|DST)\b/i);
    if (m) { team = m[1]; pos = m[2]; }
    if (!pos) { m = text.match(/\b(QB|RB|WR|TE|K|DEF|DST)\s*[-–—]\s*([A-Za-z]{2,3})\b/i); if (m) { pos = m[1]; team = m[2]; } }
    if (!pos)  { m = text.match(POS);   if (m) pos = m[1]; }
    if (!team) { m = text.match(TEAMS); if (m) team = m[1]; }
    pos = pos.toUpperCase().replace('DST', 'DEF');
    return { pick, name, pos, team: team.toUpperCase(), mine: isMine(row) };
  };

  function scrape() {
    const picks = [], seen = new Set();
    const add = (rec) => { const k = rec.name.toLowerCase(); if (rec.name && !seen.has(k)) { seen.add(k); picks.push(rec); } };
    for (const a of document.querySelectorAll('a[href*="/nfl/players/"]')) {
      const name = ((a.innerText || a.textContent) || '').replace(/\s+/g, ' ').trim();
      if (name.length < 3 || name.length > 40 || !/[A-Za-z]{2}/.test(name)) continue;
      add(parse(rowOf(a), name));
    }
    if (picks.length === 0) {
      const rows = document.querySelectorAll("[class*='pick' i], [class*='result' i], [class*='selection' i], li, tr");
      for (const row of rows) {
        const text = ((row.innerText || '') + '').replace(/\s+/g, ' ').trim();
        if (!text || text.length > 160 || !POS.test(text)) continue;
        if (row.querySelector && row.querySelector('li, tr')) continue;
        const m = text.match(/([A-Z][\w.'-]+(?: [A-Z][\w.'-]+){1,2})/);
        if (!m) continue;
        add(parse(row, m[1]));
      }
    }
    const numbered = picks.filter(p => p.pick > 0).length;
    if (numbered >= picks.length / 2) picks.sort((a, b) => (a.pick || 9999) - (b.pick || 9999));
    picks.forEach((p, i) => { if (!p.pick) p.pick = i + 1; });
    let league = '';
    const lg = document.querySelector("[class*='league' i] h1, [class*='league' i] h2, [class*='leaguename' i], header h1");
    if (lg) league = (lg.innerText || '').trim();
    if (!league) league = (document.title || '').replace(/ [|–-] Yahoo.*$/i, '').trim();
    return { picks, league };
  }

  function probe() {
    const counts = {};
    for (const el of document.querySelectorAll('[class]'))
      for (const c of cls(el).split(/\s+/)) if (c) counts[c] = (counts[c] || 0) + 1;
    const top = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 40);
    return { url: location.href, title: document.title, classes: top,
             text: (document.body.innerText || '').replace(/\s+/g, ' ').slice(0, 3000) };
  }

  // optional local monitor (pipeline/sync_monitor.py); silently ignored when it isn't running
  function report(kind, data) {
    try {
      fetch('http://127.0.0.1:8738/report', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ kind, url: location.href, ...data }) }).catch(() => {});
    } catch (e) {}
  }

  let last = '';
  function tick() {
    try {
      const r = scrape();
      const j = JSON.stringify(r);
      if (j !== last) {
        last = j;
        chrome.storage.local.set({ draft: { ...r, updated: Date.now(), url: location.href } });
        console.log('[draft-board-sync]', r.picks.length, 'picks scraped');
        report('scrape', r);
      }
    } catch (e) { console.warn('[draft-board-sync] scrape failed', e); report('error', { error: String(e) }); }
  }
  tick();
  setInterval(tick, 5000);
  setTimeout(() => {
    const p = probe();
    console.log('[draft-board-sync] probe', JSON.stringify(p));
    chrome.storage.local.set({ probe: p });
    report('probe', p);
  }, 4000);
  setInterval(() => report('probe', probe()), 60000);
})();
