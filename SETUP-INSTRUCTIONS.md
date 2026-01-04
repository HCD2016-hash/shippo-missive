# Shippo Webhook Integration Setup

## Overview

Add Shippo webhook tracking to the existing Hub City Design shipping dashboard (Python/Flask on Raspberry Pi). This enables live package tracking with full addresses and YoPrint metadata.

**Architecture:**
```
Shippo Webhooks ──► Pi Flask App (port 5000) ──► SQLite DB
                         ▲
                         │
              Missive iframe (GitHub Pages) queries /api/shippo/*
```

---

## Part 1: Update Pi Shipping Dashboard

### Files to Modify

**Location:** `~/HCD-Shipping/` on Raspberry Pi

### Step 1: Create `shippo_webhook.py`

Create a new file `~/HCD-Shipping/shippo_webhook.py` with this content:

```python
"""
Shippo Webhook Integration for Hub City Design Shipping Dashboard
Handles: transaction_created, transaction_updated, track_updated
"""

import json
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)

shippo_bp = Blueprint('shippo', __name__)


def init_shippo_tables(db_connection_func):
    """Initialize Shippo tracking tables - call from init_db()"""
    conn = db_connection_func()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS shippo_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id TEXT UNIQUE NOT NULL,
            tracking_number TEXT,
            carrier TEXT,
            status TEXT DEFAULT 'UNKNOWN',
            status_details TEXT,
            metadata TEXT,
            label_url TEXT,
            tracking_url TEXT,
            eta TEXT,
            to_name TEXT,
            to_city TEXT,
            to_state TEXT,
            to_zip TEXT,
            to_country TEXT,
            from_city TEXT,
            from_state TEXT,
            from_zip TEXT,
            from_country TEXT,
            service_name TEXT,
            service_token TEXT,
            tracking_history TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            status_date TEXT,
            delivered_at TEXT
        )
    ''')
    
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_shippo_tracking ON shippo_tracking(tracking_number)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_shippo_status ON shippo_tracking(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_shippo_created ON shippo_tracking(created_at)')
    
    conn.commit()
    conn.close()
    logger.info("Shippo tracking tables initialized")


def detect_carrier(tracking_number):
    """Detect carrier from tracking number pattern"""
    if not tracking_number:
        return 'UNKNOWN'
    tn = tracking_number.upper()
    if tn.startswith('1Z'):
        return 'UPS'
    if len(tn) >= 12 and tn.isdigit():
        return 'FEDEX'
    if (len(tn) >= 16 and tn[0] == '9' and tn.isdigit()) or \
       (len(tn) == 13 and tn[:2].isalpha() and tn[-2:] == 'US'):
        return 'USPS'
    if len(tn) in [10, 11] and tn.isdigit():
        return 'DHL'
    return 'CARRIER'


def create_shippo_routes(get_db_func):
    """Create Shippo routes with database access"""
    
    @shippo_bp.route('/webhook/shippo', methods=['POST'])
    def shippo_webhook():
        """Receive Shippo webhooks"""
        try:
            payload = request.get_json()
            if not payload:
                return jsonify({'error': 'No payload'}), 400
            
            event = payload.get('event', 'unknown')
            data = payload.get('data', {})
            
            logger.info(f"[SHIPPO] Webhook: {event}")
            
            conn = get_db_func()
            
            if event == 'transaction_created':
                _handle_transaction(conn, data, is_create=True)
            elif event == 'transaction_updated':
                _handle_transaction(conn, data, is_create=False)
            elif event == 'track_updated':
                _handle_track_updated(conn, data)
            
            conn.close()
            return jsonify({'received': True}), 200
            
        except Exception as e:
            logger.error(f"[SHIPPO] Error: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 200
    
    @shippo_bp.route('/api/shippo/shipments', methods=['GET'])
    def get_shippo_shipments():
        """List shipments for Missive iframe"""
        try:
            status = request.args.get('status')
            search = request.args.get('search', '')
            days = int(request.args.get('days', 90))
            limit = int(request.args.get('limit', 200))
            
            conn = get_db_func()
            cursor = conn.cursor()
            
            sql = f"SELECT * FROM shippo_tracking WHERE created_at >= datetime('now', '-{days} days') AND status != 'ERROR'"
            params = []
            
            if status and status.upper() != 'ALL':
                sql += ' AND status = ?'
                params.append(status.upper())
            
            if search:
                sql += ' AND (tracking_number LIKE ? OR metadata LIKE ? OR to_city LIKE ? OR carrier LIKE ?)'
                pattern = f'%{search}%'
                params.extend([pattern, pattern, pattern, pattern])
            
            sql += ' ORDER BY created_at DESC LIMIT ?'
            params.append(limit)
            
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            
            shipments = []
            for row in rows:
                s = dict(row)
                if s.get('tracking_history'):
                    try:
                        s['tracking_history'] = json.loads(s['tracking_history'])
                    except:
                        s['tracking_history'] = []
                else:
                    s['tracking_history'] = []
                shipments.append(s)
            
            conn.close()
            return jsonify({'success': True, 'count': len(shipments), 'shipments': shipments})
            
        except Exception as e:
            logger.error(f"[SHIPPO] API error: {e}")
            return jsonify({'error': str(e)}), 500
    
    @shippo_bp.route('/api/shippo/shipments/<shipment_id>', methods=['GET'])
    def get_shippo_shipment(shipment_id):
        """Get single shipment"""
        try:
            conn = get_db_func()
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM shippo_tracking WHERE id = ? OR tracking_number = ? OR transaction_id = ?', 
                          (shipment_id, shipment_id, shipment_id))
            row = cursor.fetchone()
            conn.close()
            
            if not row:
                return jsonify({'error': 'Not found'}), 404
            
            s = dict(row)
            if s.get('tracking_history'):
                try:
                    s['tracking_history'] = json.loads(s['tracking_history'])
                except:
                    s['tracking_history'] = []
            
            return jsonify({'success': True, 'shipment': s})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @shippo_bp.route('/api/shippo/stats', methods=['GET'])
    def get_shippo_stats():
        """Get status counts"""
        try:
            days = int(request.args.get('days', 90))
            conn = get_db_func()
            cursor = conn.cursor()
            cursor.execute(f"SELECT status, COUNT(*) as count FROM shippo_tracking WHERE created_at >= datetime('now', '-{days} days') AND status != 'ERROR' GROUP BY status")
            rows = cursor.fetchall()
            conn.close()
            
            by_status = {row['status']: row['count'] for row in rows}
            return jsonify({'success': True, 'total': sum(by_status.values()), 'by_status': by_status})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    def _handle_transaction(conn, data, is_create=True):
        """Handle transaction_created/updated"""
        transaction_id = data.get('object_id')
        tracking_number = data.get('tracking_number')
        
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO shippo_tracking (transaction_id, tracking_number, carrier, status, metadata, label_url, tracking_url, eta, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(transaction_id) DO UPDATE SET
                tracking_number = COALESCE(excluded.tracking_number, tracking_number),
                status = excluded.status,
                metadata = COALESCE(excluded.metadata, metadata),
                label_url = COALESCE(excluded.label_url, label_url),
                tracking_url = COALESCE(excluded.tracking_url, tracking_url),
                eta = COALESCE(excluded.eta, eta),
                updated_at = CURRENT_TIMESTAMP
        ''', (
            transaction_id,
            tracking_number,
            detect_carrier(tracking_number),
            data.get('tracking_status', 'PRE_TRANSIT'),
            data.get('metadata'),
            data.get('label_url'),
            data.get('tracking_url_provider'),
            data.get('eta'),
            data.get('object_created')
        ))
        conn.commit()
    
    def _handle_track_updated(conn, data):
        """Handle track_updated - has addresses and history"""
        tracking_number = data.get('tracking_number')
        transaction_id = data.get('transaction')
        
        address_to = data.get('address_to', {})
        address_from = data.get('address_from', {})
        tracking_status = data.get('tracking_status', {})
        service = data.get('servicelevel', {})
        
        carrier = (data.get('carrier') or detect_carrier(tracking_number)).upper()
        status = tracking_status.get('status', 'UNKNOWN') if isinstance(tracking_status, dict) else str(tracking_status)
        delivered_at = tracking_status.get('status_date') if status == 'DELIVERED' and isinstance(tracking_status, dict) else None
        
        cursor = conn.cursor()
        
        # Check if exists
        if transaction_id:
            cursor.execute('SELECT id FROM shippo_tracking WHERE transaction_id = ?', (transaction_id,))
        else:
            cursor.execute('SELECT id FROM shippo_tracking WHERE tracking_number = ?', (tracking_number,))
        
        existing = cursor.fetchone()
        
        if existing:
            cursor.execute('''
                UPDATE shippo_tracking SET
                    tracking_number = COALESCE(?, tracking_number), carrier = ?, status = ?,
                    status_details = ?, status_date = ?, eta = COALESCE(?, eta),
                    to_city = ?, to_state = ?, to_zip = ?, to_country = ?,
                    from_city = ?, from_state = ?, from_zip = ?, from_country = ?,
                    service_name = ?, service_token = ?, tracking_history = ?,
                    delivered_at = COALESCE(?, delivered_at), updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (
                tracking_number, carrier, status,
                tracking_status.get('status_details') if isinstance(tracking_status, dict) else None,
                tracking_status.get('status_date') if isinstance(tracking_status, dict) else None,
                data.get('eta'),
                address_to.get('city'), address_to.get('state'), address_to.get('zip'), address_to.get('country'),
                address_from.get('city'), address_from.get('state'), address_from.get('zip'), address_from.get('country'),
                service.get('name'), service.get('token'),
                json.dumps(data.get('tracking_history', [])),
                delivered_at,
                existing['id']
            ))
        else:
            cursor.execute('''
                INSERT INTO shippo_tracking (
                    transaction_id, tracking_number, carrier, status, status_details, status_date, eta,
                    to_city, to_state, to_zip, to_country, from_city, from_state, from_zip, from_country,
                    service_name, service_token, tracking_history, delivered_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                transaction_id or f'track_{tracking_number}',
                tracking_number, carrier, status,
                tracking_status.get('status_details') if isinstance(tracking_status, dict) else None,
                tracking_status.get('status_date') if isinstance(tracking_status, dict) else None,
                data.get('eta'),
                address_to.get('city'), address_to.get('state'), address_to.get('zip'), address_to.get('country'),
                address_from.get('city'), address_from.get('state'), address_from.get('zip'), address_from.get('country'),
                service.get('name'), service.get('token'),
                json.dumps(data.get('tracking_history', [])),
                delivered_at
            ))
        conn.commit()
    
    return shippo_bp
```

### Step 2: Modify `app.py`

Make these 3 changes to the existing `app.py`:

**1. Add import at top of file (with other imports):**
```python
from shippo_webhook import init_shippo_tables, create_shippo_routes
```

**2. In the `init_db()` function, add this line at the end (before `conn.close()`):**
```python
    # Initialize Shippo tracking tables
    init_shippo_tables(get_db)
```

**3. After `CORS(app)` line, add:**
```python
# Register Shippo webhook routes
app.register_blueprint(create_shippo_routes(get_db))
```

### Step 3: Restart the Dashboard

```bash
sudo systemctl restart HCD-Shipping
# Or if running manually:
# pkill -f "python.*run.py" && cd ~/HCD-Shipping && python run.py &
```

### Step 4: Verify

```bash
# Test health
curl https://hcd2016.ngrok.dev/health

# Test new Shippo endpoint
curl https://hcd2016.ngrok.dev/api/shippo/shipments

# Test webhook endpoint
curl -X POST https://hcd2016.ngrok.dev/webhook/shippo \
  -H "Content-Type: application/json" \
  -d '{"event": "test", "data": {}}'
```

---

## Part 2: Configure Shippo Webhooks

Go to: **https://apps.goshippo.com/settings/webhooks**

Update the **Production** webhook URL to:
```
https://hcd2016.ngrok.dev/webhook/shippo
```

Ensure these events are enabled:
- ✅ transaction_created
- ✅ transaction_updated  
- ✅ track_updated

---

## Part 3: Update Missive Iframe (GitHub Pages)

The existing Shippo Missive iframe repo needs to be updated to query the Pi API instead of Shippo directly.

**Repository:** The shippo-missive GitHub Pages repo

**Change the API_BASE constant** in the HTML/JS:
```javascript
// OLD - direct to Shippo (doesn't work well)
// const API_BASE = 'https://api.goshippo.com';

// NEW - query Pi server which has webhook data
const API_BASE = 'https://hcd2016.ngrok.dev';
```

**Update the fetch calls** to use the new endpoints:
- `/api/shippo/shipments` - list all shipments
- `/api/shippo/shipments/:id` - single shipment
- `/api/shippo/stats` - status counts

---

## API Reference

### GET /api/shippo/shipments

Query parameters:
- `status` - Filter: PRE_TRANSIT, TRANSIT, DELIVERED, FAILURE, ALL
- `search` - Search tracking#, metadata, city, carrier
- `days` - Days back (default: 90)
- `limit` - Max results (default: 200)

Response:
```json
{
  "success": true,
  "count": 42,
  "shipments": [
    {
      "id": 1,
      "tracking_number": "1ZR6535H0311635634",
      "carrier": "UPS",
      "status": "DELIVERED",
      "metadata": "Sales Order SO1282-SHIP-1490",
      "to_city": "Rockport",
      "to_state": "TX",
      "to_zip": "78382",
      "tracking_history": [...],
      "created_at": "2025-11-21T17:08:08Z"
    }
  ]
}
```

### GET /api/shippo/shipments/:id

Get single shipment by ID, tracking number, or transaction ID.

### GET /api/shippo/stats

Returns status counts:
```json
{
  "success": true,
  "total": 42,
  "by_status": {
    "PRE_TRANSIT": 5,
    "TRANSIT": 12,
    "DELIVERED": 25
  }
}
```

### POST /webhook/shippo

Receives Shippo webhook events. No authentication required (Shippo doesn't support webhook signatures for custom endpoints).

---

## Troubleshooting

**Webhooks not arriving?**
- Check ngrok is running: `curl https://hcd2016.ngrok.dev/health`
- Check logs: `tail -f ~/HCD-Shipping/logs/app.log`
- Verify webhook URL in Shippo dashboard

**Empty shipments list?**
- Webhooks only capture NEW events after setup
- Existing shipments won't appear until they get a tracking update
- Create a test label to verify flow

**Database errors?**
- Check table exists: `sqlite3 shipping.db ".tables"`
- Manually init: `python -c "from app import init_db; init_db()"`
