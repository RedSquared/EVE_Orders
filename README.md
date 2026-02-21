# EVE Orders Dashboard

A static, client-side dashboard for monitoring your EVE Online market orders — no server required, runs on GitHub Pages.

## Features

- Sign in with EVE SSO (PKCE OAuth2 — no client secret needed)
- View all active character orders
- Sell value summary, buy/sell counts
- Filter by order type, sort by any column
- Item icons and NPC station names resolved automatically
- Corp orders flagged with a CORP badge
- Token auto-refresh — stay logged in without re-authenticating

## Setup

### 1. Create an EVE Application

1. Go to [https://developers.eveonline.com/](https://developers.eveonline.com/) and log in
2. Click **Create New Application**
3. Fill in:
   - **Name**: anything (e.g. `My Orders Dashboard`)
   - **Description**: anything
   - **Connection Type**: `Authentication & API Access`
   - **Permissions**: add `esi-markets.read_character_orders.v1`
   - **Callback URL**: your GitHub Pages URL, e.g.
     ```
     https://<your-username>.github.io/EVE_Orders/
     ```
4. Click **Create Application** and copy the **Client ID**

### 2. (Optional) Hardcode your Client ID

Open `index.html` and find this line near the top of the `<script>` block:

```js
const HARDCODED_CLIENT_ID = '';
```

Paste your Client ID between the quotes. Otherwise you can enter it in the text field each visit (it gets saved to `localStorage` after the first login).

### 3. Enable GitHub Pages

In your repository settings → **Pages** → set the source to the `main`/`master` branch, root directory. Your app will be live at:

```
https://<your-username>.github.io/EVE_Orders/
```

Make sure this matches the Callback URL you registered in step 1.

## Notes

- Tokens are stored in `localStorage` and are never sent anywhere except the official EVE SSO and ESI endpoints.
- Upwell structure names are shown as *Player Structure* — resolving them requires an extra scope (`esi-universe.read_structures.v1`); you can add it later.
- The ESI character orders endpoint also returns orders placed on behalf of your corporation (`is_corporation: true`), so corp orders appear automatically if your character placed them.
