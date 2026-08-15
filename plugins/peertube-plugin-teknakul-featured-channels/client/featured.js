// Adds a "Featured Channels" section to the left sidebar, listing local channels
// that have published videos (most recent first). Auto-populates as creators upload.
async function register ({ registerHook }) {
  registerHook({
    target: 'filter:left-menu.links.create.result',
    handler: async (result) => {
      try {
        const res = await fetch('/api/v1/videos?count=24&sort=-publishedAt&isLocal=true&nsfw=false')
        const data = await res.json()

        const seen = new Set()
        const channels = []
        for (const v of (data.data || [])) {
          const c = v.channel
          if (c && c.name && !seen.has(c.name)) {
            seen.add(c.name)
            channels.push(c)
          }
        }

        const featured = channels.slice(0, 10)
        if (!featured.length) return result

        const links = featured.map(c => ({
          label: c.displayName || c.name,
          shortLabel: c.displayName || c.name,
          path: '/c/' + c.name,
          icon: 'videos'
        }))

        const block = { key: 'teknakul-featured-channels', title: 'Featured Channels', links }

        if (Array.isArray(result)) result.push(block)
        return result
      } catch (err) {
        console.error('[teknakul-featured-channels] failed to build section', err)
        return result
      }
    }
  })
}

export { register }
