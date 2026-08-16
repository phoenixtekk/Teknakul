// Floating one-click light/dark toggle. Switches the built-in dark/light themes live.
async function register () {
  const DARK = 'peertube-core-dark-brown'
  const LIGHT = 'peertube-core-light-beige'

  const isDark = () =>
    (document.documentElement.getAttribute('data-bs-theme') || '').includes('dark') ||
    (document.documentElement.getAttribute('data-pt-theme') || '').includes('dark')

  let iconEl

  function updateIcon (dark) { if (iconEl) iconEl.textContent = dark ? '☀️' : '🌙' } // ☀️ / 🌙

  function applyTheme (dark) {
    const name = dark ? DARK : LIGHT
    document.documentElement.setAttribute('data-pt-theme', name)
    document.documentElement.setAttribute('data-bs-theme', dark ? 'dark' : 'light')
    try { localStorage.setItem('last_active_theme', JSON.stringify({ name })) } catch (e) {}
    updateIcon(dark)
  }

  function build () {
    if (document.getElementById('tk-theme-toggle')) return
    const btn = document.createElement('button')
    btn.id = 'tk-theme-toggle'
    btn.title = 'Toggle light / dark'
    btn.setAttribute('aria-label', 'Toggle light or dark theme')
    Object.assign(btn.style, {
      position: 'fixed', right: '18px', bottom: '18px', zIndex: '99999',
      width: '44px', height: '44px', borderRadius: '50%', border: 'none', cursor: 'pointer',
      background: '#6366f1', color: '#ffffff', fontSize: '20px', padding: '0',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      boxShadow: '0 2px 12px rgba(0,0,0,.4)'
    })
    iconEl = document.createElement('span')
    btn.appendChild(iconEl)
    updateIcon(isDark())
    btn.addEventListener('click', () => applyTheme(!isDark()))
    document.body.appendChild(btn)
  }

  if (document.body) build()
  else document.addEventListener('DOMContentLoaded', build)
}

export { register }
