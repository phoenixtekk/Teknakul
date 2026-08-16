// Runbook Mode - "Ask this video" co-pilot panel on the watch page.
// Asks the self-hosted co-pilot API a question about the current video, shows the
// answer + a verbatim quote, and jumps the player to the most relevant timestamp.
async function register ({ registerHook }) {
  const TEAL = '#27d3c1'
  // Public endpoint of the ask API (Cloudflare route -> linuxg1:3081). Override-able.
  const API = (window.TEKNAKUL_ASK_API || 'https://runbook.teknakul.com').replace(/\/$/, '')

  let player = null
  let currentVideo = null

  registerHook({
    target: 'action:video-watch.player.loaded',
    handler: (params) => { player = (params && (params.player || params.videojs)) || player }
  })

  registerHook({
    target: 'action:video-watch.video.loaded',
    handler: (params) => {
      currentVideo = (params && (params.video || params)) || null
      // let the DOM settle, then inject
      setTimeout(injectPanel, 400)
    }
  })

  function fmt (sec) {
    sec = Math.max(0, parseInt(sec, 10) || 0)
    const m = Math.floor(sec / 60), s = sec % 60
    return m + ':' + String(s).padStart(2, '0')
  }

  function seek (sec) {
    try {
      if (player && typeof player.currentTime === 'function') {
        player.currentTime(sec)
        if (typeof player.play === 'function') player.play()
        window.scrollTo({ top: 0, behavior: 'smooth' })
      }
    } catch (e) { /* no-op */ }
  }

  function findAnchor () {
    return document.querySelector('#plugin-placeholder-player-next')
      || document.querySelector('my-video-watch .video-info')
      || document.querySelector('.video-info')
      || document.querySelector('my-video-watch')
  }

  function injectPanel () {
    const existing = document.getElementById('tk-runbook')
    if (existing) existing.remove()
    const anchor = findAnchor()
    if (!anchor || !currentVideo) return

    const videoId = currentVideo.uuid || currentVideo.shortUUID || currentVideo.id
    const box = document.createElement('div')
    box.id = 'tk-runbook'
    Object.assign(box.style, {
      border: '1px solid rgba(39,211,193,.28)', borderRadius: '14px',
      padding: '16px 18px', margin: '18px 0',
      background: 'linear-gradient(180deg,rgba(39,211,193,.06),transparent)'
    })

    const title = document.createElement('div')
    title.textContent = '✨ Ask this video'
    Object.assign(title.style, { fontWeight: '700', fontSize: '16px', marginBottom: '4px', color: TEAL })
    const sub = document.createElement('div')
    sub.textContent = 'AI co-pilot — answers from the transcript and jumps you to the moment.'
    Object.assign(sub.style, { fontSize: '13px', opacity: '.7', marginBottom: '12px' })

    const row = document.createElement('div')
    Object.assign(row.style, { display: 'flex', gap: '8px' })
    const input = document.createElement('input')
    input.type = 'text'
    input.placeholder = 'e.g. Where do they assign the policy?'
    Object.assign(input.style, {
      flex: '1', padding: '10px 12px', borderRadius: '10px',
      border: '1px solid rgba(39,211,193,.3)', background: 'var(--input-bg,rgba(0,0,0,.15))',
      color: 'inherit', fontSize: '14px', outline: 'none'
    })
    const btn = document.createElement('button')
    btn.textContent = 'Ask'
    Object.assign(btn.style, {
      padding: '10px 20px', borderRadius: '10px', border: 'none', cursor: 'pointer',
      background: TEAL, color: '#04100e', fontWeight: '700', fontSize: '14px', flex: 'none'
    })

    const out = document.createElement('div')
    Object.assign(out.style, { marginTop: '12px', fontSize: '14.5px', lineHeight: '1.55', display: 'none' })

    row.appendChild(input); row.appendChild(btn)
    box.appendChild(title); box.appendChild(sub); box.appendChild(row); box.appendChild(out)

    if (anchor.id === 'plugin-placeholder-player-next') anchor.appendChild(box)
    else anchor.parentNode.insertBefore(box, anchor)

    async function ask () {
      const q = input.value.trim()
      if (!q) return
      out.style.display = 'block'
      out.innerHTML = '<span style="opacity:.7">Thinking…</span>'
      btn.disabled = true
      try {
        const res = await fetch(API + '/ask', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ videoId, question: q })
        })
        const d = await res.json()
        if (d.error) throw new Error(d.error)
        render(d)
      } catch (e) {
        out.innerHTML = '<span style="opacity:.8">The co-pilot is unavailable right now. ('
          + (e && e.message ? e.message : 'network error') + ')</span>'
      } finally { btn.disabled = false }
    }

    function render (d) {
      out.innerHTML = ''
      const ans = document.createElement('div')
      ans.textContent = d.answer || 'No answer.'
      out.appendChild(ans)
      if (d.quote) {
        const q = document.createElement('div')
        q.textContent = '“' + d.quote + '”'
        Object.assign(q.style, {
          marginTop: '8px', paddingLeft: '10px', borderLeft: '3px solid ' + TEAL,
          fontStyle: 'italic', opacity: '.85', fontSize: '13.5px'
        })
        out.appendChild(q)
      }
      if (d.found && d.timecode >= 0) {
        const jump = document.createElement('button')
        jump.textContent = '▶ Jump to ' + fmt(d.timecode)
        Object.assign(jump.style, {
          marginTop: '10px', padding: '7px 14px', borderRadius: '9px', cursor: 'pointer',
          border: '1px solid ' + TEAL, background: 'transparent', color: TEAL, fontWeight: '700', fontSize: '13px'
        })
        jump.addEventListener('click', () => seek(d.timecode))
        out.appendChild(jump)
      }
    }

    btn.addEventListener('click', ask)
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') ask() })
  }
}

export { register }
