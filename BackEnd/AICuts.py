from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import smtplib
import os
import re
import html
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import load_and_predict
from ultralytics import YOLO
from PIL import Image, ImageDraw, ImageFont
import os
import cv2
import numpy as np
from io import BytesIO
import base64
import tempfile


app = Flask(__name__)
CORS(app)

load_dotenv()

# Security configuration
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB limit
ALLOWED_MIME_TYPES = {
    'image/jpeg', 'image/jpg', 'image/png', 'image/gif', 
    'image/bmp', 'image/webp'
}

# Configure Flask security
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE  # Flask will reject files larger than this

# Load YOLO model once at startup
print("🚀 Loading YOLO model...")
YOLO_MODEL = load_and_predict.load_yolo_model()
if YOLO_MODEL is None:
    print("Failed to load YOLO model at startup!")
else:
    print("✅ YOLO model loaded successfully!")

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def validate_file_security(file):
    """Comprehensive file security validation"""
    errors = []
    
    # Check file extension
    if not allowed_file(file.filename):
        errors.append("Invalid file type. Only images are allowed.")
    
    # Check MIME type
    if file.content_type not in ALLOWED_MIME_TYPES:
        errors.append("Invalid file format detected.")
    
    # Check file size (Flask doesn't auto-check file size during upload)
    file.seek(0, 2)  # Seek to end
    file_size = file.tell()
    file.seek(0)  # Reset to beginning
    
    if file_size > MAX_FILE_SIZE:
        errors.append(f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB.")
    
    if file_size == 0:
        errors.append("File is empty.")
    
    return errors



@app.route('/api/upload', methods=['POST'])
def handle_image():
    """Handle image upload and return a success message"""
    try:
        # Check if the request contains files
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': 'No file part in the request.'}), 400
        
        file = request.files['file']
        
        # Check if a file was actually uploaded
        if file.filename == '':
            return jsonify({'success': False, 'message': 'No selected file.'}), 400
        
        # Security validation
        security_errors = validate_file_security(file)
        if security_errors:
            return jsonify({'success': False, 'message': security_errors[0]}), 400
        
        # Sanitize filename
        import secrets
        secure_filename = f"{secrets.token_hex(16)}.jpg"  # Generate random filename
        
        # Rate limiting for uploads
        client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.environ.get('REMOTE_ADDR', 'unknown'))
        is_allowed, remaining_time = check_rate_limit(client_ip, 'upload')
        if not is_allowed:
            return jsonify({
                'success': False, 
                'message': f'Please wait {remaining_time} seconds before uploading again.'
            }), 429
        
        # Check if model is loaded
        if YOLO_MODEL is None:
            return jsonify({'success': False, 'message': 'AI model not available. Please try again later.'}), 503
        
        else:
            # Save uploaded file to temporary location with secure filename
            with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg', prefix='upload_') as temp_file:
                file.save(temp_file.name)
                temp_file_path = temp_file.name
            
            try:
                results = load_and_predict.predict_face_shape(temp_file_path, YOLO_MODEL)
            finally:
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
            if results["success"]==False:
                return jsonify(results), 500
            
            else:
                return jsonify(results), 200
    except Exception as e:
        print(f"Upload error: {e}")
        return jsonify({'success': False, 'message': 'An error occurred while uploading the file.'}), 500



def sanitize_input(text):
    """Clean user input to prevent injection attacks"""
    if not text:
        return ""
    # Remove HTML tags and escape special characters
    text = html.escape(text.strip())
    # Remove any suspicious patterns
    text = re.sub(r'[<>"\']', '', text)
    return text

def validate_contact_data(data):
    """Validate contact form data"""
    errors = []
    
    # Check required fields
    firstname = data.get('firstname', '').strip()
    lastname = data.get('lastname', '').strip()
    subject = data.get('subject', '').strip()
    
    if not firstname:
        errors.append("First name is required")
    elif len(firstname) < 2 or len(firstname) > 50:
        errors.append("First name must be 2-50 characters")
    
    if not lastname:
        errors.append("Last name is required")
    elif len(lastname) < 2 or len(lastname) > 50:
        errors.append("Last name must be 2-50 characters")
    
    if not subject:
        errors.append("Subject is required")
    elif len(subject) < 10 or len(subject) > 500:  # Reduced max length
        errors.append("Subject must be 10-500 characters")
    
    # Check for suspicious patterns
    suspicious_patterns = [r'<script', r'javascript:', r'onclick', r'onerror']
    for field in [firstname, lastname, subject]:
        for pattern in suspicious_patterns:
            if re.search(pattern, field, re.IGNORECASE):
                errors.append("Invalid characters detected")
                break
    
    return errors, sanitize_input(firstname), sanitize_input(lastname), sanitize_input(subject)

# Simple rate limiting - store last submission times
last_submissions = {}

def check_rate_limit(ip_address, endpoint_type='upload'):
    """Check if IP is making requests too frequently"""
    current_time = datetime.now()
    
    # Different cooldowns for different endpoints
    if endpoint_type == 'contact':
        cooldown_seconds = 86400  # 24 hours (1 day) for contact form
    else:  # 'upload' or default
        cooldown_seconds = 30  # 30 seconds for image uploads
    
    # Use different keys for different endpoints
    key = f"{ip_address}_{endpoint_type}"
    
    if key in last_submissions:
        time_diff = (current_time - last_submissions[key]).total_seconds()
        if time_diff < cooldown_seconds:
            remaining_time = int(cooldown_seconds - time_diff)
            return False, remaining_time
    
    last_submissions[key] = current_time
    return True, 0

def send_email(firstname, lastname, subject):
    try:
        # Get email credentials from environment variables
        sender_email = os.getenv('EMAIL_ADDRESS')
        sender_password = os.getenv('EMAIL_PASSWORD')
        receiver_email = sender_email  # Send to yourself
        
        # Create email message
        message = MIMEMultipart()
        message["From"] = sender_email
        message["To"] = receiver_email
        message["Subject"] = f"New Contact Form - {firstname} {lastname}"
        
        # Email body
        body = f"""
New contact form submission:

Name: {firstname} {lastname}
Subject: {subject}
Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """
        
        message.attach(MIMEText(body, "plain"))
        
        # Send email
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, receiver_email, message.as_string())
        server.quit()
        
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False

@app.route('/api/contact', methods=['POST'])
def handle_contact():
    try:
        # Rate limiting
        client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.environ.get('REMOTE_ADDR', 'unknown'))
        is_allowed, remaining_time = check_rate_limit(client_ip, 'contact')
        if not is_allowed:
            # Convert seconds to hours for better user experience
            remaining_hours = remaining_time // 3600
            remaining_minutes = (remaining_time % 3600) // 60
            
            if remaining_hours > 0:
                time_msg = f"{remaining_hours} hours and {remaining_minutes} minutes"
            else:
                time_msg = f"{remaining_minutes} minutes"
                
            return jsonify({
                'success': False, 
                'message': f'You can only submit one contact form per day. Please wait {time_msg} before submitting again.'
            }), 429
        
        # Get and validate JSON data
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'Invalid request format.'}), 400
        
        # Validate and sanitize input
        errors, clean_firstname, clean_lastname, clean_subject = validate_contact_data(data)
        
        if errors:
            return jsonify({'success': False, 'message': 'Please check your input and try again.'}), 400
        
        # Send email with cleaned data
        email_sent = send_email(clean_firstname, clean_lastname, clean_subject)
        
        if email_sent:
            return jsonify({'success': True, 'message': 'Message sent successfully!'}), 200
        else:
            return jsonify({'success': False, 'message': 'Unable to send message. Please try again later.'}), 500
            
    except Exception as e:
        # Log error for debugging but don't expose details to user
        print(f"Contact form error: {e}")
        return jsonify({'success': False, 'message': 'An unexpected error occurred. Please try again later.'}), 500
    


if __name__ == '__main__':
    app.run(debug=True)


