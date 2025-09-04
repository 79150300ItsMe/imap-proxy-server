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
            
            # Check last 20 emails (increased from 15)
            for email_id in email_ids[-20:]:
                status, msg_data = self.connection.fetch(email_id, '(RFC822)')
                
                if status == "OK":
                    email_body = msg_data[0][1]
                    email_message = email.message_from_bytes(email_body)
                    
                    # Get sender for debugging
                    sender = email_message.get('From', 'Unknown')
                    subject = email_message.get('Subject', 'No Subject')
                    print(f"Checking email from: {sender}, Subject: {subject}")
                    
                    # Get email content
                    body = ""
                    if email_message.is_multipart():
                        for part in email_message.walk():
                            if part.get_content_type() in ["text/plain", "text/html"]:
                                try:
                                    payload = part.get_payload(decode=True)
                                    if payload:
                                        body += payload.decode('utf-8', errors='ignore') + "\n"
                                except:
                                    continue
                    else:
                        try:
                            payload = email_message.get_payload(decode=True)
                            if payload:
                                body = payload.decode('utf-8', errors='ignore')
                        except:
                            body = str(email_message.get_payload())
                    
                    if body:
                        print(f"Email body preview: {body[:200]}...")
                        results["emails_checked"] += 1
                        
                        # Extract codes with platform-specific methods
                        if not results["verification_code"]:
                            results["verification_code"] = self.extract_verification_code(body, sender)
                        
                        if not results["security_code"]:
                            results["security_code"] = self.extract_security_code(body, sender)
                            
                        if not results["confirmation_code"]:
                            results["confirmation_code"] = self.extract_confirmation_code(body, sender)
            
            # Set success flag if any codes found
            if results["verification_code"] or results["security_code"] or results["confirmation_code"]:
                results["success"] = True
            
            return results
            
        except Exception as e:
            return {"error": f"Search failed: {str(e)}"}
    
    def extract_verification_code(self, text, sender=""):
        """Extract 5-digit verification codes - Facebook, Instagram, etc."""
        print(f"Searching for 5-digit verification code in text from {sender}")
        
        # Platform-specific patterns
        patterns = []
        
        # INSTAGRAM PATTERNS (5-digit)
        if 'instagram' in sender.lower() or 'instagram' in text.lower():
            patterns.extend([
                r'(\d{5})\s*adalah\s*kode\s*Instagram\s*Anda',  # Instagram Indonesia
                r'(\d{5})\s*is\s*your\s*Instagram\s*code',      # Instagram English
                r'kode\s*Instagram.*?(\d{5})',                   # "kode Instagram Anda: 12345"
                r'Instagram.*?kode.*?(\d{5})',                   # "Instagram kode verifikasi: 12345"
                r'(\d{5})\s*untuk\s*Instagram',                  # "12345 untuk Instagram"
            ])
        
        # FACEBOOK PATTERNS (5-digit)
        if 'facebook' in sender.lower() or 'facebook' in text.lower():
            patterns.extend([
                r'verification\s*code[:\s]*(\d{5})',
                r'kode\s*verifikasi[:\s]*(\d{5})',
                r'(\d{5})\s*adalah\s*kode\s*verifikasi.*Facebook',
                r'Facebook.*verification.*(\d{5})',
            ])
        
        # GENERIC PATTERNS (fallback)
        patterns.extend([
            r'verification\s*code[:\s]*(\d{5})',           # Generic verification
            r'kode\s*verifikasi[:\s]*(\d{5})',            # Indonesian verification
            r'confirmation\s*code[:\s]*(\d{5})',          # Generic confirmation 
            r'kode\s*konfirmasi[:\s]*(\d{5})',            # Indonesian confirmation
            r'(\d{5})\s*adalah\s*kode\s*verifikasi',      # "12345 adalah kode verifikasi"
            r'(\d{5})\s*adalah\s*kode\s*konfirmasi',      # "12345 adalah kode konfirmasi"
            r'your\s*code[:\s]*(\d{5})',                  # "your code: 12345"
            r'kode\s*Anda[:\s]*(\d{5})',                  # "kode Anda: 12345"
            r'code[:\s]*(\d{5})(?!\d)',                   # Generic 5-digit code
            r'(?<!\d)(\d{5})(?!\d)',                      # Standalone 5-digit
        ])
        
        for i, pattern in enumerate(patterns):
            print(f"Trying verification pattern {i+1}: {pattern}")
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                code = match.group(1)
                print(f"Verification pattern {i+1} matched! Found code: {code}")
                if len(code) == 5 and code.isdigit():
                    return code
        
        print("No 5-digit verification code found")
        return None
    
    def extract_security_code(self, text, sender=""):
        """Extract 6-digit security codes - Facebook, Instagram login codes"""
        print(f"Searching for 6-digit security code in text from {sender}")
        
        # Skip if email confirmation context
        email_confirmation_indicators = [
            'mengonfirmasi email',
            'konfirmasi email', 
            'confirm email',
            'email confirmation',
            'email verification',
            'mengonfirmasi alamat email'
        ]
        
        text_lower = text.lower()
        for indicator in email_confirmation_indicators:
            if indicator in text_lower and 'bukan untuk' not in text_lower:
                print(f"Text contains email confirmation indicator: '{indicator}' - skipping security code")
                return None
        
        patterns = []
        
        # INSTAGRAM SECURITY PATTERNS (6-digit)
        if 'instagram' in sender.lower() or 'instagram' in text.lower():
            patterns.extend([
                r'(\d{6})\s*adalah\s*kode\s*keamanan\s*Instagram',
                r'Instagram\s*security\s*code[:\s]*(\d{6})',
                r'(\d{6})\s*untuk\s*login\s*Instagram',
                r'Instagram\s*login.*?(\d{6})',
            ])
        
        # FACEBOOK SECURITY PATTERNS (6-digit)
        if 'facebook' in sender.lower() or 'facebook' in text.lower():
            patterns.extend([
                r'security\s*code[:\s]*(\d{6})',
                r'(\d{6})\s*adalah\s*kode\s*keamanan.*Facebook',
                r'Facebook\s*security.*(\d{6})',
            ])
        
        # GENERIC SECURITY PATTERNS
        patterns.extend([
            r'security\s*code[:\s]*(\d{6})',               # Generic security
            r'kode\s*keamanan[:\s]*(\d{6})',              # Indonesian security
            r'login\s*code[:\s]*(\d{6})',                 # Login code
            r'kode\s*login[:\s]*(\d{6})',                 # Indonesian login
            r'access\s*code[:\s]*(\d{6})',                # Access code
            r'kode\s*akses[:\s]*(\d{6})',                 # Indonesian access
            r'(\d{6})\s*adalah\s*kode\s*keamanan',        # "123456 adalah kode keamanan"
            r'(\d{6})\s*adalah\s*kode\s*login',           # "123456 adalah kode login"
        ])
        
        for i, pattern in enumerate(patterns):
            print(f"Trying security pattern {i+1}: {pattern}")
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                code = match.group(1)
                print(f"Security pattern {i+1} matched! Found code: {code}")
                if len(code) == 6 and code.isdigit():
                    return code
        
        print("No 6-digit security code found")
        return None
        
    def extract_confirmation_code(self, text, sender=""):
        """Extract 6-digit email confirmation codes - Instagram, Facebook email confirmation"""
        print(f"Searching for 6-digit confirmation code in text from {sender}")
        
        patterns = []
        
        # INSTAGRAM EMAIL CONFIRMATION PATTERNS (6-digit)
        if 'instagram' in sender.lower() or 'instagram' in text.lower():
            patterns.extend([
                r'(\d{6})\s*adalah\s*kode\s*Instagram\s*Anda',                    # Instagram Indonesia
                r'(\d{6})\s*is\s*your\s*Instagram\s*code',                        # Instagram English
                r'(\d{6})\s*untuk\s*mengonfirmasi.*Instagram',                    # "123456 untuk mengonfirmasi Instagram"
                r'Instagram.*konfirmasi.*(\d{6})',                                # "Instagram konfirmasi: 123456"
                r'(\d{6})\s*untuk\s*memverifikasi.*Instagram',                    # Verification
                r'Instagram.*verification.*(\d{6})',                              # Instagram verification
                r'(\d{6})\s*adalah\s*kode\s*verifikasi.*Instagram',              # "123456 adalah kode verifikasi Instagram"
            ])
        
        # FACEBOOK EMAIL CONFIRMATION PATTERNS (6-digit)
        if 'facebook' in sender.lower() or 'facebook' in text.lower():
            patterns.extend([
                r'(\d{6})\s*adalah\s*kode.*mengonfirmasi.*email.*Facebook',       # Facebook email confirmation
                r'Facebook.*email.*confirmation.*(\d{6})',                        # Facebook email confirmation
                r'(\d{6})\s*untuk\s*mengonfirmasi.*Facebook',                     # "123456 untuk mengonfirmasi Facebook"
            ])
        
        # EMAIL CONFIRMATION PATTERNS (HIGHEST PRIORITY - Most specific)
        patterns.extend([
            r'(\d{6})\s*adalah\s*kode\s*[Aa]nda\s*untuk\s*mengonfirmasi\s*email\s*ini',     # "790433 adalah kode Anda untuk mengonfirmasi email ini"
            r'(\d{6})\s*adalah\s*kode\s*[Aa]nda\s*untuk\s*mengonfirmasi\s*alamat\s*email', # "790433 adalah kode Anda untuk mengonfirmasi alamat email"
            r'(\d{6})\s*untuk\s*mengonfirmasi\s*alamat\s*email',                # "615792 untuk mengonfirmasi alamat email"
            r'(\d{6})\s*satu\s*langkah\s*lagi.*?mengonfirmasi.*?email',         # "615792 satu langkah lagi untuk mengonfirmasi alamat email ini"
            r'(\d{6})\s*[,.]?\s*satu\s*langkah\s*lagi.*?mengonfirmasi.*?email', # With punctuation
            r'satu\s*langkah\s*lagi.*?mengonfirmasi.*?alamat\s*email.*?(\d{6})', # Reverse order
            
            # Indonesian patterns
            r'kode\s*konfirmasi\s*[Aa]nda.*?(\d{6})',                           # "kode konfirmasi Anda: 123456"
            r'masukkan\s*kode\s*konfirmasi.*?(\d{6})',                          # "Masukkan kode konfirmasi: 123456"
            r'(\d{6})\s*adalah\s*kode.*?mengonfirmasi.*?email',                 # Flexible email confirmation
            
            # English patterns
            r'(\d{6})\s*is\s*your\s*code\s*to\s*confirm\s*email',              # English version
            r'email\s*confirmation\s*code.*?(\d{6})',                           # "email confirmation code: 615792"
            r'confirm\s*your\s*email.*?(\d{6})',                                # "confirm your email with 615792"
            r'your\s*email\s*confirmation\s*code\s*is\s*(\d{6})',              # "Your email confirmation code is 615792"
            
            # More flexible patterns
            r'mengonfirmasi\s*email.*?(\d{6})',                                 # "mengonfirmasi email ini: 615792"
            r'konfirmasi\s*alamat\s*email.*?(\d{6})',                          # "konfirmasi alamat email: 615792"
            r'(\d{6})\s*[,.]?\s*untuk\s*mengonfirmasi',                        # "615792, untuk mengonfirmasi"
        ])
        
        for i, pattern in enumerate(patterns):
            print(f"Trying confirmation pattern {i+1}: {pattern}")
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                code = match.group(1)
                print(f"Confirmation pattern {i+1} matched! Found code: {code}")
                if len(code) == 6 and code.isdigit():
                    return code
        
        print("No 6-digit confirmation code found")
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
        "service": "IMAP Proxy Server with Instagram Support",
        "status": "running",
        "version": "2.0", 
        "endpoints": [
            "/api/test-connection",
            "/api/get-codes"
        ],
        "supported_platforms": [
            "Instagram", "Facebook", "Generic Email Confirmation"
        ]
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
