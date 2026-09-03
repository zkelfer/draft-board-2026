/* Draft Board Sync — board-page content script.
   Forwards the scraped draft (from chrome.storage.local, written by yahoo.js)
   into the page via window.postMessage; the board listens for
   {source:"draft-board-sync"} messages and marks players. */
(function () {
  function push(d) {
    if (!d) return;
    window.postMessage({ source: 'draft-board-sync', picks: d.picks || [], league: d.league || '',
                         updated: d.updated || 0 }, '*');
    // report what the board made of it to the optional local monitor
    setTimeout(() => {
      const st = document.getElementById('status');
      const gone = document.querySelectorAll('tr.gone').length, mine = document.querySelectorAll('tr.mine').length;
      try {
        fetch('http://127.0.0.1:8738/report', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ kind: 'board', status: st ? st.textContent : '', rowsGone: gone, rowsMine: mine,
                                 picksIn: (d.picks || []).length }) }).catch(() => {});
      } catch (e) {}
    }, 1500);
  }
  function pushRoom(rm) {
    if (!rm || !(rm.picks || []).length) return;
    window.postMessage({ source: 'draft-board-sync', leagues: { [rm.league || 'Draft room']: rm.picks }, updated: rm.updated || 0 }, '*');
  }
  chrome.storage.local.get(['draft', 'room'], r => { push(r.draft); pushRoom(r.room); });
  chrome.storage.onChanged.addListener((ch, area) => {
    if (area !== 'local') return;
    if (ch.draft) push(ch.draft.newValue);
    if (ch.room) pushRoom(ch.room.newValue);
  });
  window.addEventListener('message', e => {
    if (e.source === window && e.data && e.data.source === 'draft-board-page' && e.data.type === 'ping')
      chrome.storage.local.get(['draft', 'room'], r => { push(r.draft); pushRoom(r.room); });
  });
})();
