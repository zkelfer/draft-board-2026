/* Draft Board Sync — Yahoo draft room reader.
   Reads two lines the draft room always shows:
     "… Round R, Pick P …" (or "YOUR TURN • ROUND R, PICK P")  → the pick on the clock
     "Last: J. GIBBS (RB · DET) <Team name>"                     → the pick just made (P−1)
   Every pick is recorded with its REAL number and manager (your own picks included — Yahoo
   never toasts those). Your team name is learned the first time a pick is made on your turn.
   Result is stored for board.js to forward into the board tab, and reported to the optional
   local monitor. No guessing at Yahoo's obfuscated DOM. */
(function () {
  if (!/draftclient|draft|mock/i.test(location.href)) return;

  const room = { league: '', picks: [], cur: 0, me: '', myTurnAt: 0, updated: 0, url: location.href };

  function report(kind, data) {
    try {
      fetch('http://127.0.0.1:8738/report', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ kind, url: location.href, ...data }) }).catch(() => {});
    } catch (e) {}
  }
  function persist() {
    room.updated = Date.now();
    chrome.storage.local.set({ room });
  }

  function readRoom() {
    const text = (document.body.innerText || '').replace(/\s+/g, ' ');
    const lg = text.match(/FOOTBALL DRAFT\s+(.+?)\s+(?:\d{1,2}:\d{2}\b|\d+\s+(?:YOUR TURN|[A-Za-z]))/);
    if (lg) room.league = lg[1].trim();

    // pick on the clock
    let cur = 0, myTurn = false;
    let m = text.match(/YOUR TURN\s*[•·]\s*ROUND\s*(\d+),\s*PICK\s*(\d+)/i);
    if (m) { cur = +m[2]; myTurn = true; }
    else { m = text.match(/Round\s*(\d+),\s*Pick\s*(\d+)/i); if (m) cur = +m[2]; }
    if (cur) { room.cur = cur; if (myTurn) room.myTurnAt = cur; }

    // the pick just made
    let rec = null;
    m = text.match(/Last:\s*([A-Z])\.\s*([A-Z][A-Z' .-]*?)\s*\((QB|RB|WR|TE|K)\s*[·•-]\s*([A-Za-z]{2,3})\)\s*(.+?)\s*(?:DRAFT SCOUT|Subscribe|Queue|$)/);
    if (m) rec = { name: m[1] + '. ' + m[2].trim(), pos: m[3], team: m[4].toUpperCase(), by: m[5].trim(), abbrev: true };
    else {
      m = text.match(/Last:\s*([A-Z][A-Za-z' .-]+?)\s*\((DEF|DST)\s*[·•-]\s*([A-Za-z]{2,3})\)\s*(.+?)\s*(?:DRAFT SCOUT|Subscribe|Queue|$)/);
      if (m) rec = { name: m[1].trim(), pos: 'DEF', team: m[3].toUpperCase(), by: m[4].trim() };
    }
    if (!rec || !room.cur) return;
    rec.pick = room.cur - 1;
    if (rec.pick < 1) return;

    // learn my team name: the pick made on my turn carries it
    if (room.myTurnAt && rec.pick === room.myTurnAt && !room.me) room.me = rec.by;
    rec.mine = !!room.me && rec.by === room.me;

    const known = room.picks.find(p => p.pick === rec.pick);
    if (known) { if (known.name !== rec.name) Object.assign(known, rec); else return; }
    else room.picks.push(rec);
    room.picks.sort((a, b) => a.pick - b.pick);
    if (room.me) room.picks.forEach(p => { p.mine = p.by === room.me; });
    persist();
    console.log('[draft-board-sync] pick', rec.pick, rec.name, rec.pos, rec.team, 'by', rec.by, rec.mine ? '★' : '');
    report('room', { league: room.league, cur: room.cur, me: room.me, picks: room.picks });
  }

  // resume the pick list if this tab was reloaded mid-draft
  chrome.storage.local.get('room', r => {
    const prev = r && r.room;
    if (prev && prev.url === location.href && Array.isArray(prev.picks)) {
      room.picks = prev.picks; room.me = prev.me || ''; room.league = prev.league || '';
    }
    readRoom();
    setInterval(() => { try { readRoom(); } catch (e) { console.warn('[draft-board-sync]', e); } }, 1500);
    // keep the "pick on the clock" fresh even between picks
    setInterval(() => { const before = room.cur; try { readRoom(); } catch (e) {} if (room.cur !== before) persist(); }, 5000);
  });
})();
