from flask import Flask, request, jsonify
from flask_cors import CORS
import imaplib
import email
import re
from datetime import datetime
import json

app = Flask(__name__)
CORS(app)  # Enable CORS untuk semua routes

class IMAPClient:
    def __init__(self):
        self.connection = None
        
    def connect(self, server, port, email_addr, password):
        try:
            self.connection = imaplib.IMAP4_SSL(server, port, timeout=30)
            result = self.connection.login(email_addr, password)
            return result[0] == 'OK'
        except Exception as e:
            print(f"Connection error: {e}")
            return False
    
    def search_codes(self, target_email, timeout_minutes=5):
        if not self.connection:
            return {"error": "Not connected"}
            
        try:
            self.connection.select('inbox')
            status, messages = self.connection.search(None, 'ALL')
            
            if status != "OK":
                return {"error": "Search failed"}
                
            email_ids = messages[0].split()
            results = {
                "verification_code": None,
                "security_code": None, 
                "confirmation_code": None,
                "instagram_code": None,
                "emails_checked": 0,
                "timestamp": datetime.now().isoformat(),
                "success": False
            }
            
            # Check last 20 emails (lebih banyak untuk Instagram)
            for email_id in email_ids[-20:]:
                status, msg_data = self.connection.fetch(email_id, '(RFC822)')
                
                if status == "OK":
                    email_body = msg_data[0][1]
                    email_message = email.message_from_bytes(email_body)
                    
                    # Get sender info
                    sender = email_message.get('From', '').lower()
                    subject = email_message.get('Subject', '').lower()
                    
                    # Get email content
                    body = ""
                    if email_message.is_multipart():
                        for part in email_message.walk():
                            if part.get_content_type() == "text/plain":
                                body += part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    else:
                        body = email_message.get_payload(decode=True).decode('utf-8', errors='ignore')
                    
                    results["emails_checked"] += 1
                    
                    # Extract codes berdasarkan prioritas
                    if not results["instagram_code"]:
                        results["instagram_code"] = self.extract_instagram_code(body, sender, subject)
                    
                    if not results["verification_code"]:
                        results["verification_code"] = self.extract_verification_code(body, sender, subject)
                    
                    if not results["security_code"]:
                        results["security_code"] = self.extract_security_code(body, sender, subject)
                        
                    if not results["confirmation_code"]:
                        results["confirmation_code"] = self.extract_confirmation_code(body, sender, subject)
            
            # Set success flag if any codes found
            if (results["verification_code"] or results["security_code"] or 
                results["confirmation_code"] or results["instagram_code"]):
                results["success"] = True
            
            return results
            
        except Exception as e:
            return {"error": f"Search failed: {str(e)}"}
    
    def extract_instagram_code(self, text, sender="", subject=""):
        """Extract Instagram specific codes"""
        # Check if it's from Instagram
        instagram_senders = ['instagram', 'ig.me', 'facebookmail', 'meta']
        is_instagram = any(ig_sender in sender for ig_sender in instagram_senders)
        
        instagram_subjects = ['instagram', 'confirm', 'verification', 'kode', 'code']
        is_instagram_subject = any(ig_subject in subject for ig_subject in instagram_subjects)
        
        if not (is_instagram or is_instagram_subject):
            return None
        
        # Instagram specific patterns
        patterns = [
            # Instagram Indonesia
            r'(\d{6})\s*adalah\s*kode\s*konfirmasi\s*instagram',
            r'kode\s*konfirmasi\s*instagram.*?(\d{6})',
            r'gunakan\s*kode\s*ini.*?(\d{6})',
            r'(\d{6})\s*untuk\s*mengonfirmasi\s*akun',
            
            # Instagram English
            r'(\d{6})\s*is\s*your\s*instagram\s*code',
            r'instagram\s*confirmation\s*code.*?(\d{6})',
            r'use\s*this\s*code.*?(\d{6})',
            r'(\d{6})\s*to\s*confirm\s*your\s*account',
            
            # Generic Instagram patterns
            r'confirm\s*your\s*email.*?(\d{6})',
            r'(\d{6})\s*.*?instagram',
            r'verification\s*code.*?(\d{6})',
            
            # Meta/Facebook related
            r'(\d{6})\s*.*?meta',
            r'facebook.*?(\d{6})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match and len(match.group(1)) == 6:
                return match.group(1)
        return None
    
    def extract_verification_code(self, text, sender="", subject=""):
        """Extract general verification codes"""
        patterns = [
            # 5 digit codes
            r'verification\s*code[:\s]*(\d{5})',
            r'kode\s*verifikasi[:\s]*(\d{5})',
            r'(\d{5})\s*adalah\s*kode\s*verifikasi',
            r'your.*?code[:\s]*(\d{5})',
            r'code[:\s]*(\d{5})(?!\d)',
            
            # 6 digit codes for verification
            r'verification\s*code[:\s]*(\d{6})',
            r'kode\s*verifikasi[:\s]*(\d{6})',
            r'(\d{6})\s*adalah\s*kode\s*verifikasi',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                code = match.group(1)
                if len(code) in [5, 6]:
                    return code
        return None
    
    def extract_security_code(self, text, sender="", subject=""):
        """Extract security codes (avoid email confirmation context)"""
        # Skip if email confirmation context
        if re.search(r'mengonfirmasi\s+email|konfirmasi\s+email|confirm\s+email|email\s*confirmation', 
                    text, re.IGNORECASE):
            return None
            
        patterns = [
            r'security\s*code[:\s]*(\d{6})',
            r'kode\s*keamanan[:\s]*(\d{6})',
            r'login\s*code[:\s]*(\d{6})',
            r'(\d{6})\s*adalah\s*kode\s*keamanan',
            r'(\d{6})\s*.*?login',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match and len(match.group(1)) == 6:
                return match.group(1)
        return None
        
    def extract_confirmation_code(self, text, sender="", subject=""):
        """Extract email confirmation codes"""
        patterns = [
            # Email confirmation specific
            r'(\d{6})\s*adalah\s*kode.*mengonfirmasi\s*email',
            r'kode\s*konfirmasi\s*email.*?(\d{6})',
            r'email\s*confirmation.*?(\d{6})',
            r'(\d{6})\s*untuk\s*mengonfirmasi\s*alamat\s*email',
            r'confirm\s*your\s*email.*?(\d{6})',
            
            # General confirmation
            r'kode\s*konfirmasi.*?(\d{6})',
            r'confirmation\s*code.*?(\d{6})',
            r'(\d{6})\s*.*?konfirmasi',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match and len(match.group(1)) == 6:
                return match.group(1)
        return None

@app.route('/api/test-connection', methods=['POST'])
def test_connection():
    data = request.json
    
    client = IMAPClient()
    success = client.connect(
        data.get('imap_server'),
        int(data.get('imap_port', 993)),
        data.get('login_email'),
        data.get('login_password')
    )
    
    if success:
        client.connection.close()
        return jsonify({
            "status": "success",
            "message": "IMAP connection successful",
            "timestamp": datetime.now().isoformat(),
            "version": "3.2"
        })
    else:
        return jsonify({
            "status": "failed", 
            "message": "IMAP connection failed",
            "version": "3.2"
        }), 400

@app.route('/api/get-codes', methods=['POST'])
def get_codes():
    data = request.json
    
    client = IMAPClient()
    success = client.connect(
        data.get('imap_server'),
        int(data.get('imap_port', 993)),
        data.get('login_email'),
        data.get('login_password')
    )
    
    if not success:
        return jsonify({"error": "Connection failed"}), 400
    
    results = client.search_codes(
        data.get('target_email'),
        data.get('timeout_minutes', 5)
    )
    
    client.connection.close()
    return jsonify(results)

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "service": "IMAP Proxy Server Instagram",
        "status": "running",
        "version": "3.2",
        "features": ["Instagram codes", "Multi-provider support"],
        "endpoints": [
            "/api/test-connection",
            "/api/get-codes"
        ]
    })

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "3.2"
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
