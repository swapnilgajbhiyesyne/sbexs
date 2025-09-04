import os
import logging
from flask import Flask, render_template, request, jsonify, make_response
from scanner import BTCOptionsScanner
import io
import csv

logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "btc-options-scanner-secret-key")

@app.route('/')
def index():
    """Main page with the scanner interface"""
    return render_template('index.html')

@app.route('/scan', methods=['POST'])
def scan_options():
    """Handle the options scanning request"""
    try:
        # Get form data
        data = request.get_json()
        
        # Create scanner instance
        scanner = BTCOptionsScanner()
        
        # Parse parameters
        params = {
            'dte_max': data.get('dte_max'),
            'expiry': data.get('expiry'),
            'side': data.get('side', 'both'),
            'delta_band': data.get('delta_band'),
            'prem_min': data.get('prem_min'),
            'prem_max': data.get('prem_max'),
            'premium_in_btc': data.get('premium_in_btc', False),
            'limit': data.get('limit', 200),
            'sort': data.get('sort', 'pop_delta'),
            'desc': data.get('desc', True)
        }
        
        # Scan options
        results = scanner.scan(**params)
        
        return jsonify({
            'success': True,
            'data': results['data'],
            'btc_spot': results['btc_spot'],
            'total_count': results['total_count']
        })
        
    except Exception as e:
        logging.error(f"Error in scan_options: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/export', methods=['POST'])
def export_csv():
    """Export scan results to CSV"""
    try:
        data = request.get_json()
        
        # Create scanner instance
        scanner = BTCOptionsScanner()
        
        # Parse parameters (same as scan)
        params = {
            'dte_max': data.get('dte_max'),
            'expiry': data.get('expiry'),
            'side': data.get('side', 'both'),
            'delta_band': data.get('delta_band'),
            'prem_min': data.get('prem_min'),
            'prem_max': data.get('prem_max'),
            'premium_in_btc': data.get('premium_in_btc', False),
            'limit': None,  # Export all results
            'sort': data.get('sort', 'pop_delta'),
            'desc': data.get('desc', True)
        }
        
        # Get all results
        results = scanner.scan(**params)
        
        # Create CSV
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=[
            'instrument', 'type', 'expiry', 'dte', 'spot', 'strike', 
            'iv', 'delta', 'premium_native', 'premium_usd', 
            'breakeven', 'pop_delta', 'pop_logN'
        ])
        writer.writeheader()
        writer.writerows(results['data'])
        
        # Create response
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = 'attachment; filename=btc_options_scan.csv'
        
        return response
        
    except Exception as e:
        logging.error(f"Error in export_csv: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
