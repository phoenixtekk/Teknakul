// Persistent light/dark toggle.
//
// PeerTube re-resolves the theme on every SPA navigation: for a logged-in user it
// falls back to the account theme (default -> instance light), wiping a plain
// data-pt-theme flip. So we STORE the user's choice and re-assert it on every
// navigation via a MutationObserver, and also persist it (localStorage + best-effort
// account update) so it survives reloads. The built-in themes are keyed off the
// data-pt-theme attribute, so re-asserting the attribute fully switches the look.
async function register ({ peertubeHelpers }) {
  const DARK = 'peertube-core-dark-brown'
  const LIGHT = 'peertube-core-light-beige'
  const PREF = 'tk_pref_theme' // our own persisted choice: 'dark' | 'light'
  const html = document.documentElement

  const getPref = () => { try { return localStorage.getItem(PREF) } catch (e) { return null } }
  const setPref = v => { try { localStorage.setItem(PREF, v) } catch (e) {} }
  const domIsDark = () =>
    (html.getAttribute('data-pt-theme') || '').includes('dark') ||
    (html.getAttribute('data-bs-theme') || '').includes('dark')

  let iconEl
  const updateIcon = dark => { if (iconEl) iconEl.textContent = dark ? '☀️' : '🌙' }

  // Apply the attributes only (no persistence) — used by both the toggle and the enforcer.
  function applyDom (dark) {
    const name = dark ? DARK : LIGHT
    if (html.getAttribute('data-pt-theme') !== name) html.setAttribute('data-pt-theme', name)
    html.setAttribute('data-bs-theme', dark ? 'dark' : 'light')
    try { localStorage.setItem('last_active_theme', JSON.stringify({ name })) } catch (e) {}
    updateIcon(dark)
  }

  // Persist the choice so it survives reloads / other devices.
  async function persist (dark) {
    const name = dark ? DARK : LIGHT
    setPref(dark ? 'dark' : 'light')
    try { localStorage.setItem('theme', name) } catch (e) {}   // anon resolution path
    try {                                                       // logged-in: update the account
      const header = peertubeHelpers && peertubeHelpers.getAuthHeader && peertubeHelpers.getAuthHeader()
      if (header) {
        await fetch('/api/v1/users/me', {
          method: 'PUT',
          headers: Object.assign({ 'Content-Type': 'application/json' }, header),
          body: JSON.stringify({ theme: name })
        })
      }
    } catch (e) { /* best effort */ }
  }

  // Re-assert the stored choice whenever PeerTube changes the theme out from under us.
  function enforce () {
    const p = getPref()
    if (!p) return
    const want = p === 'dark'
    if (domIsDark() !== want) applyDom(want)
  }

  function toggle () {
    const dark = !domIsDark()
    applyDom(dark)
    persist(dark)
  }

  function buildButton () {
    if (document.getElementById('tk-theme-toggle')) return
    const btn = document.createElement('button')
    btn.id = 'tk-theme-toggle'
    btn.title = 'Toggle light / dark'
    btn.setAttribute('aria-label', 'Toggle light or dark theme')
    Object.assign(btn.style, {
      position: 'fixed', right: '18px', bottom: '18px', zIndex: '99999',
      width: '44px', height: '44px', borderRadius: '50%', border: 'none', cursor: 'pointer',
      background: '#3ebdf8', color: '#0b1120', fontSize: '20px', padding: '0',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      boxShadow: '0 2px 12px rgba(0,0,0,.4)'
    })
    iconEl = document.createElement('span')
    btn.appendChild(iconEl)
    updateIcon(domIsDark())
    btn.addEventListener('click', toggle)
    document.body.appendChild(btn)
  }

  function boot () {
    // Apply the stored choice immediately (covers the post-reload re-resolution).
    const p = getPref()
    if (p) applyDom(p === 'dark')
    buildButton()
    // Watch the root element; if PeerTube re-applies its default on navigation, correct it.
    const obs = new MutationObserver(() => {
      clearTimeout(window.__tkThemeT)
      window.__tkThemeT = setTimeout(enforce, 0)
    })
    obs.observe(html, { attributes: true, attributeFilter: ['data-pt-theme', 'data-bs-theme'] })
  }

  if (document.body) boot()
  else document.addEventListener('DOMContentLoaded', boot)
}

export { register }
