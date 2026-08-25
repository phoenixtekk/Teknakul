// Teknakul Go — browser/phone WebRTC (WHIP) go-live page.
// Captures camera+mic, asks the restream API to create a live (returns the WHIP url),
// publishes via WHIP to the gateway (which pushes it into Teknakul), and — if the
// creator is Pro — the restream engine fans it out to every destination. Registers a
// /p/go route + a "Go Live" menu link.
async function register ({ registerHook, registerClientRoute, peertubeHelpers }) {
  const SKY = '#3ebdf8'
  const API = (window.TEKNAKUL_RESTREAM_API || 'https://restream.teknakul.com').replace(/\/$/, '')

  registerHook({
    target: 'filter:left-menu.links.create.result',
    handler: (result) => {
      try {
        return result.concat([{ key: 'teknakul-go', title: 'Teknakul',
          links: [{ label: 'Go Live', shortLabel: 'Go Live', path: '/p/go', icon: 'live' }] }])
      } catch (e) { return result }
    }
  })

  registerClientRoute({ route: 'go', onMount: ({ rootEl }) => render(rootEl) })

  function el (tag, style, text) {
    const e = document.createElement(tag)
    if (style) Object.assign(e.style, style)
    if (text != null) e.textContent = text
    return e
  }

  function iceComplete (pc) {
    return new Promise((res) => {
      if (pc.iceGatheringState === 'complete') return res()
      const cb = () => { if (pc.iceGatheringState === 'complete') { pc.removeEventListener('icegatheringstatechange', cb); res() } }
      pc.addEventListener('icegatheringstatechange', cb)
      setTimeout(res, 3000) // don't wait forever for host candidates
    })
  }

  async function render (root) {
    root.innerHTML = ''
    Object.assign(root.style, { maxWidth: '720px', margin: '0 auto', padding: '24px 18px', color: 'var(--fg,#e6edf5)' })
    root.appendChild(el('h1', { fontSize: '26px', fontWeight: '800', margin: '0 0 4px' }, '🔴 Go Live'))
    root.appendChild(el('div', { color: 'var(--fg-350,#94a3b8)', marginBottom: '18px', fontSize: '15px' },
      'Stream straight from this device. If multistream is set up, you go out everywhere at once.'))

    const video = el('video', { width: '100%', borderRadius: '14px', background: '#000', aspectRatio: '16/9' })
    video.autoplay = true; video.muted = true; video.playsInline = true
    root.appendChild(video)

    const title = el('input', { width: '100%', padding: '10px 12px', borderRadius: '10px', border: '1px solid rgba(62,189,248,.3)', background: 'var(--input-bg,#0b1120)', color: 'var(--fg,#e6edf5)', margin: '12px 0', fontSize: '14px', outline: 'none' })
    title.placeholder = 'Stream title'; title.value = 'Live from Teknakul Go'
    root.appendChild(title)

    const btn = el('button', { padding: '12px 24px', borderRadius: '11px', border: 'none', background: SKY, color: '#0b1120', fontWeight: '800', fontSize: '16px', cursor: 'pointer' }, 'Go Live')
    const status = el('div', { marginTop: '14px', fontSize: '14px', lineHeight: '1.6' })
    root.appendChild(btn); root.appendChild(status)

    let stream, pc, resourceUrl, live = false
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { width: 1280, height: 720 }, audio: true })
      video.srcObject = stream
    } catch (e) {
      status.style.color = '#f88'
      status.textContent = 'Camera/mic permission is required to go live. (' + e.message + ')'
      return
    }

    async function goLive () {
      btn.disabled = true; status.style.color = ''; status.textContent = 'Starting…'
      try {
        const h = (peertubeHelpers.getAuthHeader && peertubeHelpers.getAuthHeader()) || {}
        const res = await fetch(API + '/go/start', { method: 'POST', headers: Object.assign({ 'Content-Type': 'application/json' }, h), body: JSON.stringify({ name: title.value }) })
        const info = await res.json()
        if (!res.ok) throw new Error(info.error || 'could not start the live')
        status.textContent = 'Connecting…'
        pc = new RTCPeerConnection({ iceServers: [{ urls: 'stun:stun.l.google.com:19302' }] })
        stream.getTracks().forEach(t => pc.addTrack(t, stream))
        await pc.setLocalDescription(await pc.createOffer())
        await iceComplete(pc)
        const whip = await fetch(info.whipUrl, { method: 'POST', headers: { 'Content-Type': 'application/sdp' }, body: pc.localDescription.sdp })
        if (!whip.ok) throw new Error('the streaming gateway rejected the connection (' + whip.status + ')')
        const loc = whip.headers.get('Location')
        if (loc) { try { resourceUrl = new URL(loc, info.whipUrl).href } catch (e) { resourceUrl = loc } }
        await pc.setRemoteDescription({ type: 'answer', sdp: await whip.text() })
        live = true
        status.innerHTML = ''
        status.appendChild(el('div', { color: '#22c55e', fontWeight: '700' },
          '🔴 You are LIVE' + (info.multistream ? ' — multistreaming to your destinations' : '')))
        const a = el('a', { color: SKY, display: 'inline-block', marginTop: '4px' }, 'Open your stream ↗')
        a.href = info.watchUrl; a.target = '_blank'; status.appendChild(a)
        btn.textContent = 'Stop'; btn.style.background = '#ef4444'; btn.style.color = '#fff'; btn.disabled = false
      } catch (e) {
        status.style.color = '#f88'; status.textContent = 'Could not go live: ' + e.message
        btn.disabled = false
      }
    }

    async function stop () {
      live = false
      try { if (resourceUrl) await fetch(resourceUrl, { method: 'DELETE' }) } catch (e) { /* ignore */ }
      try { if (pc) pc.close() } catch (e) { /* ignore */ }
      status.style.color = ''; status.textContent = 'Stream ended.'
      btn.textContent = 'Go Live'; btn.style.background = SKY; btn.style.color = '#0b1120'
    }

    btn.addEventListener('click', () => (live ? stop() : goLive()))
  }
}

export { register }
