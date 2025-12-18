# Shippo Dashboard for Missive

A custom iframe integration that displays your Shippo shipments directly in Missive's sidebar.

![Shippo Dashboard](https://img.shields.io/badge/Shippo-Dashboard-blue) ![Missive Integration](https://img.shields.io/badge/Missive-Integration-green)

## Features

- **Real-time shipment tracking** — View all outgoing packages from the last 90 days
- **Status filtering** — Filter by Pre-Transit, In Transit, Out for Delivery, Delivered, or Exception
- **Search** — Find shipments by tracking number, recipient name, city, or state
- **Tracking timeline** — Full tracking history with locations and timestamps
- **Quick actions** — Copy tracking numbers, view labels, track on carrier site
- **Auto-refresh** — Updates every 5 minutes
- **Dark/Light theme** — Automatically matches your system preference
- **Secure storage** — API token stored securely via Missive's storage API

## Installation

### 1. Deploy to GitHub Pages

1. Create a new repository on GitHub (e.g., `shippo-missive`)
2. Rename `shippo-missive.html` to `index.html`
3. Upload `index.html` to the repository
4. Go to **Settings → Pages**
5. Under "Source", select **Deploy from a branch**
6. Select `main` branch and `/ (root)` folder
7. Click **Save**
8. Wait 1-2 minutes for deployment

Your dashboard will be live at:
```
https://YOUR-USERNAME.github.io/shippo-missive/
```

### 2. Add to Missive

1. Open Missive
2. Go to **Settings → Integrations**
3. Scroll to **Custom integrations**
4. Click **Add integration**
5. Enter your GitHub Pages URL
6. Give it a name (e.g., "Shippo")
7. Click **Save**

### 3. Connect Your Shippo Account

1. Open the Shippo panel in Missive's sidebar
2. Enter your Shippo API token
3. Click **Connect Shippo**

## Getting Your Shippo API Token

1. Log in to [Shippo](https://goshippo.com)
2. Go to **Settings → API**
3. Copy your **Live API Token** (starts with `shippo_live_`)

> ⚠️ Use your **Live** token to see real shipments. Test tokens only show test data.

## Usage

### Status Filters

| Status | Description |
|--------|-------------|
| **Pre-Transit** | Label created, not yet scanned by carrier |
| **In Transit** | Package is moving through carrier network |
| **Out for Delivery** | On the truck for final delivery |
| **Delivered** | Successfully delivered |
| **Exception** | Delivery issue or failed attempt |

### Quick Actions

- **Click tracking number** — Copies to clipboard
- **Click shipment row** — Opens detailed view
- **View Label** — Opens shipping label PDF
- **Track on Carrier** — Opens carrier's tracking page

### Search

Search works across:
- Tracking numbers
- Recipient names
- City names
- State abbreviations

## Technical Details

### API Endpoints Used

- `GET /transactions` — List all purchased labels
- `GET /tracks/{carrier}/{tracking_number}` — Get tracking history

### Data Refresh

- Manual refresh via the ↻ button
- Auto-refresh every 5 minutes
- Loads last 90 days of shipments (Shippo API limit)

### Security

- API token stored in Missive's secure storage (`Missive.storeSet`)
- Token never exposed in code or URL
- Falls back to localStorage for local development

## Troubleshooting

### "Invalid API token" error
- Verify you're using a Live token (not Test)
- Check for extra spaces when copying
- Regenerate token in Shippo settings if needed

### No shipments showing
- Confirm you have shipments in the last 90 days
- Check that labels were purchased (not just rates retrieved)
- Try the refresh button

### Tracking history not loading
- Some carriers have delayed tracking updates
- Pre-transit shipments won't have tracking events yet

## Development

To run locally:

1. Clone the repository
2. Serve with any static server:
   ```bash
   npx serve .
   # or
   python -m http.server 8000
   ```
3. For Missive integration testing, use [ngrok](https://ngrok.com) or [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/) for HTTPS

## License

MIT License — Free to use and modify.

---

Built for [Hub City Design](https://hubcitydesignlbk.com) | Powered by [Shippo API](https://goshippo.com/docs/intro)
