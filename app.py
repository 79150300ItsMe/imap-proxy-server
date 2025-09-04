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
            print(f"Connecting to {server}:{port} with {email_addr}")
            self.connection = imaplib.IMAP4_SSL(server, port, timeout=30)
            result = self.connection.login(email_addr, password)
            print(f"Login result: {result}")
            return result[0] == 'OK'
        except Exception as e:
            print(f"Connection error: {e}")
            return False
    
    def search_codes(self, target_email, timeout_minutes=5):
        if not self.connection:
            return {"error": "Not connected"}
            
        try:
            # Select inbox
            result = self.connection.select('inbox')
            print(f"Inbox selection: {result}")
            
            # Multiple search strategies for better compatibility (from original get_code.py)
            search_queries = [
                f'TO "{target_email}"',
                f'FROM "facebook"',
                f'FROM "facebookmail.com"', 
                f'FROM "instagram"',
                f'FROM "instagrammail.com"',
                f'FROM "notification+*@facebookmail.com"',
                'ALL'  # Fallback to all emails
            ]
            
            results = {
                "verification_code": None,
                "security_code": None, 
                "confirmation_code": None,
                "emails_checked": 0,
                "timestamp": datetime.now().isoformat(),
                "success": False
            }
            
            for query in search_queries:
                print(f"Searching with: {query}")
                status, messages = self.connection.search(None, query)
                
                if status == "OK" and messages[0]:
                    email_ids = messages[0].split()
                    print(f"Found {len(email_ids)} emails with query: {query}")
                    
                    # Check latest emails (more emails for better chance)
                    for email_id in email_ids[-10:]:  # Check last 10 emails
                        try:
                            status, msg_data = self.connection.fetch(email_id, '(RFC822)')
                            
                            if status == "OK" and msg_data:
                                email_body = msg_data[0][1]
                                email_message = email.message_from_bytes(email_body)
                                
                                # Get sender info for debugging
                                sender = email_message.get('From', 'Unknown')
                                subject = email_message.get('Subject', 'No Subject')
                                print(f"Checking email from: {sender}, Subject: {subject}")
                                
                                # Get email content with better handling (EXACT from get_code.py)
                                body_text = ""
                                if email_message.is_multipart():
                                    for part in email_message.walk():
                                        if part.get_content_type() in ["text/plain", "text/html"]:
                                            try:
                                                payload = part.get_payload(decode=True)
                                                if payload:
                                                    body_text += payload.decode('utf-8', errors='ignore') + "\n"
                                            except:
                                                continue
                                else:
                                    try:
                                        payload = email_message.get_payload(decode=True)
                                        if payload:
                                            body_text = payload.decode('utf-8', errors='ignore')
                                    except:
                                        body_text = str(email_message.get_payload())
                                
                                if body_text:
                                    print(f"Email body preview: {body_text[:200]}...")
                                    results["emails_checked"] += 1
                                    
                                    # Extract codes using EXACT original patterns
                                    if not results["verification_code"]:
                                        results["verification_code"] = self.extract_verification_code(body_text)
                                        if results["verification_code"]:
                                            print(f"Found verification code: {results['verification_code']}")
                                    
                                    if not results["security_code"]:
                                        results["security_code"] = self.extract_security_code(body_text)
                                        if results["security_code"]:
                                            print(f"Found security code: {results['security_code']}")
                                            
                                    if not results["confirmation_code"]:
                                        results["confirmation_code"] = self.extract_email_confirmation_code(body_text)
                                        if results["confirmation_code"]:
                                            print(f"Found confirmation code: {results['confirmation_code']}")
                        
                        except Exception as email_error:
                            print(f"Error processing email {email_id}: {email_error}")
                            continue
                    
                    # If we found emails but no code, break to avoid redundant searches
                    if email_ids:
                        break
            
            # Set success flag if any codes found
            if results["verification_code"] or results["security_code"] or results["confirmation_code"]:
                results["success"] = True
            
            print(f"Final results: {results}")
            return results
            
        except Exception as e:
            print(f"Search failed: {str(e)}")
            return {"error": f"Search failed: {str(e)}"}
    
    def extract_verification_code(self, text):
        """Extract verification code - EXACT from original get_code.py"""
        print(f"Searching for 5-digit verification code in text: {text[:200]}...")
        
        # EXACT Facebook verification patterns from original (ONLY 5-digit codes)
        patterns = [
            r'verification code[:\s]*(\d{5})',           # Facebook 5-digit verification
            r'kode verifikasi[:\s]*(\d{5})',            # Indonesian verification
            r'confirmation code[:\s]*(\d{5})',          # Facebook 5-digit confirmation
            r'kode konfirmasi[:\s]*(\d{5})',            # Indonesian confirmation
            r'(\d{5})\s*adalah\s*kode\s*verifikasi',    # "12345 adalah kode verifikasi"
            r'(\d{5})\s*adalah\s*kode\s*konfirmasi',    # "12345 adalah kode konfirmasi"
            r'code[:\s]*(\d{5})(?!\d)',                 # Generic 5-digit code (no more digits after)
            r'(?<!\d)(\d{5})(?!\d)',                    # Standalone 5-digit number
            
            # INSTAGRAM specific patterns (5-digit)
            r'(\d{5})\s*adalah\s*kode\s*Instagram\s*Anda',  # Instagram Indonesia
            r'(\d{5})\s*is\s*your\s*Instagram\s*code',      # Instagram English
            r'kode\s*Instagram.*?(\d{5})',                   # "kode Instagram Anda: 12345"
            r'Instagram.*?kode.*?(\d{5})',                   # "Instagram kode verifikasi: 12345"
            r'(\d{5})\s*untuk\s*Instagram',                  # "12345 untuk Instagram"
        ]
        
        for i, pattern in enumerate(patterns):
            print(f"Trying verification pattern {i+1}: {pattern}")
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                code = match.group(1)
                print(f"Verification pattern {i+1} matched! Found code: {code}")
                # ONLY accept 5-digit codes for verification
                if len(code) == 5 and code.isdigit():
                    return code
                else:
                    print(f"Code {code} is not 5 digits, skipping...")
        
        print("No 5-digit verification code found")
        return None
    
    def extract_security_code(self, text):
        """Extract security code - EXACT from original get_code.py"""
        print(f"Searching for 6-digit security code in text: {text[:200]}...")
        
        # EXCLUDE email confirmation patterns first - EXACT from original
        email_confirmation_indicators = [
            'mengonfirmasi email',
            'konfirmasi email', 
            'confirm email',
            'email confirmation',
            'email verification',
            'mengonfirmasi alamat email'  # More specific - only exclude if it's about confirming email address
        ]
        
        # Check if this is specifically an email confirmation context (should be excluded)
        text_lower = text.lower()
        for indicator in email_confirmation_indicators:
            if indicator in text_lower:
                # Additional check: if it contains "bukan untuk" (not for) then it's OK for security
                if 'bukan untuk' not in text_lower:
                    print(f"Text contains email confirmation indicator: '{indicator}' - skipping for security code")
                    return None
        
        # Security code patterns (ONLY 6-digit codes, NOT in email confirmation context) - EXACT from original
        patterns = [
            r'security code[:\s]*(\d{6})',               # 6-digit security code
            r'kode keamanan[:\s]*(\d{6})',              # Indonesian security code
            r'login code[:\s]*(\d{6})',                 # 6-digit login code
            r'kode login[:\s]*(\d{6})',                 # Indonesian login code
            r'access code[:\s]*(\d{6})',                # 6-digit access code
            r'kode akses[:\s]*(\d{6})',                 # Indonesian access code
            r'kode\s+akses\s+[Aa]nda[:\s]*(\d{6})',     # "kode akses Anda: 334496"
            r'защитный код[:\s]*(\d{6})',               # Russian: security code
            r'код доступа[:\s]*(\d{6})',                # Russian: access code
            r'код безопасности[:\s]*(\d{6})',           # Russian: security code
            r'(\d{6})\s*adalah\s*kode\s*keamanan',      # "123456 adalah kode keamanan"
            r'(\d{6})\s*adalah\s*kode\s*login',         # "123456 adalah kode login"
            r'(\d{6})\s*adalah\s*kode\s*akses',         # "123456 adalah kode akses"
            r'kode\s*keamanan.*?(\d{6})',               # "kode keamanan Anda: 123456"
            r'kode\s*login.*?(\d{6})',                  # "kode login: 123456"
            r'security.*?(\d{6})',                      # "security: 123456"
            r'kode\s*akses.*?(\d{6})',                  # "kode akses: 123456"
        ]
        
        for i, pattern in enumerate(patterns):
            print(f"Trying security pattern {i+1}: {pattern}")
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                code = match.group(1)
                print(f"Security pattern {i+1} matched! Found code: {code}")
                # ONLY accept 6-digit codes for security
                if len(code) == 6 and code.isdigit():
                    return code
                else:
                    print(f"Code {code} is not 6 digits, skipping...")
        
        print("No 6-digit security code found")
        return None
        
    def extract_email_confirmation_code(self, text):
        """Extract email confirmation code - EXACT from original get_code.py"""
        print(f"Searching for email confirmation code in text: {text[:300]}...")
        
        # Email confirmation patterns (6-digit codes for email confirmation)
        # ORDERED BY SPECIFICITY - Most specific patterns first to avoid wrong matches - EXACT from original
        patterns = [
            # HIGHEST PRIORITY - Exact patterns from screenshots
            r'(\d{6})\s+adalah\s+kode\s+[Aa]nda\s+untuk\s+mengonfirmasi\s+email\s+ini',     # "790433 adalah kode Anda untuk mengonfirmasi email ini"
            r'(\d{6})\s+adalah\s+kode\s+[Aa]nda\s+untuk\s+mengonfirmasi\s+alamat\s+email', # "790433 adalah kode Anda untuk mengonfirmasi alamat email"
            
            # Direct patterns from Gmail/ZohoMail screenshots
            r'kode\s+konfirmasi\s+[Aa]nda.*?(\d{6})',                            # "kode konfirmasi Anda" followed by 6-digit
            r'masukkan\s+kode\s+konfirmasi.*?(\d{6})',                           # "Masukkan kode konfirmasi" 
            r'(\d{6})\s*untuk\s+mengonfirmasi\s+alamat\s+email',                # "615792 untuk mengonfirmasi alamat email"
            r'(\d{6})\s*satu\s+langkah\s+lagi.*?mengonfirmasi.*?email',         # "615792 satu langkah lagi untuk mengonfirmasi alamat email ini"
            r'(\d{6})\s*[,.]?\s*satu\s+langkah\s+lagi.*?mengonfirmasi.*?email', # "615792, satu langkah lagi untuk mengonfirmasi alamat email ini"
            
            # Indonesian patterns - MOST SPECIFIC FIRST
            r'(\d{6})\s+adalah\s+kode\s+[Aa]nda\s+untuk\s+mengonfirmasi\s+email',  # "615792 adalah kode Anda untuk mengonfirmasi email"
            r'(\d{6})\s*[,.]?\s*adalah\s*kode.*?mengonfirmasi.*?email',          # More flexible with punctuation
            
            # Facebook specific patterns
            r'satu\s+langkah\s+lagi.*?mengonfirmasi.*?alamat\s+email.*?(\d{6})', # "Satu langkah lagi untuk mengonfirmasi alamat email ini: 615792"
            r'untuk\s+mengonfirmasi\s+alamat\s+email.*?(\d{6})',                # "untuk mengonfirmasi alamat email ini 615792"
            
            # Instagram specific patterns
            r'(\d{6})\s*adalah\s*kode\s*Instagram\s*Anda',                      # Instagram Indonesia
            r'(\d{6})\s*is\s*your\s*Instagram\s*code',                          # Instagram English
            r'(\d{6})\s*untuk\s*mengonfirmasi.*Instagram',                      # "123456 untuk mengonfirmasi Instagram"
            r'Instagram.*konfirmasi.*(\d{6})',                                  # "Instagram konfirmasi: 123456"
            
            # Reverse patterns (code after text) - LOWER PRIORITY
            r'kode\s+[Aa]nda\s+untuk\s+mengonfirmasi\s+email.*?(\d{6})',        # "kode Anda untuk mengonfirmasi email ini: 615792"
            r'mengonfirmasi\s+alamat\s+email.*?(\d{6})',                        # "mengonfirmasi alamat email ini: 615792"
            r'konfirmasi\s+alamat\s+email.*?(\d{6})',                           # "konfirmasi alamat email: 615792"
            r'kode\s+konfirmasi\s+email.*?(\d{6})',                             # "kode konfirmasi email Anda adalah: 615792"
            
            # English patterns - SPECIFIC CONFIRMATION CONTEXT
            r'(\d{6})\s+is\s+your\s+code\s+to\s+confirm\s+email',              # English version
            r'email\s+confirmation\s+code.*?(\d{6})',                           # "email confirmation code is 615792"
            r'confirm\s+your\s+email.*?(\d{6})',                                # "confirm your email with 615792"
            r'email\s+verification.*?(\d{6})',                                  # "email verification: 615792"
            r'your\s+email\s+confirmation\s+code\s+is\s+(\d{6})',              # "Your email confirmation code is 615792"
            
            # More flexible patterns - LOWEST PRIORITY
            r'(\d{6})\s*[,.]?\s*untuk\s+mengonfirmasi',                        # "615792, untuk mengonfirmasi"
            r'mengonfirmasi\s+email.*?(\d{6})',                                 # "mengonfirmasi email ini: 615792"
        ]
        
        for i, pattern in enumerate(patterns):
            print(f"Trying pattern {i+1}: {pattern}")
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                code = match.group(1)
                print(f"Pattern {i+1} matched! Found code: {code}")
                # Validate that it's a 6-digit code
                if len(code) == 6 and code.isdigit():
                    print(f"FINAL RESULT: Returning code {code}")
                    return code
                else:
                    print(f"Code {code} is not 6 digits, continuing...")
        
        print("No email confirmation code pattern matched")
        return None

@app.route('/api/test-connection', methods=['POST'])
def test_connection():
    data = request.json
    print(f"Testing connection with data: {data}")
    
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
    print(f"Getting codes with data: {data}")
    
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
        "service": "IMAP Proxy Server - Exact Match Original",
        "status": "running",
        "version": "3.0", 
        "endpoints": [
            "/api/test-connection",
            "/api/get-codes"
        ],
        "supported_platforms": [
            "Instagram", "Facebook", "Generic Email Confirmation"
        ],
        "pattern_source": "get_code.py exact match"
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
