// Header logo behavior:
//   - clicking the ICON (monogram)  -> the marketing site https://www.teknakul.com/
//   - clicking the NAME  (TEKNAKUL) -> the platform home (unchanged, PeerTube routerLink="/")
// PeerTube's header logo is one anchor wrapping the icon image + the instance name.
// We add a capture-phase click handler on the icon that navigates away and stops the
// event before PeerTube's router handles it; the name keeps the anchor's default.
async function register () {
  const WWW = 'https://www.teknakul.com/'

  function findLogoLink () {
    const direct = document.querySelector('a.logo, .logo a, .top-left-block a, header a.logo')
    if (direct) return direct
    const name = document.querySelector('.instance-name')
    if (name && name.closest('a')) return name.closest('a')
    // Fallback: the top-left-most anchor that contains an <img>.
    for (const a of document.querySelectorAll('a')) {
      if (!a.querySelector('img')) continue
      const r = a.getBoundingClientRect()
      if (r.top < 110 && r.left < 420 && r.width < 420) return a
    }
    return null
  }

  function wire () {
    const link = findLogoLink()
    if (!link || link.dataset.tkIconWired) return
    const icon = link.querySelector('img') || link.querySelector('.icon, svg, my-global-icon')
    if (!icon) return
    link.dataset.tkIconWired = '1'
    icon.style.cursor = 'pointer'
    icon.setAttribute('title', 'Go to www.teknakul.com')
    icon.addEventListener('click', function (e) {
      e.preventDefault()
      e.stopPropagation()
      e.stopImmediatePropagation()
      window.location.href = WWW
    }, true) // capture: beat the anchor's router click handler
  }

  function boot () {
    wire()
    const obs = new MutationObserver(() => {
      clearTimeout(window.__tkLogoT)
      window.__tkLogoT = setTimeout(wire, 300)
    })
    obs.observe(document.body, { childList: true, subtree: true })
  }

  if (document.body) boot()
  else document.addEventListener('DOMContentLoaded', boot)
}

export { register }
