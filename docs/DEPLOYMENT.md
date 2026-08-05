# FocusSentinel — Testing, running locally, and deploying (GitHub + Railway)

## 1. Run the test suites

Each package/service has its own tests. From the repo root:

```bash
# Rules engine (simulated-clock tests — a 45-minute limit tested in milliseconds)
cd packages/rules-engine && pip install -e . --break-system-packages && pytest && cd ../..

# Activity classifier
cd packages/activity-classifier && pip install -e . --break-system-packages && pytest && cd ../..

# API — the full vertical slice: warning one -> warning two -> restriction ->
# extension request -> approval -> restored access, plus offline sync and auth
cd services/api && pip install -r requirements.txt --break-system-packages && pytest && cd ../..

# Notification worker
cd services/notification-worker && pip install -r requirements.txt --break-system-packages && pytest && cd ../..

# Browser extension active-time tracking logic
cd apps/browser-extension && npm install && npm test && cd ../..
```

All of these run against SQLite or in-memory fakes — no Postgres/Docker needed to test.

## 2. Run it locally

Fastest path, with Docker:

```bash
cp .env.example .env    # edit JWT_SECRET at minimum
docker compose up --build
```

Then seed demo data and open `http://localhost:3000`. The seed script isn't copied into the API image, so run it from your host — `docker compose` exposes Postgres on `localhost:5432` — using the same dependencies as the API:

```bash
cd services/api
pip install -r requirements.txt --break-system-packages   # if you haven't already
DATABASE_URL=postgresql+psycopg://focussentinel:change-me@localhost:5432/focussentinel \
  python ../../database/seed/seed.py
```

(Without Docker: see the root `README.md` "Local development" section — run the API, worker, and dashboard as three separate local processes against a local SQLite file.)

## 3. Push to GitHub

```bash
cd focussentinel
git init
git add .
git status   # sanity check: .env should NOT appear (it's gitignored); .env.example should
git commit -m "FocusSentinel: Phase 1 vertical slice"
git branch -M main
git remote add origin https://github.com/<your-username>/focussentinel.git
git push -u origin main
```

If you don't have a repo yet, create an empty one on GitHub first (no README/license, to avoid a merge conflict on first push), then run the commands above.

## 4. Deploy to Railway

Railway deploys each Dockerfile as its own **service**, and multiple services share one **project**. This repo has three deployable services (API, notification worker, web dashboard) plus one managed database (Postgres). Redis is *not* required — `redis_url` is defined in config for a future Celery integration, but nothing in this codebase actually connects to Redis yet, so skip provisioning it for now.

### 4.1 Create the project and database

1. In the Railway dashboard, **New Project → Deploy from GitHub repo** and pick your `focussentinel` repo.
2. Railway will try to auto-detect a service from the repo root — delete that auto-created service once you've created the three below (or repurpose it as the API service).
3. **New → Database → Add PostgreSQL.** This creates a `Postgres` service with its own `DATABASE_URL`.

### 4.2 Create the API service

1. **New → GitHub Repo** → same repo.
2. In that service's **Settings → Build**, set the variable `RAILWAY_DOCKERFILE_PATH` (under **Variables**, not Build settings) to `services/api/Dockerfile`. Leave **Root Directory** unset/at the repo root — the Dockerfile's `COPY` paths (e.g. `COPY packages/rules-engine /packages/rules-engine`) assume the build context is the monorepo root, matching `docker-compose.yml`'s `context: .`.
3. Add variables:
   - `DATABASE_URL` = `${{Postgres.DATABASE_URL}}`
     (the app normalizes `postgres://`/`postgresql://` to the `postgresql+psycopg://` SQLAlchemy needs — see `services/api/app/config.py` — so you can paste Railway's value as-is)
   - `JWT_SECRET` = a long random string (`openssl rand -hex 32`)
   - `ENVIRONMENT` = `production`
   - `CORS_ORIGINS` = leave as `http://localhost:3000` for now; you'll update it once the dashboard has a domain (step 4.4)
4. **Settings → Networking → Generate Domain** to get a public URL, e.g. `focussentinel-api-production.up.railway.app`. Confirm it's live: `curl https://<that-domain>/health` should return `{"status":"ok",...}`.

### 4.3 Create the notification worker service

1. **New → GitHub Repo** → same repo again.
2. Set `RAILWAY_DOCKERFILE_PATH` = `services/notification-worker/Dockerfile`.
3. Add `DATABASE_URL` = `${{Postgres.DATABASE_URL}}` (same reference as the API — both need to read/write the same tables).
4. Leave `EMAIL_PROVIDER`/`SMS_PROVIDER` as `console` to start (notifications show up in this service's Railway logs); switch to `smtp`/`sendgrid`/`twilio` plus the matching credential variables once you have a real provider — see `services/notification-worker/app/config.py` for the full variable list.
5. This service has no HTTP endpoint — that's expected. Don't generate a domain for it, and if Railway's health check complains about no open port, disable the health check for this service in **Settings → Deploy**.

### 4.4 Create the web dashboard service

1. **New → GitHub Repo** → same repo again.
2. Set `RAILWAY_DOCKERFILE_PATH` = `apps/web-dashboard/Dockerfile`.
3. Add `NEXT_PUBLIC_API_BASE_URL` = the API's public URL from step 4.2 (e.g. `https://focussentinel-api-production.up.railway.app`). This has to be set *before* the first build — Next.js inlines `NEXT_PUBLIC_*` variables into the client bundle at build time, and the Dockerfile now declares it as a build `ARG` so Railway passes it through automatically (see `apps/web-dashboard/Dockerfile`). If you add/change this variable later, trigger a redeploy for it to take effect.
4. **Settings → Networking → Generate Domain.**
5. Go back to the **API service** and update `CORS_ORIGINS` to `["https://<your-dashboard-domain>"]`, then redeploy the API so browser requests from the dashboard aren't blocked by CORS.

### 4.5 Seed demo data

Using the Railway CLI (`npm i -g @railway/cli`, then `railway login`):

```bash
railway link         # select your project
railway service      # select the API service
railway run python ../../database/seed/seed.py
```

`railway run` executes the command with that service's environment variables (including `DATABASE_URL`) injected, against your Railway Postgres instance.

### 4.6 Turn on real extension-request approval emails

When a student requests more time, every parent in the family gets an email
with one-tap Approve/Deny links (see `GET /extension-requests/decide` in
`services/api/app/routers/extension_requests.py`) — no phone number or SMS
provider required. This is on by default in the sense that the links are
always generated; what's off by default is actual *delivery*, since the
`console` email provider just logs the email to the notification-worker's
Railway logs instead of sending it.

1. On the **notification-worker** service, set `EMAIL_PROVIDER` to `smtp` or
   `sendgrid` and add the matching credential variables (see
   `services/notification-worker/app/config.py` for the full list — a Gmail
   account with an "app password" works fine for `smtp`).
2. On the **API** service, set `PUBLIC_API_BASE_URL` to this service's own
   public domain from step 4.2 (e.g. `https://focussentinel-api-production.up.railway.app`).
   The approve/deny links are built from this value, so they'll be broken
   (pointing at `localhost:8000`) until it's set.
3. Redeploy both services so the new variables take effect.

Known limits: the approve/deny link expires after 24 hours
(`EXTENSION_ACTION_TOKEN_EXPIRE_MINUTES`, configurable) — after that, or
once a request has already been decided any other way, clicking it just
shows a friendly "already decided"/"expired" page instead of acting again.

A previous version of this app had two-way SMS (students texting to request
time, parents replying YES/NO by text). That was removed at the product
owner's request — Twilio and similar providers require a dedicated,
carrier-verified phone number and often a slow business-verification
process, which turned out to be more friction than it was worth for this
use case. The email approach above achieves the same "parent can act from
their phone" goal without any of that.

### 4.7 Point the browser extension at production

The extension currently has to be configured per install (see `apps/browser-extension/README.md`). Once you have a real device registered against the production API, run the same `chrome.runtime.sendMessage({type: "focussentinel:configure", config: {...}})` snippet with `apiBaseUrl` set to your API's Railway domain instead of `localhost:8000`.

## 5. After deploying: things to revisit

- Rotate `JWT_SECRET` out of any shared history if it was ever committed by mistake — Railway variables aren't in git, so as long as you only ever entered it in the dashboard, you're fine.
- Turn on a real email/SMS provider (`docs/SECURITY_PRIVACY.md` lists the adapters) — the console adapter only logs to the worker's Railway logs, it doesn't deliver anything.
- Everything in `docs/KNOWN_LIMITATIONS.md` still applies — deploying doesn't add capabilities the code doesn't have (no Windows/macOS/Android/iOS enforcement yet).
- Consider adding a `railway.toml` per service once this setup is working, so the Dockerfile path and non-secret variables are version-controlled instead of only living in the Railway dashboard.
