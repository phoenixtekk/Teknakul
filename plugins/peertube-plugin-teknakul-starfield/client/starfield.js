// Subtle drifting/twinkling starfield behind the whole app (Enogye-style).
// Deterministic scatter (Mulberry32 PRNG, seeded) so it looks organic and stable.
// Styling + theme-adaptive star color live in the instance theme CSS (#tk-stars/.tk-star).
async function register () {
  const COUNT = 130

  function rng (seed) {
    let s = seed >>> 0
    return () => {
      s = (s + 0x6d2b79f5) | 0
      let t = s
      t = Math.imul(t ^ (t >>> 15), t | 1)
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296
    }
  }

  function build () {
    if (document.getElementById('tk-stars')) return
    if (!document.body) return
    const box = document.createElement('div')
    box.id = 'tk-stars'
    box.setAttribute('aria-hidden', 'true')
    const next = rng(1337)
    for (let i = 0; i < COUNT; i++) {
      const r = 0.4 + next() * 1.8
      const x = next() * 100
      const y = next() * 100
      const o = 0.16 + next() * 0.5
      const delay = next() * -6
      const dur = 3 + next() * 6
      const dx = (next() - 0.5) * 30
      const dy = (next() - 0.5) * 30
      const s = document.createElement('span')
      s.className = 'tk-star'
      s.style.cssText =
        'left:' + x + '%;top:' + y + '%;width:' + (r * 2) + 'px;height:' + (r * 2) + 'px;' +
        'opacity:' + o + ';--o:' + o + ';--dx:' + dx + 'px;--dy:' + dy + 'px;' +
        'animation-delay:' + delay + 's,' + (delay * 0.7) + 's;' +
        'animation-duration:' + dur + 's,' + (dur * 2.3) + 's'
      box.appendChild(s)
    }
    document.body.appendChild(box)
  }

  if (document.body) build()
  else document.addEventListener('DOMContentLoaded', build)
}

export { register }
