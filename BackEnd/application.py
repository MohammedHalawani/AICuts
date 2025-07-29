from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import smtplib
import os
import re
import html
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
CORS(app, origins=["https://steelwarden.github.io", "https://steelwarden.github.io/AICuts/", "https://steelwarden.github.io/AICuts"])  # Allow your GitHub Pages URLs

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

    import magic
    mime = magic.from_buffer(file.read(2048), mime=True)
    file.seek(0)
    
    # Check MIME type
    if mime not in ALLOWED_MIME_TYPES:
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



@app.route('/upload', methods=['POST'])
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
            return jsonify({'success': False, 'message': "Invalid file format, make sure you meet the file requirments."}), 400
        
    
        
        # Rate limiting for uploads
        client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.environ.get('REMOTE_ADDR', 'unknown'))
        is_allowed, remaining_time = check_rate_limit(client_ip, 'upload')
        if not is_allowed:
            return jsonify({
                'success': False, 
                'message': f'Please wait {remaining_time} seconds before uploading again.'
            }), 429
        
        # Check if model is loaded

        YOLO_MODEL = load_and_predict.load_yolo_model()
        if YOLO_MODEL is None:
           return jsonify({'success': False, 'message': 'AI model not available. Please try again later.'}), 503


        
        else:
            # Save uploaded file to temporary location with secure filename
            with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg', prefix='upload_') as temp_file:
                image = Image.open(file).convert('RGB')
                image.save(temp_file.name)
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




if __name__ == '__main__':
    app.run(debug=False)


