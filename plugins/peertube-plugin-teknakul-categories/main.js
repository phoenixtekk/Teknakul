// Teknakul — replaces PeerTube's default video categories with a technical taxonomy.
async function register ({ videoCategoryManager }) {
  // Remove the default PeerTube categories (Music/Films/Gaming/etc.) — irrelevant here.
  for (let id = 1; id <= 18; id++) {
    try { videoCategoryManager.deleteCategory(id) } catch (e) { /* not present, ignore */ }
  }

  // Teknakul niche categories.
  const categories = {
    100: 'Microsoft 365',
    101: 'Intune & Endpoint',
    102: 'Google Workspace',
    103: 'Cybersecurity',
    104: 'Linux & Homelab',
    105: 'Cloud & DevOps',
    106: 'Networking',
    107: 'Scripting & PowerShell',
    108: 'AI & Automation',
    109: 'Build in Public',
    110: 'Career & Certs',
    111: 'General Tutorials',
    112: 'News'
  }

  for (const id of Object.keys(categories)) {
    videoCategoryManager.addCategory(parseInt(id, 10), categories[id])
  }
}

async function unregister () {}

module.exports = { register, unregister }
