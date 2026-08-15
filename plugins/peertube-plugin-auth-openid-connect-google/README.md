# peertube-plugin-auth-openid-connect-google (fork)

**Why this exists:** PeerTube's official `peertube-plugin-auth-openid-connect` supports only **one**
OIDC provider per install, and there is no clean npm-installable second OIDC plugin (auth-oauth2 uses a
single-domain model that breaks on Google/Microsoft split userinfo domains; oidc-cnr isn't on npm).
So to offer **both Microsoft and Google** sign-in, we run the official plugin **twice**: the unmodified
one for Microsoft, and this renamed fork for Google.

## The fork recipe (from `peertube-plugin-auth-openid-connect@1.2.0`)
Three edits to the published package:
1. `package.json` → `"name": "peertube-plugin-auth-openid-connect-google"`
2. `dist/main.js` line ~127 — the hardcoded callback path:
   `/plugins/auth-openid-connect/router/code-cb` → `/plugins/auth-openid-connect-google/router/code-cb`
3. `dist/main.js` — the external-auth name (must be unique so it doesn't collide with the Microsoft one):
   `authName: 'openid-connect'` → `'openid-connect-google'` **and**
   `unregisterExternalAuth('openid-connect')` → `unregisterExternalAuth('openid-connect-google')`

(`main.js.forked` here is the edited file; `package.json` is the edited manifest.)

## Install (from disk, on the PeerTube host)
The from-disk installer uses the **directory basename** as the plugin name, so the dir MUST be named
exactly `peertube-plugin-auth-openid-connect-google`:
```bash
sudo docker compose cp <fork-dir> peertube:/app/peertube-plugin-auth-openid-connect-google
sudo docker compose exec -T peertube npm run plugin:install -- \
  --plugin-path /app/peertube-plugin-auth-openid-connect-google
sudo docker compose restart peertube
```
Installed copy lives in `/data/plugins` (persists across restarts/upgrades via the `./data` volume).

## Config (set in Admin → Plugins, or via API `PUT /plugins/peertube-plugin-auth-openid-connect-google/settings`)
- Auth display name: `Google`
- Discover URL: `https://accounts.google.com/.well-known/openid-configuration`
- Client ID / Client secret: the Google OAuth app's
- Scope: `openid profile email` · username+email property: `email` · display-name: `name` · sig: `RS256`

## Redirect URIs (register on the provider side)
| Provider | Plugin | Redirect URI to register |
|---|---|---|
| Microsoft (Entra) | `auth-openid-connect` | `https://teknakul.com/plugins/auth-openid-connect/router/code-cb` |
| Google | this fork | `https://teknakul.com/plugins/auth-openid-connect-google/router/code-cb` |

## Maintenance
This is a **hand-forked copy** — it does NOT auto-update. On a PeerTube upgrade, re-check compatibility;
if the upstream `auth-openid-connect` bumps, re-apply the 3 edits to the new version and reinstall.
