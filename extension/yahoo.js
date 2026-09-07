/* Draft Board Sync — Yahoo draft room reader.

   Primary path: parse the room's FULL pick list, which renders every pick as
       <pick #> / <manager, or "You"> / <Player> / [status tag] / <POS> / [Team] / Bye <n>
   The whole list is re-read every poll, so a pick can never be lost to sampling —
   anything missed earlier is backfilled on the next pass. Your own picks are
   labelled "You" by Yahoo, so they need no team-name guessing. (The old reader
   sampled the single "Last: …" line every 1500ms and lost ~13% of picks in a
   fast 14-team room — any pick overwritten inside one poll window vanished.)

   Fallback: that old single-line "Last: …" reader, used only if the list can't
   be found (Yahoo markup change). That path samples, and can miss fast picks. */
(function () {
  if (!/draftclient|draft|mock/i.test(location.href)) return;

  const room = { league: '', picks: [], cur: 0, me: '', myTurnAt: 0, updated: 0, url: location.href };

  function persist() {
    room.updated = Date.now();
    chrome.storage.local.set({ room });
  }

  const POS = /^(QB|RB|WR|TE|K|DEF|DST)$/;
  // Yahoo slots an injury/status chip between the name and the position
  const TAG = /^(Q|D|O|P|DTD|SUS|NA|IR|IR-R|IR-NFI|NFI|NFI-R|PUP|PUP-R|CEL)$/;

  /* Every pick currently rendered in the room's pick list. */
  function parsePickList(text) {
    const L = text.split('\n').map(s => s.trim()).filter(Boolean);
    const seen = {};
    for (let i = 0; i + 3 < L.length; i++) {
      if (!/^\d{1,3}$/.test(L[i])) continue;          // pick number, alone on its line
      const pick = +L[i];
      if (!pick || pick > 400) continue;
      const by = L[i + 1];                            // manager, or "You"
      if (!by || /\b(joined|left)$/.test(by) || POS.test(by) || /^Bye\b/.test(by)) continue;
      const name = L[i + 2];
      if (!name || /^\d/.test(name) || POS.test(name) || /^Bye\b/.test(name)) continue;

      let j = i + 3, pos = '';
      for (let g = 0; g < 3 && j < L.length; g++, j++) {   // skip status chips
        if (POS.test(L[j])) { pos = L[j]; j++; break; }
        if (!TAG.test(L[j])) break;
      }
      if (!pos) continue;
      let team = '';
      if (!/^Bye\b/.test(L[j] || '')) { team = L[j] || ''; j++; }
      if (!/^Bye\s*\d+/.test(L[j] || '')) continue;        // must close with the bye week
      // NOTE: team defenses render with no team code ("Texans / DEF / Bye 8") — that's
      // fine: the board resolves a DEF by its nickname via its NICK map (TEXANS -> def_HOU).

      // uppercase to match what the "Last:" path has always sent the board
      seen[pick] = { pick, by, name: name.toUpperCase(), pos: pos === 'DST' ? 'DEF' : pos,
                     team: team.toUpperCase(), abbrev: true, mine: by === 'You' };
    }
    return Object.keys(seen).map(Number).sort((a, b) => a - b).map(n => seen[n]);
  }
  // exposed for the fixture harness (data_private/ext_test.html); inert in the draft room
  try { window.__dbs_test = { parsePickList }; } catch (e) {}

  /* Legacy sampler — only if the list isn't there. Keeps its own team-name
     learning (room.me), so it still stars your picks if we ever fall back. */
  function readLastLine(flat) {
    let cur = 0, myTurn = false;
    let m = flat.match(/YOUR TURN\s*[•·]\s*ROUND\s*(\d+),\s*PICK\s*(\d+)/i);
    if (m) { cur = +m[2]; myTurn = true; }
    else { m = flat.match(/Round\s*(\d+),\s*Pick\s*(\d+)/i); if (m) cur = +m[2]; }
    if (cur) { room.cur = cur; if (myTurn) room.myTurnAt = cur; }

    let rec = null;
    m = flat.match(/Last:\s*([A-Z])\.\s*([A-Z][A-Z' .-]*?)\s*\((QB|RB|WR|TE|K)\s*[·•-]\s*([A-Za-z]{2,3})\)\s*(.+?)\s*(?:DRAFT SCOUT|Subscribe|Queue|$)/);
    if (m) rec = { name: m[1] + '. ' + m[2].trim(), pos: m[3], team: m[4].toUpperCase(), by: m[5].trim(), abbrev: true };
    else {
      m = flat.match(/Last:\s*([A-Z][A-Za-z' .-]+?)\s*\((DEF|DST)\s*[·•-]\s*([A-Za-z]{2,3})\)\s*(.+?)\s*(?:DRAFT SCOUT|Subscribe|Queue|$)/);
      if (m) rec = { name: m[1].trim(), pos: 'DEF', team: m[3].toUpperCase(), by: m[4].trim() };
    }
    if (!rec || !room.cur) return;
    rec.pick = room.cur - 1;
    if (rec.pick < 1) return;
    if (room.myTurnAt && rec.pick === room.myTurnAt && !room.me) room.me = rec.by;
    rec.mine = !!room.me && rec.by === room.me;
    upsert([rec]);
  }

  function upsert(list) {
    let changed = false;
    list.forEach(p => {
      const k = room.picks.find(q => q.pick === p.pick);
      if (!k) { room.picks.push(p); changed = true; }
      else if (k.name !== p.name || k.mine !== p.mine) { Object.assign(k, p); changed = true; }
    });
    if (!changed) return;
    room.picks.sort((a, b) => a.pick - b.pick);
    persist();
    const nums = room.picks.map(p => p.pick), top = Math.max.apply(null, nums), gaps = [];
    for (let i = 1; i < top; i++) if (nums.indexOf(i) < 0) gaps.push(i);
    console.log('[draft-board-sync]', room.picks.length, 'picks', gaps.length ? 'GAPS: ' + gaps.join(',') : '— complete');
  }

  function readRoom() {
    const text = document.body.innerText || '';
    const flat = text.replace(/\s+/g, ' ');
    const lg = flat.match(/FOOTBALL DRAFT\s+(.+?)\s+(?:\d{1,2}:\d{2}\b|\d+\s+(?:YOUR TURN|[A-Za-z]))/);
    if (lg) room.league = lg[1].trim();
    const m = flat.match(/Round\s*(\d+),\s*Pick\s*(\d+)/i);
    if (m) room.cur = +m[2];

    const list = parsePickList(text);
    if (list.length) upsert(list);
    else readLastLine(flat);
  }

  chrome.storage.local.get('room', r => {
    const prev = r && r.room;
    if (prev && prev.url === location.href && Array.isArray(prev.picks)) {
      room.picks = prev.picks; room.me = prev.me || ''; room.league = prev.league || '';
    }
    readRoom();
    setInterval(() => { try { readRoom(); } catch (e) { console.warn('[draft-board-sync]', e); } }, 1500);
  });
})();
