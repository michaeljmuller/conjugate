# Google OAuth setup (Google Cloud Console)

One-time setup to let people sign in with Google. Produces a **Client ID** and
**Client Secret** that go into `src/docker/.env`.

## 1. Project

1. Go to <https://console.cloud.google.com/> and sign in.
2. Top bar → project picker → **New Project** (or reuse an existing one). Name it
   e.g. `conjugate`, then **Create** and select it.

## 2. Configure the consent screen

APIs & Services → **OAuth consent screen** (branding).

1. **User type: External** → Create.
2. App name `Conjugate`, your email as support + developer contact. Save.
3. **Scopes:** the defaults are enough — `openid`, `.../auth/userinfo.email`,
   `.../auth/userinfo.profile`. You don't need to add any.
4. **Publishing status:** leave it in **Testing** and add each person's Google
   address under **Test users** (fine for friends-and-family; no Google review
   needed). Only click **Publish app** if you want anyone with the link to sign in.

## 3. Create the OAuth client

APIs & Services → **Credentials** → **Create credentials** → **OAuth client ID**.

- **Application type:** Web application
- **Name:** `conjugate-web`
- **Authorized JavaScript origins:**
  - `https://conjugate.themullers.org`
- **Authorized redirect URIs** (must match exactly, path included):
  - `https://conjugate.themullers.org/auth/callback`
  - *(local testing only, optional)* `http://localhost:8081/auth/callback`

Click **Create**. Copy the **Client ID** and **Client Secret**.

> The redirect URI is exact-match. The app builds it from the request URL, so it must
> equal `https://<host>/auth/callback`. If Google shows `redirect_uri_mismatch`, the
> URI in the console doesn't match the address you signed in from.

## 4. Wire it into the app

In `src/docker/.env` (gitignored — never commit):

```env
GOOGLE_CLIENT_ID=<client id>
GOOGLE_CLIENT_SECRET=<client secret>
SESSION_SECRET=<python -c "import secrets; print(secrets.token_hex(32))">
# Optional: restrict sign-in beyond the test-users list
ALLOWED_EMAILS=me@example.com,friend@example.com
# Make sure the dev-only bypass is NOT set in prod:
# DEV_LOGIN=
# SESSION_HTTPS_ONLY defaults to 1 (correct behind Caddy's TLS)
```

Restart: `docker compose up -d --build`. Visiting the site now redirects unsigned
users to Google. `ALLOWED_EMAILS` (if set) is enforced on top of Google's test-user
list — leave it empty to allow any Google account that passes the consent screen.

## Notes

- **Testing vs Published:** in Testing mode only listed test users can sign in, and a
  refresh token expires after 7 days — harmless here since we only read the profile at
  login. Publishing removes the test-user cap.
- **Local dev without Google:** set `DEV_LOGIN=1` and `SESSION_HTTPS_ONLY=0` in `.env`
  to sign in as a fake local user — no Google client needed.
