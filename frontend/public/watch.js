(() => {
  function redact(s) {
    if (typeof s !== 'string') return s;
    return s.length > 140 ? s.slice(0, 140) + '…' : s;
  }
  function log(msg, obj) {
    try { console.log('[watch]', msg, obj || ''); } catch {}
  }

  const params = new URLSearchParams(window.location.search);
  const id = params.get('id');
  if (!id) { log('missing id'); return; }

  async function fetchPresignedUrl(sub, idToken) {
    const endpoint = 'https://api.videomk.com/users/' + encodeURIComponent(sub) + '/videos/' + encodeURIComponent(id);
    log('fetching presigned URL', { endpoint });
    const r = await fetch(endpoint, { headers: { Authorization: 'Bearer ' + idToken } });
    if (!r.ok) { log('presign failed', { status: r.status }); return null; }
    const j = await r.json();
    if (!j || !j.url) { log('no url in response'); return null; }
    log('received URL', { length: j.url.length, url: redact(j.url) });
    return j.url;
  }

  (async () => {
    let playUrl = null;
    try { playUrl = sessionStorage.getItem('vmk_play_url_' + id); } catch (e) { log('sessionStorage get failed', { error: String(e) }); }
    if (!playUrl) {
      let tokens = null;
      try { tokens = JSON.parse(localStorage.getItem('vmk_auth_tokens') || 'null'); } catch {}
      const idToken = tokens && tokens.id_token;
      if (!idToken) { log('missing id_token'); return; }
      let sub = null;
      try {
        const payload = JSON.parse(atob(idToken.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
        sub = payload && (payload.sub || payload['cognito:username']) || null;
      } catch {}
      if (!sub) { log('missing sub'); return; }
      playUrl = await fetchPresignedUrl(sub, idToken);
      if (!playUrl) return;
    }

    const videoEl = document.getElementById('video');
    const sourceEl = document.getElementById('source');
    if (!videoEl) { log('missing video element'); return; }
    log('setting video src', { url: redact(playUrl) });
    if (sourceEl) sourceEl.setAttribute('src', playUrl);
    videoEl.setAttribute('src', playUrl);
    try { if (sourceEl) sourceEl.setAttribute('type', 'video/mp4'); } catch {}
    if (videoEl.load) videoEl.load();

    videoEl.addEventListener('loadstart', () => log('event: loadstart', { src: redact(videoEl.currentSrc) }));
    videoEl.addEventListener('loadedmetadata', () => log('event: loadedmetadata', { duration: videoEl.duration, videoWidth: videoEl.videoWidth, videoHeight: videoEl.videoHeight }));
    videoEl.addEventListener('canplay', () => log('event: canplay'));
    videoEl.addEventListener('error', () => { const err = videoEl.error; log('event: error', { code: err && err.code, message: err && err.message, src: redact(videoEl.currentSrc) }); });
  })();
})();


