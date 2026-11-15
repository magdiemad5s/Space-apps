# Web development and future hosting

The application remains an **Angular/Ionic web app**. Windows and Linux launch exactly the same source; there is no separate desktop fork. The `.cmd` files are local convenience launchers, not a change to the architecture.

## Frontend development

After the main setup, start the model/backend through the launcher, or use the manual commands in [ai/README.md](../ai/README.md). To run just the frontend:

```bash
cd frontend
npm ci
npm start
```

Open <http://localhost:4200>. The default API base is `/api/v1`. `proxy.conf.cjs` forwards it to `http://127.0.0.1:3000`; set `BACKEND_URL` to another backend **origin** before starting Angular. Do not include `/api/v1` in `BACKEND_URL`.

```bash
BACKEND_URL=http://127.0.0.1:3100 npm start
```

PowerShell:

```powershell
$env:BACKEND_URL = 'http://127.0.0.1:3100'
npm start
```

If the backend is unavailable, the app shows a connection error. **View simulated demo** explicitly opts into local fixture data. Offline additions stay in memory and are not predictions or backend records. Leaving that mode returns to the actual backend.

An explicit API override is available in the Check-in screen. For a phone, `localhost` points to the phone, not the laptop. Prefer one same-origin hosted URL; the supplied launcher binds only to laptop loopback and does not expose the API to a network.

## Build once for static hosting

```bash
cd frontend
npm run typecheck
npm test
npm run build
```

The frontend output is **`frontend/dist/dashboard-angular/browser/`**. It contains static assets and can be served by an ordinary web server. The original Manrope typeface is bundled locally, with a system fallback; no external Google Fonts download is required. The model stays on the server and is not copied into the browser bundle.

For a web deployment, use this routing:

```text
Browser -> HTTPS origin
              /          -> Angular static files
              /api/v1/*  -> TypeScript backend on a private interface
                               -> Python model on a private interface
```

Keep `/api/v1` intact when proxying. Configure `AI_SERVICE_URL` only on the backend, not in frontend code. Angular's development proxy is not included in the production build; the hosting reverse proxy must supply the route.

[nginx.local.example.conf](../deploy/nginx.local.example.conf) is a local routing example, **not a complete public deployment configuration**. Change its static root to the actual build path. The backend and model commands are unchanged.

Before public or multi-user hosting, implement authentication/authorization for participant history, restrict cross-origin access, enable HTTPS, and replace or appropriately secure the local JSON store. The existing delete-history endpoint is unauthenticated. No public deployment, user-account system, TLS configuration, or medical-data security review is claimed by the local demo integration.

## Later desktop packaging

If an installer is required later, an Electron/Tauri/PWA decision can be made around this same frontend. A self-contained Windows installer also needs Windows-compatible model dependencies, service lifecycle handling, storage/update decisions, and a native Windows build/test process. No retraining is inherently required. The current delivery deliberately stops at the selected one-click launcher.
