/* Draft Board Sync — board-page content script.
   Forwards the draft room's pick list (written by yahoo.js) into the page via
   window.postMessage; the board listens for {source:"draft-board-sync"} messages. */
(function () {
  function pushRoom(rm) {
    if (!rm || !(rm.picks || []).length) return;
    const league = rm.league || 'Draft room';
    window.postMessage({ source: 'draft-board-sync', leagues: { [league]: rm.picks },
                         cur: { [league]: rm.cur || 0 }, newest: league, me: rm.me || '', updated: rm.updated || 0 }, '*');
    setTimeout(() => {
      const st = document.getElementById('status');
      try {
        fetch('http://127.0.0.1:8738/report', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ kind: 'board', status: st ? st.textContent : '',
                                 rowsGone: document.querySelectorAll('tr.gone').length,
                                 rowsMine: document.querySelectorAll('tr.mine').length,
                                 picksIn: (rm.picks || []).length, cur: rm.cur || 0 }) }).catch(() => {});
      } catch (e) {}
    }, 1500);
  }
  chrome.storage.local.get('room', r => pushRoom(r.room));
  chrome.storage.onChanged.addListener((ch, area) => { if (area === 'local' && ch.room) pushRoom(ch.room.newValue); });
  window.addEventListener('message', e => {
    if (e.source !== window || !e.data || e.data.source !== 'draft-board-page') return;
    if (e.data.type === 'ping')
      chrome.storage.local.get('room', r => pushRoom(r.room));
    else if (e.data.type === 'clear')
      // "Clear this draft" on the board: drop the cached room so old picks never replay.
      // (A live Yahoo tab will simply re-persist as new picks happen — that's a real draft.)
      chrome.storage.local.remove('room', () => console.log('[draft-board-sync] room cache cleared by board'));
  });
})();
