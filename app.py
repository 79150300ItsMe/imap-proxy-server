from flask import Flask, request, jsonify
import imaplib
import email
import re
from datetime import datetime
import json

app = Flask(__name__)

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
                "emails_checked": 0,
                "timestamp": datetime.now().isoformat(),
                "success": False
            }
            
            # Check last 15 emails
            for email_id in email_ids[-15:]:
                status, msg_data = self.connection.fetch(email_id, '(RFC822)')
                
                if status == "OK":
                    email_body = msg_data[0][1]
                    email_message = email.message_from_bytes(email_body)
                    
                    # Get email content
                    body = ""
                    if email_message.is_multipart():
                        for part in email_message.walk():
                            if part.get_content_type() == "text/plain":
                                body += part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    else:
                        body = email_message.get_payload(decode=True).decode('utf-8', errors='ignore')
                    
                    results["emails_checked"] += 1
                    
                    # Extract codes
                    if not results["verification_code"]:
                        results["verification_code"] = self.extract_verification_code(body)
                    
                    if not results["security_code"]:
                        results["security_code"] = self.extract_security_code(body)
                        
                    if not results["confirmation_code"]:
                        results["confirmation_code"] = self.extract_confirmation_code(body)
            
            # Set success flag if any codes found
            if results["verification_code"] or results["security_code"] or results["confirmation_code"]:
                results["success"] = True
            
            return results
            
        except Exception as e:
            return {"error": f"Search failed: {str(e)}"}
    
    def extract_verification_code(self, text):
        patterns = [
            r'verification code[:\s]*(\d{5})',
            r'kode verifikasi[:\s]*(\d{5})',
            r'(\d{5})\s*adalah\s*kode\s*verifikasi',
            r'your\s*facebook\s*code[:\s]*(\d{5})',
            r'code[:\s]*(\d{5})(?!\d)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match and len(match.group(1)) == 5:
                return match.group(1)
        return None
    
    def extract_security_code(self, text):
        # Skip if email confirmation context
        if re.search(r'mengonfirmasi\s+email|konfirmasi\s+email|confirm\s+email', text, re.IGNORECASE):
            return None
            
        patterns = [
            r'security code[:\s]*(\d{6})',
            r'kode keamanan[:\s]*(\d{6})',
            r'login code[:\s]*(\d{6})',
            r'(\d{6})\s*adalah\s*kode\s*keamanan'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match and len(match.group(1)) == 6:
                return match.group(1)
        return None
        
    def extract_confirmation_code(self, text):
        patterns = [
            r'(\d{6})\s*adalah\s*kode.*mengonfirmasi\s*email',
            r'kode\s*konfirmasi.*(\d{6})',
            r'email\s*confirmation.*(\d{6})',
            r'(\d{6})\s*untuk\s*mengonfirmasi\s*alamat\s*email',
            r'satu\s*langkah\s*lagi.*mengonfirmasi.*(\d{6})'
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
            "timestamp": datetime.now().isoformat()
        })
    else:
        return jsonify({
            "status": "failed", 
            "message": "IMAP connection failed"
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
        "service": "IMAP Proxy Server",
        "status": "running",
        "endpoints": [
            "/api/test-connection",
            "/api/get-codes"
        ]
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)