# Shippo Integration for Hub City Design Shipping Dashboard

This adds Shippo webhook tracking to your **existing** shipping dashboard at port 5000.

## Quick Integration (2 Steps)

### Step 1: Copy the webhook module

```bash
# On your Pi, copy shippo_webhook.py to your shipping-dashboard folder
cp shippo_webhook.py ~/shipping-dashboard/
```

### Step 2: Update your app.py

Add these lines to your existing `app.py`:

**At the top with other imports:**
```python
from shippo_webhook import shippo_bp, init_shippo_tables, create_shippo_routes
```

**In your `init_db()` function, add:**
```python
# Initialize Shippo tables
init_shippo_tables(get_db)
```

**After `app = Flask(__name__)` and CORS setup, add:**
```python
# Register Shippo webhook routes
shippo_routes = create_shippo_routes(get_db)
app.register_blueprint(shippo_routes)
```

That's it! Restart your dashboard and the endpoints are live.

---

## Endpoints Added

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/webhook/shippo` | POST | Receives Shippo webhooks |
| `/api/shippo/shipments` | GET | List all tracked shipments |
| `/api/shippo/shipments/<id>` | GET | Get single shipment |
| `/api/shippo/stats` | GET | Get status counts |

### Query Parameters for `/api/shippo/shipments`

- `status` - Filter: PRE_TRANSIT, TRANSIT, DELIVERED, FAILURE, or ALL
- `search` - Search tracking#, metadata, city, carrier
- `days` - How many days back (default: 90)
- `limit` - Max results (default: 200)

---

## Configure Shippo Webhooks

Go to: **https://apps.goshippo.com/settings/webhooks**

Update your Production webhook to:
```
https://hcd2016.ngrok.dev/webhook/shippo
```

Events to enable:
- ✅ `transaction_created`
- ✅ `transaction_updated`
- ✅ `track_updated`

---

## Missive iFrame Setup

For the Missive dashboard, point it to:
```
https://hcd2016.ngrok.dev/static/shippo-dashboard.html
```

Or host the HTML on GitHub Pages and have it query:
```
https://hcd2016.ngrok.dev/api/shippo/shipments
```

---

## Testing

After restarting your dashboard:

```bash
# Test the webhook endpoint
curl -X POST https://hcd2016.ngrok.dev/webhook/shippo \
  -H "Content-Type: application/json" \
  -d '{"event": "test", "data": {}}'

# Test the API
curl https://hcd2016.ngrok.dev/api/shippo/shipments

# Check health
curl https://hcd2016.ngrok.dev/health
```

---

## Database

Creates a new table `shippo_tracking` in your existing `shipping.db`.

To view data:
```bash
sqlite3 shipping.db "SELECT tracking_number, status, to_city, metadata FROM shippo_tracking LIMIT 10;"
```

---

## What You Get

- ✅ Live tracking updates via webhooks
- ✅ Ship-to addresses (city, state, zip)  
- ✅ YoPrint metadata (SO numbers)
- ✅ Full tracking history with locations
- ✅ Carrier detection (UPS, FedEx, USPS)
- ✅ ETA tracking
- ✅ Delivery timestamps
- ✅ No separate server needed!
