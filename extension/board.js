/* Draft Board Sync — board-page content script.
   Forwards the scraped draft (from chrome.storage.local, written by yahoo.js)
   into the page via window.postMessage; the board listens for
   {source:"draft-board-sync"} messages and marks players. */
(function () {
  function push(d) {
    if (!d) return;
    window.postMessage({ source: 'draft-board-sync', picks: d.picks || [], league: d.league || '',
                         updated: d.updated || 0 }, '*');
  }
  chrome.storage.local.get('draft', r => push(r.draft));
  chrome.storage.onChanged.addListener((ch, area) => { if (area === 'local' && ch.draft) push(ch.draft.newValue); });
  window.addEventListener('message', e => {
    if (e.source === window && e.data && e.data.source === 'draft-board-page' && e.data.type === 'ping')
      chrome.storage.local.get('draft', r => push(r.draft));
  });
})();
