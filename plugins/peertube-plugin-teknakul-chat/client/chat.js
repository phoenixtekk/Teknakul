// Unified chat — Twitch + YouTube live chat in one panel. Registers a /p/chat route +
// menu link. Connect buttons kick off OAuth (via the restream API); once connected it
// polls the merged message stream and lets you reply to either platform.
async function register ({ registerHook, registerClientRoute, peertubeHelpers }) {
  const SKY = '#3ebdf8'
  const COLORS = { twitch: '#a970ff', youtube: '#ff4d4d', you: SKY }
  const API = (window.TEKNAKUL_RESTREAM_API || 'https://restream.teknakul.com').replace(/\/$/, '')

  registerHook({
    target: 'filter:left-menu.links.create.result',
    handler: (result) => {
      try {
        return result.concat([{ key: 'teknakul-chat', title: 'Teknakul',
          links: [{ label: 'Unified Chat', shortLabel: 'Chat', path: '/p/chat', icon: 'message-circle' }] }])
      } catch (e) { return result }
    }
  })

  registerClientRoute({ route: 'chat', onMount: ({ rootEl }) => render(rootEl) })

  function el (tag, style, text) {
    const e = document.createElement(tag)
    if (style) Object.assign(e.style, style)
    if (text != null) e.textContent = text
    return e
  }
  function headers () {
    return Object.assign({ 'Content-Type': 'application/json' },
      (peertubeHelpers.getAuthHeader && peertubeHelpers.getAuthHeader()) || {})
  }
  async function api (path, opts) {
    const res = await fetch(API + path, Object.assign({ headers: headers() }, opts || {}))
    let d = {}; try { d = await res.json() } catch (e) {}
    if (!res.ok) throw new Error(d.error || ('HTTP ' + res.status))
    return d
  }

  async function render (root) {
    root.innerHTML = ''
    Object.assign(root.style, { maxWidth: '760px', margin: '0 auto', padding: '24px 18px', color: 'var(--fg,#e6edf5)' })
    root.appendChild(el('h1', { fontSize: '26px', fontWeight: '800', margin: '0 0 4px' }, '💬 Unified Chat'))
    root.appendChild(el('div', { color: 'var(--fg-350,#94a3b8)', marginBottom: '18px', fontSize: '15px' },
      'Read and reply to your Twitch and YouTube live chat in one place while you multistream.'))

    let st
    try { st = await api('/chat/status') } catch (e) {
      root.appendChild(el('div', { color: '#f88' }, 'Could not load chat (' + e.message + ').')); return
    }

    // connect row
    const connectRow = el('div', { display: 'flex', gap: '10px', flexWrap: 'wrap', marginBottom: '16px' })
    function connectBtn (platform, label, connected) {
      const b = el('button', {
        padding: '9px 16px', borderRadius: '10px', fontWeight: '700', fontSize: '14px', cursor: 'pointer',
        border: '1px solid ' + COLORS[platform], color: connected ? '#0b1120' : COLORS[platform],
        background: connected ? COLORS[platform] : 'transparent'
      }, (connected ? '✓ ' : '') + label)
      b.addEventListener('click', async () => {
        if (connected) { await api('/chat/disconnect', { method: 'POST', body: JSON.stringify({ platform }) }); render(root); return }
        try { const d = await api('/oauth/' + platform + '/start', { method: 'POST' }); window.location.href = d.url } catch (e) { alert(e.message) }
      })
      return b
    }
    connectRow.appendChild(connectBtn('twitch', st.twitch ? ('Twitch: ' + st.twitch) : 'Connect Twitch', !!st.twitch))
    connectRow.appendChild(connectBtn('youtube', st.youtube ? 'YouTube connected' : 'Connect YouTube', !!st.youtube))
    root.appendChild(connectRow)

    if (!st.connected.length) {
      root.appendChild(el('div', { color: 'var(--fg-350,#94a3b8)' }, 'Connect a platform above to see your live chat here. (You need to be live on that platform for messages to appear.)'))
      return
    }

    // messages pane
    const pane = el('div', {
      height: '420px', overflowY: 'auto', border: '1px solid var(--border-primary,rgba(62,189,248,.2))',
      borderRadius: '12px', padding: '12px 14px', background: 'var(--bg-secondary-400,#0f1729)', fontSize: '14px'
    })
    root.appendChild(pane)
    pane.appendChild(el('div', { color: 'var(--fg-350,#94a3b8)', fontSize: '13px' }, 'Waiting for messages…'))

    // reply row
    const replyRow = el('div', { display: 'flex', gap: '8px', marginTop: '12px' })
    const sel = el('select', inputStyle())
    ;['twitch', 'youtube'].filter(p => st.connected.includes(p)).forEach(p => {
      const o = el('option', null, 'Reply to ' + p); o.value = p; sel.appendChild(o)
    })
    sel.style.maxWidth = '160px'
    const input = el('input', inputStyle()); input.placeholder = 'Message your chat…'
    const send = el('button', { padding: '9px 18px', borderRadius: '10px', border: 'none', background: SKY, color: '#0b1120', fontWeight: '700', cursor: 'pointer', flex: 'none' }, 'Send')
    async function doSend () {
      const t = input.value.trim(); if (!t) return
      input.value = ''
      try { await api('/chat/send', { method: 'POST', body: JSON.stringify({ platform: sel.value, text: t }) }) } catch (e) { /* shown as no echo */ }
    }
    send.addEventListener('click', doSend)
    input.addEventListener('keydown', e => { if (e.key === 'Enter') doSend() })
    replyRow.appendChild(sel); replyRow.appendChild(input); replyRow.appendChild(send)
    root.appendChild(replyRow)

    // poll loop
    let after = 0; let first = true; let alive = true
    const obs = new MutationObserver(() => { if (!document.body.contains(pane)) { alive = false; obs.disconnect() } })
    obs.observe(document.body, { childList: true, subtree: true })
    async function loop () {
      if (!alive) return
      try {
        const d = await api('/chat/poll?after=' + after)
        if (d.messages && d.messages.length) {
          if (first) { pane.innerHTML = ''; first = false }
          const atBottom = pane.scrollTop + pane.clientHeight >= pane.scrollHeight - 40
          d.messages.forEach(m => {
            after = Math.max(after, m.ts)
            const line = el('div', { margin: '3px 0', lineHeight: '1.4' })
            line.appendChild(el('span', { color: COLORS[m.platform] || '#aaa', fontWeight: '700' }, m.user))
            line.appendChild(el('span', { color: 'var(--fg-350,#94a3b8)', fontSize: '11px', margin: '0 6px' }, m.platform))
            line.appendChild(document.createTextNode(m.text))
            pane.appendChild(line)
          })
          if (atBottom) pane.scrollTop = pane.scrollHeight
        }
      } catch (e) { /* keep trying */ }
      if (alive) setTimeout(loop, 3000)
    }
    loop()
  }

  function inputStyle () {
    return { flex: '1', padding: '9px 11px', borderRadius: '9px', border: '1px solid var(--border-primary,rgba(62,189,248,.3))', background: 'var(--input-bg,#0b1120)', color: 'var(--fg,#e6edf5)', fontSize: '14px', outline: 'none' }
  }
}

export { register }
