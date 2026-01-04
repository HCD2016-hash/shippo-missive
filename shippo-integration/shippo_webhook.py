"""
Shippo Webhook Integration for Hub City Design Shipping Dashboard
Add this to your existing app.py or import it

Handles:
- transaction_created: New label created (has metadata, no address)
- transaction_updated: Label status changes
- track_updated: Full tracking with addresses

Database table: shippo_tracking (separate from YoPrint shipments)
"""

import json
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)

# Create blueprint for Shippo routes
shippo_bp = Blueprint('shippo', __name__)


def init_shippo_tables(db_connection_func):
    """
    Initialize Shippo tracking tables
    Call this from your init_db() function
    
    Args:
        db_connection_func: Your get_db() function
    """
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
            
            -- Address To (from track_updated)
            to_name TEXT,
            to_city TEXT,
            to_state TEXT,
            to_zip TEXT,
            to_country TEXT,
            
            -- Address From
            from_city TEXT,
            from_state TEXT,
            from_zip TEXT,
            from_country TEXT,
            
            -- Service info
            service_name TEXT,
            service_token TEXT,
            
            -- Tracking history stored as JSON
            tracking_history TEXT,
            
            -- Timestamps
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            status_date TEXT,
            delivered_at TEXT
        )
    ''')
    
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_shippo_tracking ON shippo_tracking(tracking_number)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_shippo_status ON shippo_tracking(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_shippo_created ON shippo_tracking(created_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_shippo_metadata ON shippo_tracking(metadata)')
    
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
    """
    Create Shippo routes with database access
    
    Args:
        get_db_func: Your get_db() function that returns a database connection
    
    Returns:
        Blueprint with all Shippo routes
    """
    
    @shippo_bp.route('/webhook/shippo', methods=['POST'])
    def shippo_webhook():
        """Receive Shippo webhooks"""
        try:
            payload = request.get_json()
            if not payload:
                return jsonify({'error': 'No payload'}), 400
            
            event = payload.get('event', 'unknown')
            data = payload.get('data', {})
            
            logger.info(f"[SHIPPO] Received webhook: {event}")
            
            conn = get_db_func()
            
            if event == 'transaction_created':
                handle_transaction_created(conn, data)
            elif event == 'transaction_updated':
                handle_transaction_updated(conn, data)
            elif event == 'track_updated':
                handle_track_updated(conn, data)
            else:
                logger.info(f"[SHIPPO] Unhandled event: {event}")
            
            conn.close()
            return jsonify({'received': True}), 200
            
        except Exception as e:
            logger.error(f"[SHIPPO] Webhook error: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 200  # Return 200 to prevent retries
    
    @shippo_bp.route('/api/shippo/shipments', methods=['GET'])
    def get_shippo_shipments():
        """Get all Shippo shipments for Missive iframe"""
        try:
            status = request.args.get('status')
            search = request.args.get('search', '')
            days = int(request.args.get('days', 90))
            limit = int(request.args.get('limit', 200))
            
            conn = get_db_func()
            cursor = conn.cursor()
            
            sql = f'''
                SELECT * FROM shippo_tracking 
                WHERE created_at >= datetime('now', '-{days} days')
                AND status != 'ERROR'
            '''
            params = []
            
            if status and status.upper() != 'ALL':
                sql += ' AND status = ?'
                params.append(status.upper())
            
            if search:
                sql += ''' AND (
                    tracking_number LIKE ? OR 
                    metadata LIKE ? OR 
                    to_city LIKE ? OR 
                    carrier LIKE ?
                )'''
                pattern = f'%{search}%'
                params.extend([pattern, pattern, pattern, pattern])
            
            sql += ' ORDER BY created_at DESC LIMIT ?'
            params.append(limit)
            
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            
            shipments = []
            for row in rows:
                shipment = dict(row)
                # Parse tracking history JSON
                if shipment.get('tracking_history'):
                    try:
                        shipment['tracking_history'] = json.loads(shipment['tracking_history'])
                    except:
                        shipment['tracking_history'] = []
                else:
                    shipment['tracking_history'] = []
                shipments.append(shipment)
            
            conn.close()
            
            return jsonify({
                'success': True,
                'count': len(shipments),
                'shipments': shipments
            })
            
        except Exception as e:
            logger.error(f"[SHIPPO] API error: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500
    
    @shippo_bp.route('/api/shippo/shipments/<shipment_id>', methods=['GET'])
    def get_shippo_shipment(shipment_id):
        """Get single shipment by ID or tracking number"""
        try:
            conn = get_db_func()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM shippo_tracking 
                WHERE id = ? OR tracking_number = ? OR transaction_id = ?
            ''', (shipment_id, shipment_id, shipment_id))
            
            row = cursor.fetchone()
            conn.close()
            
            if not row:
                return jsonify({'error': 'Not found'}), 404
            
            shipment = dict(row)
            if shipment.get('tracking_history'):
                try:
                    shipment['tracking_history'] = json.loads(shipment['tracking_history'])
                except:
                    shipment['tracking_history'] = []
            
            return jsonify({'success': True, 'shipment': shipment})
            
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @shippo_bp.route('/api/shippo/stats', methods=['GET'])
    def get_shippo_stats():
        """Get shipment stats"""
        try:
            days = int(request.args.get('days', 90))
            
            conn = get_db_func()
            cursor = conn.cursor()
            
            cursor.execute(f'''
                SELECT status, COUNT(*) as count
                FROM shippo_tracking 
                WHERE created_at >= datetime('now', '-{days} days')
                AND status != 'ERROR'
                GROUP BY status
            ''')
            
            rows = cursor.fetchall()
            conn.close()
            
            by_status = {row['status']: row['count'] for row in rows}
            total = sum(by_status.values())
            
            return jsonify({
                'success': True,
                'total': total,
                'by_status': by_status
            })
            
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    return shippo_bp


def handle_transaction_created(conn, data):
    """Handle transaction_created webhook - new label"""
    transaction_id = data.get('object_id')
    tracking_number = data.get('tracking_number')
    
    logger.info(f"[SHIPPO] Transaction created: {transaction_id} - {tracking_number}")
    
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO shippo_tracking (
            transaction_id, tracking_number, carrier, status, metadata,
            label_url, tracking_url, eta, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(transaction_id) DO UPDATE SET
            tracking_number = excluded.tracking_number,
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


def handle_transaction_updated(conn, data):
    """Handle transaction_updated webhook - status change"""
    transaction_id = data.get('object_id')
    tracking_number = data.get('tracking_number')
    
    logger.info(f"[SHIPPO] Transaction updated: {transaction_id} - {data.get('tracking_status')}")
    
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE shippo_tracking SET
            tracking_number = COALESCE(?, tracking_number),
            status = ?,
            eta = COALESCE(?, eta),
            updated_at = CURRENT_TIMESTAMP
        WHERE transaction_id = ?
    ''', (
        tracking_number,
        data.get('tracking_status', 'UNKNOWN'),
        data.get('eta'),
        transaction_id
    ))
    
    # If no rows updated, insert new
    if cursor.rowcount == 0:
        handle_transaction_created(conn, data)
    else:
        conn.commit()


def handle_track_updated(conn, data):
    """Handle track_updated webhook - has full address and tracking history"""
    tracking_number = data.get('tracking_number')
    transaction_id = data.get('transaction')
    
    logger.info(f"[SHIPPO] Track updated: {tracking_number}")
    
    address_to = data.get('address_to', {})
    address_from = data.get('address_from', {})
    tracking_status = data.get('tracking_status', {})
    service = data.get('servicelevel', {})
    
    cursor = conn.cursor()
    
    # Try to find existing record
    if transaction_id:
        cursor.execute('SELECT id FROM shippo_tracking WHERE transaction_id = ?', (transaction_id,))
    else:
        cursor.execute('SELECT id FROM shippo_tracking WHERE tracking_number = ?', (tracking_number,))
    
    existing = cursor.fetchone()
    
    carrier = (data.get('carrier') or detect_carrier(tracking_number)).upper()
    status = tracking_status.get('status', 'UNKNOWN') if isinstance(tracking_status, dict) else str(tracking_status)
    
    # Check if delivered
    delivered_at = None
    if status == 'DELIVERED':
        delivered_at = tracking_status.get('status_date') if isinstance(tracking_status, dict) else None
    
    if existing:
        cursor.execute('''
            UPDATE shippo_tracking SET
                tracking_number = COALESCE(?, tracking_number),
                carrier = ?,
                status = ?,
                status_details = ?,
                status_date = ?,
                eta = COALESCE(?, eta),
                to_name = COALESCE(?, to_name),
                to_city = ?,
                to_state = ?,
                to_zip = ?,
                to_country = ?,
                from_city = ?,
                from_state = ?,
                from_zip = ?,
                from_country = ?,
                service_name = ?,
                service_token = ?,
                tracking_history = ?,
                delivered_at = COALESCE(?, delivered_at),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (
            tracking_number,
            carrier,
            status,
            tracking_status.get('status_details') if isinstance(tracking_status, dict) else None,
            tracking_status.get('status_date') if isinstance(tracking_status, dict) else None,
            data.get('eta'),
            address_to.get('name'),
            address_to.get('city'),
            address_to.get('state'),
            address_to.get('zip'),
            address_to.get('country'),
            address_from.get('city'),
            address_from.get('state'),
            address_from.get('zip'),
            address_from.get('country'),
            service.get('name'),
            service.get('token'),
            json.dumps(data.get('tracking_history', [])),
            delivered_at,
            existing['id']
        ))
    else:
        # Create new record
        cursor.execute('''
            INSERT INTO shippo_tracking (
                transaction_id, tracking_number, carrier, status, status_details, status_date,
                eta, to_city, to_state, to_zip, to_country,
                from_city, from_state, from_zip, from_country,
                service_name, service_token, tracking_history, delivered_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            transaction_id or f'track_{tracking_number}',
            tracking_number,
            carrier,
            status,
            tracking_status.get('status_details') if isinstance(tracking_status, dict) else None,
            tracking_status.get('status_date') if isinstance(tracking_status, dict) else None,
            data.get('eta'),
            address_to.get('city'),
            address_to.get('state'),
            address_to.get('zip'),
            address_to.get('country'),
            address_from.get('city'),
            address_from.get('state'),
            address_from.get('zip'),
            address_from.get('country'),
            service.get('name'),
            service.get('token'),
            json.dumps(data.get('tracking_history', [])),
            delivered_at
        ))
    
    conn.commit()
