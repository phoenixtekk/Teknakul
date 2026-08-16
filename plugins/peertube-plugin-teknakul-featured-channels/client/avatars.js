// Injects channel avatars into the "Featured Channels" sidebar section (Rumble-style).
// The left-menu link filter can't carry images, so we decorate the rendered DOM:
// find the Featured Channels block, then swap each link's generic icon for the
// channel's avatar (falling back to teal initials when a channel has no avatar).
async function register () {
  const CACHE = { map: null }

  async function channelAvatars () {
    if (CACHE.map) return CACHE.map
    const map = {}
    try {
      const res = await fetch('/api/v1/videos?count=24&sort=-publishedAt&isLocal=true&nsfw=false')
      const d = await res.json()
      for (const v of (d.data || [])) {
        const c = v.channel
        if (!c || !c.name || map[c.name] !== undefined) continue
        let path = null
        if (c.avatars && c.avatars.length) path = c.avatars[c.avatars.length - 1].path
        else if (c.avatar && c.avatar.path) path = c.avatar.path
        map[c.name] = path ? (path.startsWith('http') ? path : location.origin + path) : null
      }
    } catch (e) { /* ignore */ }
    CACHE.map = map
    return map
  }

  const initials = s => (s || '?').replace(/^@/, '').slice(0, 2).toUpperCase()

  async function decorate () {
    let target = null
    document.querySelectorAll('.menu-block').forEach(b => {
      const t = b.querySelector('.block-title')
      if (t && /featured channels/i.test(t.textContent || '')) target = b
    })
    if (!target) return
    const links = target.querySelectorAll('a.menu-link')
    if (!links.length) return
    const map = await channelAvatars()
    links.forEach(a => {
      if (a.querySelector('.tk-av')) return
      const href = a.getAttribute('href') || ''
      const name = decodeURIComponent(href.replace(/.*\/c\//, '').split('/')[0])
      const url = map[name]
      const av = document.createElement('span')
      av.className = 'tk-av'
      if (url) av.style.backgroundImage = 'url("' + url + '")'
      else av.textContent = initials(name)
      const icon = a.querySelector('my-global-icon, .icon, svg, img')
      if (icon) icon.replaceWith(av)
      else a.prepend(av)
    })
  }

  function boot () {
    setTimeout(decorate, 300)
    setTimeout(decorate, 1200)
    const obs = new MutationObserver(() => {
      clearTimeout(window.__tkAvT)
      window.__tkAvT = setTimeout(decorate, 400)
    })
    obs.observe(document.body, { childList: true, subtree: true })
  }

  if (document.body) boot()
  else document.addEventListener('DOMContentLoaded', boot)
}

export { register }
