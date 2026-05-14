from flask import Flask, request, jsonify, session
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import firebase_admin
from firebase_admin import credentials, db
from datetime import datetime
import random
import string
import hashlib
import hmac
import secrets
from functools import wraps
import requests
import uuid
import os
import json
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from flask import render_template, send_from_directory

# ==================== LOAD ENVIRONMENT VARIABLES ====================

load_dotenv()

# ==================== FLASK APP CONFIGURATION ====================

app = Flask(__name__)

app.secret_key = os.environ.get(
    'SECRET_KEY',
    secrets.token_hex(32)
)

CORS(app, supports_credentials=True)

# ==================== RATE LIMITER ====================

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# ==================== FIREBASE CONFIGURATION ====================

DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable not set")

# Initialize Firebase - Railway compatible
cred_json = os.environ.get("FIREBASE_CREDENTIALS")

if not cred_json:
    raise ValueError("FIREBASE_CREDENTIALS environment variable not set on Railway")

# Parse the JSON credentials
try:
    cred_dict = json.loads(cred_json)
    cred = credentials.Certificate(cred_dict)
    print("✅ Firebase credentials loaded successfully")
except json.JSONDecodeError as e:
    print(f"❌ Failed to parse FIREBASE_CREDENTIALS: {e}")
    raise

# Initialize Firebase app
try:
    firebase_admin.initialize_app(cred, {
        'databaseURL': DATABASE_URL
    })
    print("✅ Firebase initialized successfully")
except Exception as e:
    print(f"❌ Firebase initialization failed: {e}")
    raise
# ==================== PAWAPAY CONFIGURATION ====================

PAWAPAY_API_KEY = os.environ.get('PAWAPAY_API_KEY')

PAWAPAY_BASE_URL = os.environ.get(
    'PAWAPAY_BASE_URL',
    'https://api.pawapay.io/v1'
)

PAWAPAY_CORRESPONDENT = os.environ.get(
    'PAWAPAY_CORRESPONDENT',
    'MTN_MOMO_RWA'
)

PAWAPAY_CALLBACK_URL = os.environ.get(
    'PAWAPAY_CALLBACK_URL',
    'https://tumira-rwanda.up.railway.app/api/pawapay-webhook'
)

# ==================== APP CONSTANTS ====================

ACTIVATION_FEE = 2000
REFERRAL_COMMISSION = 2000

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_all_files(path):
    # Serve login.html for root path
    if not path:
        with open('login.html', 'r') as f:
            return f.read()
    
    # Serve any other file (login.js, login.css, etc.)
    try:
        with open(path, 'r') as f:
            content = f.read()
            # Set correct content type
            if path.endswith('.css'):
                return content, 200, {'Content-Type': 'text/css'}
            elif path.endswith('.js'):
                return content, 200, {'Content-Type': 'application/javascript'}
            else:
                return content
    except FileNotFoundError:
        return "File not found", 404
        
# ==================== PASSWORD HELPERS ====================
def hash_password(password):
    return generate_password_hash(password)

def verify_password(stored_hash, password):
    return check_password_hash(stored_hash, password)

# Generate random referral ID
def generate_random_referral_id():
    chars = string.ascii_uppercase + string.digits
    chars = chars.replace('O', '').replace('I', '')  # Remove confusing chars
    return ''.join(secrets.choice(chars) for _ in range(8))

# Authentication decorator
def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        phone = request.headers.get('X-User-Phone')
        if not phone:
            return jsonify({"status": "error", "message": "Authentication required"}), 401
        return f(*args, **kwargs)
    return decorated

# ==================== TRANSACTION LOGGING ====================

def log_transaction(transaction_type, phone, amount, transaction_id, status, details=None):
    """Log all financial transactions (deposits and payouts)"""
    try:
        transaction_log = {
            'type': transaction_type,  # 'deposit' or 'payout'
            'phone': phone,
            'amount': amount,
            'transactionId': transaction_id,
            'status': status,
            'timestamp': datetime.now().isoformat(),
            'details': details or {}
        }
        
        # Store in transactions node
        transactions_ref = db.reference(f'transactions/{phone}/{transaction_id}')
        transactions_ref.set(transaction_log)
        
        # Also store in global transaction log for admin purposes
        global_ref = db.reference(f'global_transactions/{transaction_id}')
        global_ref.set(transaction_log)
        
        return True
    except Exception as e:
        print(f"Transaction logging error: {str(e)}")
        return False

def update_transaction_status(transaction_id, new_status, additional_details=None):
    """Update transaction status"""
    try:
        # Find the transaction
        global_ref = db.reference(f'global_transactions/{transaction_id}')
        transaction = global_ref.get()
        
        if transaction:
            updates = {'status': new_status}
            if additional_details:
                updates['details'] = {**transaction.get('details', {}), **additional_details}
                updates['lastUpdated'] = datetime.now().isoformat()
            
            global_ref.update(updates)
            
            # Also update user-specific transaction
            phone = transaction.get('phone')
            if phone:
                user_txn_ref = db.reference(f'transactions/{phone}/{transaction_id}')
                user_txn_ref.update(updates)
        
        return True
    except Exception as e:
        print(f"Transaction status update error: {str(e)}")
        return False

# ==================== PAWAPAY HELPER FUNCTIONS ====================

def init_pawapay_payment(phone_number, amount, email, user_id, purpose="activation"):
    """
    Initiate a payment collection via Pawapay (deposit)
    Returns: deposit_id and status
    """
    try:
        # Format phone number (remove any prefixes, ensure 12-digit format with 250)
        formatted_phone = format_phone_number(phone_number)
        
        # Generate unique deposit ID
        deposit_id = str(uuid.uuid4())
        
        payload = {
            "depositId": deposit_id,
            "amount": str(amount),
            "currency": "RWF",
            "correspondent": PAWAPAY_CORRESPONDENT,
            "payer": {
                "type": "MSISDN",
                "address": {
                    "value": formatted_phone
                }
            },
            "customerTimestamp": datetime.now().isoformat(),
            "clientReferenceId": f"{purpose}_{user_id}_{int(datetime.now().timestamp())}",
            "customerMessage": f"Payment TUMIRA",
            "statementDescription": f"TUMIRA Payment",
            "callbackUrl": PAWAPAY_CALLBACK_URL
        }
        
        headers = {
            "Authorization": f"Bearer {PAWAPAY_API_KEY}",
            "Content-Type": "application/json"
        }
        
        response = requests.post(
            f"{PAWAPAY_BASE_URL}/deposits",
            json=payload,
            headers=headers,
            timeout=30
        )
        
        if response.status_code in [200, 201, 202]:
            result = response.json()
            
            # Log transaction initiation
            log_transaction(
                'deposit',
                phone_number,
                amount,
                deposit_id,
                'pending',
                {'purpose': purpose, 'initiation_response': result}
            )
            
            print("REQUEST:", payload)
            print("STATUS:", response.status_code)
            print("BODY:", response.text)
            
            return {
                "success": True,
                "depositId": deposit_id,
                "status": result.get("status"),
                "message": "Payment initiated successfully"
            }

        else:
            error_data = response.json() if response.text else {}
            
            print("REQUEST:", payload)
            print("STATUS:", response.status_code)
            print("BODY:", response.text)
            
            return {
                "success": False,
                "message": error_data.get("errorMessage", "Payment initiation failed"),
                "error_code": response.status_code
            }
            print("REQUEST:", payload)
            print("STATUS:", response.status_code)
            print("BODY:", response.text)
            
    except Exception as e:
        print(f"Pawapay payment initiation error: {str(e)}")
        return {"success": False, "message": str(e)}

def init_pawapay_payout(phone_number, amount, user_id, description="Referral commission"):
    """
    Send payout to user via Pawapay
    Returns: payout_id and status
    """
    try:
        # Format phone number
        formatted_phone = format_phone_number(phone_number)
        
        # Generate unique payout ID
        payout_id = str(uuid.uuid4())
        
        payload = {
            "payoutId": payout_id,
            "amount": str(amount),
            "currency": "RWF",
            "correspondent": PAWAPAY_CORRESPONDENT,
            "recipient": {
                "type": "MSISDN",
                "address": {
                    "value": formatted_phone
                }
            },
            "customerTimestamp": datetime.now().isoformat(),
            "statementDescription": description,
            "callbackUrl": PAWAPAY_CALLBACK_URL
        }
        
        headers = {
            "Authorization": f"Bearer {PAWAPAY_API_KEY}",
            "Content-Type": "application/json"
        }
        
        response = requests.post(
            f"{PAWAPAY_BASE_URL}/payouts",
            json=payload,
            headers=headers,
            timeout=30
        )
        
        if response.status_code in [200, 201, 202]:
            result = response.json()
            
            # Log transaction initiation
            log_transaction(
                'payout',
                phone_number,
                amount,
                payout_id,
                'pending',
                {'description': description, 'initiation_response': result}
            )
            print("REQUEST:", payload)
            print("STATUS:", response.status_code)
            print("BODY:", response.text)
            
            return {
                "success": True,
                "payoutId": payout_id,
                "status": result.get("status"),
                "message": "Payout initiated successfully"
            }
            print("REQUEST:", payload)
            print("STATUS:", response.status_code)
            print("BODY:", response.text)
        else:
            error_data = response.json() if response.text else {}

            print("REQUEST:", payload)
            print("STATUS:", response.status_code)
            print("BODY:", response.text)
            
            return {
                "success": False,
                "message": error_data.get("errorMessage", "Payout initiation failed"),
                "error_code": response.status_code
            }
            print("REQUEST:", payload)
            print("STATUS:", response.status_code)
            print("BODY:", response.text)
            
    except Exception as e:
        print(f"Pawapay payout initiation error: {str(e)}")
        return {"success": False, "message": str(e)}

def format_phone_number(phone):
    """
    Format phone number to required format (250XXXXXXXXX)
    Remove +, spaces, and ensure 12 digits starting with 250
    """
    # Remove any non-digit characters
    cleaned = ''.join(filter(str.isdigit, phone))
    
    # Remove leading 0 if present
    if cleaned.startswith('0'):
        cleaned = cleaned[1:]
    
    # If starts with 250, ensure it's exactly 12 digits
    if cleaned.startswith('250'):
        if len(cleaned) == 12:
            return cleaned
        elif len(cleaned) > 12:
            return cleaned[:12]
    
    # If starts with 250 but has more digits, truncate
    if cleaned.startswith('250'):
        return cleaned[:12]
    
    # Add 250 prefix if not present
    if len(cleaned) == 9:
        return f"250{cleaned}"
    elif len(cleaned) == 10:
        return f"250{cleaned[1:]}"
    
    return f"250{cleaned}"[:12]

def check_pawapay_transaction_status(transaction_id, transaction_type="deposit"):
    """
    Check status of a Pawapay transaction
    transaction_type: 'deposit' or 'payout'
    """
    try:
        headers = {
            "Authorization": f"Bearer {PAWAPAY_API_KEY}",
            "Content-Type": "application/json"
        }
        
        url = f"{PAWAPAY_BASE_URL}/{transaction_type}s/{transaction_id}"
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            # Handle response format (array or object)
            if isinstance(result, list) and len(result) > 0:
                return result[0]
            return result
        else:
            return None
            
    except Exception as e:
        print(f"Check status error: {str(e)}")
        return None

# ==================== USER MANAGEMENT ====================

@app.route('/api/register', methods=['POST'])
@limiter.limit("10 per minute")
def register_user():
    try:
        data = request.json
        
        phone = data.get('phone', '').strip()
        password = data.get('password', '')
        email = data.get('email', '').strip()
        referral_code = data.get('referralCode', '').strip()
        
        # Validation
        if not phone or not password or not email:
            return jsonify({"status": "error", "message": "All fields required"}), 400
        if len(password) < 6:
            return jsonify({"status": "error", "message": "Password must be at least 6 characters"}), 400
        if '@' not in email:
            return jsonify({"status": "error", "message": "Invalid email"}), 400
        
        user_node_name = phone
        
        # Check for duplicate phone
        user_ref = db.reference(f'users/{user_node_name}')
        existing_user = user_ref.get()
        
        if existing_user:
            return jsonify({"status": "error", "message": "Phone number already registered"}), 409

        # Check for duplicate email
        all_users_ref = db.reference('users')
        all_users = all_users_ref.get()
        
        if all_users:
            for user_id, user_data in all_users.items():
                if user_data.get('email') == email:
                    return jsonify({"status": "error", "message": "Email already registered"}), 409

        # Generate random referral ID
        temp_referral_id = generate_random_referral_id()
        
        # Hash password with Werkzeug
        hashed_password = hash_password(password)
        
        # Save user data
        user_ref.set({
            'phone': phone,
            'password': hashed_password,
            'email': email,
            'paid': False,
            'referralId': temp_referral_id,
            'registeredAt': datetime.now().isoformat(),
            'referrals': [],
            'totalEarned': 0,
            'pendingReferralCredit': False,
            'balance': 0  # Add balance for payout withdrawals
        })

        # Process referral if provided
        if referral_code and referral_code != "None" and referral_code != temp_referral_id:
            referrer = None
            referrer_phone = None
            if all_users:
                for user_id, user_data in all_users.items():
                    if user_data.get('referralId') == referral_code:
                        referrer = user_data
                        referrer_phone = user_id
                        break
            
            if referrer and referrer.get('paid') == True:
                user_ref.update({
                    'referredBy': referrer_phone,
                    'pendingReferralCredit': True
                })

        return jsonify({
            "status": "success", 
            "message": "User registered successfully!",
            "phone": phone
        }), 200

    except Exception as e:
        print("Registration Error:", str(e))
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/login', methods=['POST'])
@limiter.limit("5 per minute")
def login_user():
    try:
        data = request.json
        phone = data.get('phone', '').strip()
        password = data.get('password', '')
        
        if not phone or not password:
            return jsonify({"status": "error", "message": "Phone and password required"}), 400
        
        user_ref = db.reference(f'users/{phone}')
        user_data = user_ref.get()
        
        if not user_data:
            return jsonify({"status": "error", "message": "Phone number not found"}), 404
        
        # Verify password using Werkzeug
        if not verify_password(user_data.get('password'), password):
            return jsonify({"status": "error", "message": "Incorrect password"}), 401
        
        user_response = {
            'phone': user_data.get('phone'),
            'email': user_data.get('email'),
            'paid': user_data.get('paid', False),
            'registeredAt': user_data.get('registeredAt'),
            'referralId': user_data.get('referralId'),
            'totalEarned': user_data.get('totalEarned', 0),
            'referrals': user_data.get('referrals', []),
            'balance': user_data.get('balance', 0)
        }
        
        return jsonify({
            "status": "success",
            "message": "Login successful",
            "user": user_response
        }), 200
        
    except Exception as e:
        print("Login Error:", str(e))
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/user/<phone>', methods=['GET'])
def get_user(phone):
    try:
        print(f"🔍 Fetching user: {phone}")
        user_ref = db.reference(f'users/{phone}')
        user_data = user_ref.get()
        
        if user_data:
            print(f"✅ User found: {user_data.get('phone')}, Paid: {user_data.get('paid')}")
            if 'password' in user_data:
                del user_data['password']
            return jsonify({
                "status": "success",
                "user": user_data
            }), 200
        else:
            print(f"❌ User not found: {phone}")
            return jsonify({
                "status": "error",
                "message": "User not found"
            }), 404
    except Exception as e:
        print(f"🔥 Error fetching user: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/update-referral-id', methods=['POST'])
def update_referral_id():
    try:
        data = request.json
        phone = data.get('phone')
        new_referral_id = data.get('newReferralId')
        
        if not phone or not new_referral_id:
            return jsonify({"status": "error", "message": "Missing data"}), 400
        
        user_ref = db.reference(f'users/{phone}')
        user_data = user_ref.get()
        
        if not user_data:
            return jsonify({"status": "error", "message": "User not found"}), 404
        
        all_users = db.reference('users').get()
        if all_users:
            for user_id, user in all_users.items():
                if user.get('referralId') == new_referral_id and user_id != phone:
                    new_referral_id = generate_random_referral_id()
        
        user_ref.update({'referralId': new_referral_id})
        
        return jsonify({
            "status": "success",
            "message": "Referral ID updated",
            "referralId": new_referral_id
        }), 200
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ==================== PAYMENT MANAGEMENT (PAWAPAY INTEGRATION) ====================

@app.route('/api/initiate-payment', methods=['POST'])
@limiter.limit("3 per minute")
def initiate_payment():
    """Initiate payment collection via Pawapay"""
    try:
        data = request.json
        phone = data.get('phone')
        amount = data.get('amount', ACTIVATION_FEE)
        email = data.get('email')
        
        if not phone or not amount:
            return jsonify({"status": "error", "message": "Missing payment data"}), 400
        
        # Check if user already paid
        user_ref = db.reference(f'users/{phone}')
        user_data = user_ref.get()
        
        if not user_data:
            return jsonify({"status": "error", "message": "User not found"}), 404
        
        if user_data.get('paid') == True:
            return jsonify({
                "status": "error",
                "message": "User is already activated. No payment needed."
            }), 409
        
        # Check for existing pending Pawapay deposit
        pending_deposit_ref = db.reference(f'pending_pawapay_deposits/{phone}')
        existing_deposit = pending_deposit_ref.get()
        
        if existing_deposit:
            # Check if deposit is still valid (less than 5 minutes old)
            created_at = datetime.fromisoformat(existing_deposit.get('createdAt'))
            if (datetime.now() - created_at).total_seconds() < 300:
                return jsonify({
                    "status": "error",
                    "message": "You already have a pending payment. Please complete it or wait 5 minutes.",
                    "depositId": existing_deposit.get('depositId')
                }), 409
        
        # Initiate Pawapay payment collection
        result = init_pawapay_payment(phone, amount, email, phone, "activation")
        
        if result['success']:
            # Store pending deposit info
            pending_deposit_ref.set({
                'depositId': result['depositId'],
                'phone': phone,
                'amount': amount,
                'email': email,
                'status': 'pending',
                'createdAt': datetime.now().isoformat(),
                'expiresAt': (datetime.now().timestamp() + 300)
            })
            
            return jsonify({
                "status": "success",
                "message": "Payment initiated. Please check your phone and complete payment.",
                "depositId": result['depositId'],
                "reference": result['depositId']
            }), 200
        else:
            return jsonify({
                "status": "error",
                "message": result['message']
            }), 400
            
    except Exception as e:
        print(f"🔥 Payment initiation error: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/check-payment-status/<phone>', methods=['GET'])
def check_payment_status(phone):
    """Check if user has paid and verify with Pawapay"""
    try:
        user_ref = db.reference(f'users/{phone}')
        user_data = user_ref.get()
        
        if not user_data:
            return jsonify({"status": "error", "message": "User not found"}), 404
        
        # If already marked as paid in our system
        if user_data.get('paid', False):
            return jsonify({
                "status": "success",
                "paid": True,
                "message": "User is activated"
            }), 200
        
        # Check for pending deposit and verify with Pawapay
        pending_ref = db.reference(f'pending_pawapay_deposits/{phone}')
        pending_deposit = pending_ref.get()
        
        if pending_deposit:
            deposit_id = pending_deposit.get('depositId')
            # Check status with Pawapay
            pawapay_status = check_pawapay_transaction_status(deposit_id, 'deposit')
            
            if pawapay_status and pawapay_status.get('status') == 'COMPLETED':
                # Update transaction status
                update_transaction_status(deposit_id, 'completed', {'verification': 'manual_check'})
                # Payment completed! Activate user
                return process_successful_payment(phone, deposit_id, pending_deposit.get('amount'))
        
        return jsonify({
            "status": "success",
            "paid": False,
            "message": "Payment not completed yet"
        }), 200
        
    except Exception as e:
        print(f"Check payment status error: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


# ==================== PAYOUT MANAGEMENT ====================

@app.route('/api/request-payout', methods=['POST'])
@limiter.limit("3 per minute")
def request_payout():
    """User requests to withdraw their earnings"""
    try:
        data = request.json
        phone = data.get('phone')
        amount = data.get('amount')
        
        if not phone or not amount:
            return jsonify({"status": "error", "message": "Missing payout data"}), 400
        
        user_ref = db.reference(f'users/{phone}')
        user_data = user_ref.get()
        
        if not user_data:
            return jsonify({"status": "error", "message": "User not found"}), 404
        
        # Check minimum withdrawal amount
        if amount < 1000:
            return jsonify({
                "status": "error",
                "message": "Minimum withdrawal amount is 1000 RWF"
            }), 400
        
        # Check if user has sufficient balance
        current_balance = user_data.get('balance', 0)
        if amount > current_balance:
            return jsonify({
                "status": "error",
                "message": f"Insufficient balance. You have {current_balance} RWF available."
            }), 400
        
        # Check for existing pending payout
        pending_payouts_ref = db.reference(f'pending_pawapay_payouts/{phone}')
        existing = pending_payouts_ref.get()
        if existing and existing.get('status') == 'pending':
            return jsonify({
                "status": "error",
                "message": "You already have a pending payout request. Please wait."
            }), 409
        
        # Initiate Pawapay payout
        result = init_pawapay_payout(phone, amount, phone, "TUMIRA Earnings Withdrawal")
        
        if result['success']:
            # Store pending payout
            pending_payouts_ref.set({
                'payoutId': result['payoutId'],
                'phone': phone,
                'amount': amount,
                'status': 'pending',
                'createdAt': datetime.now().isoformat(),
                'oldBalance': current_balance
            })
            
            # Temporarily hold the amount (mark as pending withdrawal)
            user_ref.update({
                'pendingWithdrawal': amount,
                'balance': current_balance - amount
            })
            
            return jsonify({
                "status": "success",
                "message": "Withdrawal request initiated. Money will be sent to your mobile money.",
                "payoutId": result['payoutId'],
                "amount": amount
            }), 200
        else:
            return jsonify({
                "status": "error",
                "message": result['message']
            }), 400
            
    except Exception as e:
        print(f"Payout request error: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/check-payout-status/<phone>', methods=['GET'])
def check_payout_status(phone):
    """Check status of pending payouts"""
    try:
        pending_ref = db.reference(f'pending_pawapay_payouts/{phone}')
        pending_payout = pending_ref.get()
        
        if not pending_payout:
            return jsonify({
                "status": "success",
                "hasPending": False,
                "message": "No pending payouts"
            }), 200
        
        payout_id = pending_payout.get('payoutId')
        pawapay_status = check_pawapay_transaction_status(payout_id, 'payout')
        
        if pawapay_status:
            status = pawapay_status.get('status')
            
            if status == 'COMPLETED':
                # Payout completed successfully
                update_transaction_status(payout_id, 'completed', {'completion': pawapay_status})
                pending_ref.delete()  # Remove pending record
                
                # Update user record
                user_ref = db.reference(f'users/{phone}')
                user_ref.update({
                    'pendingWithdrawal': None,
                    'lastPayoutDate': datetime.now().isoformat()
                })
                
                return jsonify({
                    "status": "success",
                    "completed": True,
                    "message": "Payout completed successfully",
                    "transactionDetails": pawapay_status
                }), 200
            elif status == 'FAILED':
                # Update transaction status
                update_transaction_status(payout_id, 'failed', {'failure_details': pawapay_status})
                
                # Payout failed, return money to balance
                user_ref = db.reference(f'users/{phone}')
                user_data = user_ref.get()
                
                # Restore balance
                new_balance = user_data.get('balance', 0) + pending_payout.get('amount', 0)
                user_ref.update({
                    'balance': new_balance,
                    'pendingWithdrawal': None
                })
                pending_ref.delete()
                
                return jsonify({
                    "status": "error",
                    "completed": False,
                    "message": "Payout failed. Funds have been returned to your balance.",
                    "error": pawapay_status
                }), 400
            else:
                return jsonify({
                    "status": "success",
                    "completed": False,
                    "payoutStatus": status,
                    "message": f"Payout is {status.lower()}"
                }), 200
        
        return jsonify({
            "status": "success",
            "completed": False,
            "message": "Checking payout status..."
        }), 200
        
    except Exception as e:
        print(f"Check payout status error: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/get-balance/<phone>', methods=['GET'])
def get_user_balance(phone):
    """Get user's current balance"""
    try:
        user_ref = db.reference(f'users/{phone}')
        user_data = user_ref.get()
        
        if not user_data:
            return jsonify({"status": "error", "message": "User not found"}), 404
        
        return jsonify({
            "status": "success",
            "balance": user_data.get('balance', 0),
            "totalEarned": user_data.get('totalEarned', 0),
            "pendingWithdrawal": user_data.get('pendingWithdrawal', 0)
        }), 200
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/transactions/<phone>', methods=['GET'])
def get_user_transactions(phone):
    """Get transaction history for a user"""
    try:
        transactions_ref = db.reference(f'transactions/{phone}')
        transactions = transactions_ref.get()
        
        if not transactions:
            return jsonify({
                "status": "success",
                "transactions": [],
                "count": 0
            }), 200
        
        # Convert to list and sort by timestamp
        transaction_list = []
        for txn_id, txn_data in transactions.items():
            transaction_list.append({
                'id': txn_id,
                'type': txn_data.get('type'),
                'amount': txn_data.get('amount'),
                'status': txn_data.get('status'),
                'timestamp': txn_data.get('timestamp'),
                'details': txn_data.get('details', {})
            })
        
        # Sort by timestamp descending (newest first)
        transaction_list.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        return jsonify({
            "status": "success",
            "transactions": transaction_list,
            "count": len(transaction_list)
        }), 200
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ==================== PAWAPAY WEBHOOK ====================

@app.route('/api/pawapay-webhook', methods=['POST'])
def pawapay_webhook():
    """Webhook endpoint for Pawapay to send payment/payout status updates"""
    try:
        data = request.json
        print(f"📨 Pawapay Webhook received: {json.dumps(data, indent=2)}")
        
        # Handle deposit webhook (payment collection)
        if 'depositId' in data:
            deposit_id = data.get('depositId')
            status = data.get('status')
            
            # Update transaction status
            update_transaction_status(deposit_id, status.lower(), {'webhook_data': data})
            
            # Find the pending deposit
            pending_ref = db.reference('pending_pawapay_deposits')
            all_pending = pending_ref.get()
            
            if all_pending:
                for phone, deposit in all_pending.items():
                    if deposit.get('depositId') == deposit_id:
                        if status == 'COMPLETED':
                            # Process successful payment
                            process_successful_payment(phone, deposit_id, deposit.get('amount'))
                        elif status == 'FAILED':
                            # Delete pending record
                            pending_ref.child(phone).delete()
                        break
        
        # Handle payout webhook
        elif 'payoutId' in data:
            payout_id = data.get('payoutId')
            status = data.get('status')
            
            # Update transaction status
            update_transaction_status(payout_id, status.lower(), {'webhook_data': data})
            
            # Find the pending payout
            pending_ref = db.reference('pending_pawapay_payouts')
            all_pending = pending_ref.get()
            
            if all_pending:
                for phone, payout in all_pending.items():
                    if payout.get('payoutId') == payout_id:
                        if status == 'COMPLETED':
                            # Payout completed
                            user_ref = db.reference(f'users/{phone}')
                            user_ref.update({
                                'pendingWithdrawal': None,
                                'lastPayoutDate': datetime.now().isoformat()
                            })
                            pending_ref.child(phone).delete()
                        elif status == 'FAILED':
                            # Payout failed, return money
                            user_ref = db.reference(f'users/{phone}')
                            user_data = user_ref.get()
                            new_balance = user_data.get('balance', 0) + payout.get('amount', 0)
                            user_ref.update({
                                'balance': new_balance,
                                'pendingWithdrawal': None
                            })
                            pending_ref.child(phone).delete()
                        break
        
        return jsonify({"status": "success"}), 200
        
    except Exception as e:
        print(f"Webhook processing error: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


def process_successful_payment(phone, transaction_id, amount):
    """Process successful payment and credit referrals"""
    try:
        user_ref = db.reference(f'users/{phone}')
        user_data = user_ref.get()
        
        if not user_data:
            return jsonify({"status": "error", "message": "User not found"}), 404
        
        if user_data.get('paid') == True:
            return jsonify({"status": "success", "message": "User already paid"}), 200
        
        # Update user as paid
        user_ref.update({
            'paid': True,
            'paidAt': datetime.now().isoformat(),
            'paidAmount': amount,
            'transactionId': transaction_id
        })
        
        # Clear pending deposit
        pending_ref = db.reference(f'pending_pawapay_deposits/{phone}')
        pending_ref.delete()
        
        # Process referral credit if user was referred by someone
        referred_by = user_data.get('referredBy')
        if referred_by and user_data.get('pendingReferralCredit'):
            referrer_ref = db.reference(f'users/{referred_by}')
            referrer_data = referrer_ref.get()
            
            if referrer_data and referrer_data.get('paid') == True:
                commission = REFERRAL_COMMISSION  # Now 2000 RWF, matching activation fee
                
                # Add to referrer's referrals list
                referrals = referrer_data.get('referrals', [])
                referrals.append({
                    'phone': phone,
                    'amount': commission,
                    'date': datetime.now().strftime("%Y-%m-%d"),
                    'status': 'completed',
                    'transactionId': transaction_id
                })
                
                # Update referrer's total earned AND balance (for withdrawals)
                total_earned = referrer_data.get('totalEarned', 0) + commission
                current_balance = referrer_data.get('balance', 0) + commission
                
                referrer_ref.update({
                    'referrals': referrals,
                    'totalEarned': total_earned,
                    'balance': current_balance  # Add to balance for withdrawal
                })
                
                # Log referral commission as a transaction
                log_transaction(
                    'deposit',  # Commission is like a deposit to referrer
                    referred_by,
                    commission,
                    f"REFERRAL_{transaction_id}",
                    'completed',
                    {'referral_phone': phone, 'type': 'referral_commission'}
                )
                
                # Clear pending flag
                user_ref.update({'pendingReferralCredit': False})
        
        return jsonify({
            "status": "success",
            "message": "Payment confirmed successfully",
            "paid": True
        }), 200
        
    except Exception as e:
        print("Process payment error:", str(e))
        return jsonify({"status": "error", "message": str(e)}), 500


# ==================== STATISTICS & DEBUG ====================

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get platform statistics"""
    try:
        users_ref = db.reference('users')
        all_users = users_ref.get()
        
        total_users = 0
        paid_users = 0
        total_referrals = 0
        total_commission_paid = 0
        total_balance = 0
        
        if all_users:
            total_users = len(all_users)
            for user_data in all_users.values():
                if user_data.get('paid'):
                    paid_users += 1
                referrals = user_data.get('referrals', [])
                total_referrals += len(referrals)
                total_commission_paid += user_data.get('totalEarned', 0)
                total_balance += user_data.get('balance', 0)
        
        return jsonify({
            "status": "success",
            "stats": {
                "totalUsers": total_users,
                "paidUsers": paid_users,
                "totalReferrals": total_referrals,
                "totalCommissionPaid": total_commission_paid,
                "totalPendingBalance": total_balance
            }
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/debug/users', methods=['GET'])
def debug_users():
    """Debug endpoint to see all users"""
    try:
        users_ref = db.reference('users')
        all_users = users_ref.get()
        
        if all_users:
            users_list = []
            for phone, user_data in all_users.items():
                users_list.append({
                    'phone': phone,
                    'email': user_data.get('email'),
                    'paid': user_data.get('paid'),
                    'referralId': user_data.get('referralId'),
                    'totalEarned': user_data.get('totalEarned'),
                    'balance': user_data.get('balance', 0)
                })
            return jsonify({
                "status": "success",
                "users": users_list,
                "count": len(users_list)
            }), 200
        else:
            return jsonify({"status": "success", "users": [], "count": 0}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/debug/pending-payments', methods=['GET'])
def debug_pending():
    """Debug endpoint to see pending Pawapay deposits"""
    try:
        pending_ref = db.reference('pending_pawapay_deposits')
        all_pending = pending_ref.get()
        
        if all_pending:
            pending_list = []
            for phone, payment in all_pending.items():
                pending_list.append({
                    'phone': phone,
                    'depositId': payment.get('depositId'),
                    'amount': payment.get('amount'),
                    'status': payment.get('status'),
                    'createdAt': payment.get('createdAt')
                })
            return jsonify({
                "status": "success",
                "pending": pending_list,
                "count": len(pending_list)
            }), 200
        else:
            return jsonify({"status": "success", "pending": [], "count": 0}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/debug/pending-payouts', methods=['GET'])
def debug_pending_payouts():
    """Debug endpoint to see pending payouts"""
    try:
        pending_ref = db.reference('pending_pawapay_payouts')
        all_pending = pending_ref.get()
        
        if all_pending:
            pending_list = []
            for phone, payout in all_pending.items():
                pending_list.append({
                    'phone': phone,
                    'payoutId': payout.get('payoutId'),
                    'amount': payout.get('amount'),
                    'status': payout.get('status'),
                    'createdAt': payout.get('createdAt')
                })
            return jsonify({
                "status": "success",
                "pending": pending_list,
                "count": len(pending_list)
            }), 200
        else:
            return jsonify({"status": "success", "pending": [], "count": 0}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == '__main__':
    # Get debug setting from environment variable (default to False for production)
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    port = int(os.environ.get('PORT', 5000))
    
    app.run(
        debug=debug_mode,
        host='0.0.0.0' if not debug_mode else '127.0.0.1',
        port=port
    )
