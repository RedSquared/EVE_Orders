# EVE Orders Dashboard — User Guide

A static, client-side dashboard for monitoring your EVE Online market orders. No server required — runs directly on GitHub Pages.

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Dashboard Overview](#dashboard-overview)
3. [Wallet Bar](#wallet-bar)
4. [Stats Bar](#stats-bar)
5. [Station Breakdown](#station-breakdown)
6. [Market Orders Table](#market-orders-table)
7. [Filters](#filters)
8. [Undercut Detection](#undercut-detection)
9. [Copy Button](#copy-button)
10. [Multi-Account Support](#multi-account-support)
11. [Corp Orders](#corp-orders)
12. [Settings](#settings)
13. [Setup for Self-Hosting](#setup-for-self-hosting)

---

## Getting Started

1. Open the app in your browser.
2. Click **Sign In with EVE Online**.
3. Authenticate with your EVE account in the EVE SSO window that opens.
4. You are returned to the dashboard and your orders load automatically.

> Your tokens are stored in `localStorage` in your browser. They are **never** sent anywhere except the official EVE SSO (`login.eveonline.com`) and ESI (`esi.evetech.net`) servers.

---

## Dashboard Overview

After signing in you will see three main sections stacked vertically:

| Section | Description |
|---------|-------------|
| **Wallet Bar** | Your personal and corp ISK balances |
| **Stats Bar** | At-a-glance summary cards |
| **Station Breakdown** | Orders grouped by station |
| **Market Orders Table** | Full order list with filters and sorting |

A **?** button in the top-right corner of the header opens this guide inside the app.

---

## Wallet Bar

The wallet bar sits below the stats bar and shows your ISK balances:

- **Personal Wallet** — Your character's liquid ISK balance.
- **Corp Wallet** — Your corporation's wallet balance. Use the division selector (drop-down next to the label) to switch between the up to seven wallet divisions. Division 1 is the Master Wallet by default. Your selected division is remembered between sessions.

> The corp wallet requires the **Accountant** or **Market Manager** role in your corporation. If your character lacks this role, the corp wallet card will not appear.

---

## Stats Bar

Each card shows a key metric. Hover any card for a tooltip explaining it.

| Card | Description |
|------|-------------|
| **Personal Slots Free** | How many more orders you can place. Calculated from your Trade skills (Trade, Retail, Wholesale, Tycoon). Turns orange above 70% usage, red above 90%. Corp orders *you* placed also consume your personal slots. |
| **Corp Orders** | Count of active corp orders visible to your character, split by sell and buy. Hidden if you lack corp roles. |
| **Undercut** | How many of your active orders have been undercut by a competitor. Green = all best price, red = undercut orders exist. Counts personal orders for everyone; also includes corp orders if you have the corp role. |
| **Sell Value** | Total ISK value of all active sell orders (price × remaining quantity). |
| **Buy Volume** | Total ISK committed to active buy orders (price × remaining quantity). |
| **Most Valuable Item** | The corp sell item with the highest unit price. |
| **Most Valuable Order** | The single corp order with the highest total value. |

When a **station filter** is active (see [Filters](#filters)), all cards except Personal Slots react to it and show figures for that station only.

---

## Station Breakdown

A collapsible table beneath the stats bar groups your orders by station and shows:

- Station name
- Sell order count and total sell value
- Buy order count and total buy volume
- Number of undercut orders at that station

Click any station row to filter the orders table to that station only. Click the **Station Breakdown** header to collapse or expand the section.

---

## Market Orders Table

The main table lists every active order with these columns:

| Column | Description |
|--------|-------------|
| ⎘ | Copy suggested undercut price and open in-game market window |
| **Item** | Item name, icon, and source badge (CORP for corporation orders) |
| **Type** | Sell or Buy |
| **Status** | Undercut status — Best Price, Undercut (with ISK difference), or a loading spinner |
| **Unit Price** | Your current order price |
| **Qty** | Remaining / total quantity |
| **Order Total** | Price × remaining quantity |
| **Location** | Station or structure name |
| **Expires** | Countdown to expiry |

Click any **column header** to sort by that column. Click again to reverse the sort direction.

---

## Filters

Use the filter controls in the toolbar above the table:

| Filter | Options | Effect |
|--------|---------|--------|
| **All Types** | All Types / Sell / Buy | Show only sell orders, only buy orders, or both |
| **All Sources** | All Sources / Personal / Corp | Show personal orders, corp orders, or both |
| **All Status** | All Status / Best Price / Undercut / Dupes | Filter by undercut result. *Dupes* = more than one order for the same item at the same station |
| **Location chip** | Appears after clicking a station in the breakdown | Restricts the table to that one station. Click **✕** on the chip to clear |
| **Reset** | — | Clears all active filters at once |

---

## Undercut Detection

After the order list loads, the app fetches live market data in the background and compares your prices against competitors.

### Scope

- **Station** — Compares only against orders at the exact same station. Best for station traders who compete locally.
- **Region** — Compares against the best price anywhere in the region. Best for regional traders.

Change the scope in the **Settings (⚙)** popover.

### Ticks

EVE prices move in 0.01 ISK increments called *ticks*. The **Ticks** setting controls how many ticks below the current best price the Copy button will suggest. Default is **2 ticks** (0.02 ISK).

### Status indicators

| Status | Meaning |
|--------|---------|
| 🟢 Best Price | Your order is the best price at the chosen scope |
| 🔴 Undercut | A competitor has a better price; the difference is shown |
| ⟳ (spinner) | Market data is still loading |

---

## Copy Button (⎘)

Clicking the copy icon on a row does two things at once:

1. **Copies** the suggested undercut price to your clipboard.
2. **Opens** the item's market window inside the EVE client (requires the EVE client to be running).

Paste the price directly into the **Modify Order** dialog in-game. If the in-game window cannot be opened (client not running, or scope not granted on older logins) the button shows **!** briefly.

---

## Multi-Account Support

You can sign in with multiple EVE characters:

- Open the **account switcher** in the top-right corner of the header.
- Click a character to switch to them — orders reload automatically.
- Click **Add Account** to authenticate another character.
- Click the **✕** next to a character to remove them from the app.

Each character's tokens are stored independently and refresh automatically.

---

## Corp Orders

Corp orders are visible when your character holds the **Accountant** or **Market Manager** role in the corporation.

- If the role is **present**: corp orders appear in the table alongside personal orders, corp stat cards are shown, and the corp wallet appears in the wallet bar.
- If the role is **missing**: a notice card is shown in the stats bar, the Corp source filter is disabled, and corp stat cards are hidden.

Corp orders placed by *other* corporation members appear in the table but do **not** count against your personal order slot limit. Only corp orders you personally placed consume your slots.

---

## Settings

Open the settings popover with the **⚙** button in the toolbar:

| Setting | Description |
|---------|-------------|
| **Scope** | Station or Region undercut comparison |
| **Ticks** | How many 0.01 ISK ticks to undercut by (default: 2) |
| **Market checked** | Timestamp of the last completed undercut data fetch |
| **Compact** | Hides item icons and reduces row height for a denser view |
| **Refresh** | Manually reload all orders and re-run the undercut check |

---

## Setup for Self-Hosting

If you want to host your own instance on GitHub Pages:

### 1. Create an EVE Developer Application

1. Go to [https://developers.eveonline.com/](https://developers.eveonline.com/) and sign in.
2. Click **Create New Application**.
3. Fill in:
   - **Name**: anything, e.g. `My Orders Dashboard`
   - **Connection Type**: `Authentication & API Access`
   - **Permissions** — add all of these scopes:
     - `esi-markets.read_character_orders.v1`
     - `esi-markets.read_corporation_orders.v1`
     - `esi-skills.read_skills.v1`
     - `esi-ui.open_window.v1`
     - `esi-wallet.read_character_wallet.v1`
     - `esi-wallet.read_corporation_wallets.v1`
   - **Callback URL**: your GitHub Pages URL, e.g.
     ```
     https://<your-username>.github.io/EVE_Orders/
     ```
4. Click **Create Application** and copy the **Client ID**.

### 2. Hardcode your Client ID (recommended)

Open `index.html` and find this line near the top of the `<script>` block:

```js
const HARDCODED_CLIENT_ID = '';
```

Paste your Client ID between the quotes. This saves you from entering it on every visit.

### 3. Enable GitHub Pages

In your repository **Settings → Pages**, set the source to your `main` branch, root directory. Your app will be live at:

```
https://<your-username>.github.io/EVE_Orders/
```

Make sure this exactly matches the Callback URL you registered in step 1.

---

## Notes

- Upwell structure names are shown as *Player Structure* — resolving them requires an extra scope (`esi-universe.read_structures.v1`) which can be added to your EVE application if desired.
- All data is fetched directly from ESI in your browser. There is no backend server or third-party involved.
