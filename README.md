diff --git a/README.md b/README.md
index 1541154bb40014f64db2a7bdb4983c74e5c54b62..775f2f0fcf16a990180675c6f68b55fde8208bd5 100644
--- a/README.md
+++ b/README.md
@@ -1 +1,79 @@
-# EVE_Orders
\ No newline at end of file
+# EVE Orders (Starter)
+
+A tiny beginner-friendly web app you can host on **GitHub Pages** to view your EVE character market orders.
+
+## What this does (MVP)
+
+- Lets you sign in with EVE SSO.
+- Loads your character's active market orders.
+- Shows them in a simple table.
+
+## What you need first
+
+1. A GitHub account.
+2. This repository.
+3. An app created in the [EVE Developer Portal](https://developers.eveonline.com/).
+
+---
+
+## ELI5 setup steps
+
+### 1) Create your EVE app
+
+In EVE Developer Portal:
+
+- Create **New Application**.
+- Choose OAuth flow suitable for browser/public client.
+- Add callback URL:
+  - For local testing: `http://localhost:8000`
+  - For GitHub Pages (later): `https://YOUR_GITHUB_USERNAME.github.io/EVE_Orders/`
+- Save and copy your **Client ID**.
+
+### 2) Add your Client ID
+
+Open `app.js`, find this line, and replace it:
+
+```js
+clientId: "PUT_YOUR_EVE_CLIENT_ID_HERE",
+```
+
+with your real Client ID.
+
+### 3) Test locally
+
+From repo root run:
+
+```bash
+python3 -m http.server 8000
+```
+
+Then open:
+
+- `http://localhost:8000`
+
+Click **Sign in with EVE SSO**.
+
+### 4) Deploy to GitHub Pages
+
+- Push repo to GitHub.
+- In GitHub repo settings: **Pages** → Source: `Deploy from branch`.
+- Branch: `main` (or your default), folder: `/ (root)`.
+- Save.
+- Open the Pages URL.
+- Make sure this exact URL is also in EVE Developer Portal callback list.
+
+---
+
+## Important notes
+
+- This is a **frontend-only** app (no server).
+- Tokens are saved in your browser local storage.
+- Do **not** put a client secret in this app.
+- First version is intentionally simple.
+
+## Next ideas
+
+- Add filtering (buy/sell, station, item name search).
+- Add CSV export.
+- Add wallet transactions.
+- Add basic profit calculations.
