import os
import random
import time
import smtplib
import io
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from flask import Flask, render_template, request, redirect, url_for, flash, Response
from flask_socketio import SocketIO, emit
from PIL import Image
from flask import session
import numpy as np
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here')
socketio = SocketIO(app)

# Configuration
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Environment variables
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', 'imagesteganography24@gmail.com')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', 'fgku cjzw uqev zkrl')
app.config['MAIL_USE_TLS'] = True

otp_store = {}
email_attempts = {}
COVER_IMAGE_MIN_SIZE = 1 * 1024  # 1KB
def generate_otp():
    otp = str(random.randint(1000, 9999))
    expiry_time = time.time() + 24 * 3600
    otp_store[otp] = expiry_time
    return otp

def is_otp_valid(otp):
    if otp in otp_store and time.time() < otp_store[otp]:
        return True
    return False

def send_otp_email(receiver_email, stego_image_path):
    try:
        if receiver_email in email_attempts and email_attempts[receiver_email] >= 3:
            flash("Too many attempts. Please try again later.")
            return False

        otp = generate_otp()
        subject = "Image Steganography OTP and Stego Image"
        body = f'Welcome to Image Steganography. Here is your OTP for extracting data: "{otp}"\n\n'
        body += "The attached image contains the hidden data. Use the OTP to extract it."

        msg = MIMEMultipart()
        msg['From'] = 'imagesteganography24@gmail.com'
        msg['To'] = receiver_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        with open(stego_image_path, 'rb') as attachment:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename={os.path.basename(stego_image_path)}')
            msg.attach(part)

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login('imagesteganography24@gmail.com', "fgku cjzw uqev zkrl")
            server.sendmail('imagesteganography24@gmail.com', receiver_email, msg.as_string())
        
        if receiver_email in email_attempts:
            email_attempts[receiver_email] = 0
        return True
    except Exception as e:
        if receiver_email not in email_attempts:
            email_attempts[receiver_email] = 1
        else:
            email_attempts[receiver_email] += 1
        flash("Failed to send email. Please try again.")
        return False

def text_to_bits(text):
    return ''.join(format(ord(i), '08b') for i in text)

def bits_to_text(bits):
    chars = [bits[i:i+8] for i in range(0, len(bits), 8)]
    return ''.join(chr(int(char, 2)) for char in chars)

def get_image_bytes(image_path):
    with open(image_path, 'rb') as image_file:
        return image_file.read()

def get_audio_bytes(audio_path):
    with open(audio_path, 'rb') as audio_file:
        return audio_file.read()

def get_video_bytes(video_path):
    with open(video_path, 'rb') as video_file:
        return video_file.read()

def calculate_capacity(cover_image_path):
    cover_image = Image.open(cover_image_path)
    width, height = cover_image.size
    capacity_bits = width * height * 3
    capacity_bytes = capacity_bits // 8
    capacity_kb = capacity_bytes / 1024
    return capacity_kb

def hide_data_in_image(cover_image_path, hidden_file_path, output_image_path):
    try:
        cover_image = Image.open(cover_image_path)
        pixels = cover_image.load()
        with open(hidden_file_path, 'rb') as file:
            data = file.read()
        binary_data = ''.join(format(byte, '08b') for byte in data) + '1111111111111110'
        width, height = cover_image.size
        binary_index = 0
        for y in range(height):
            for x in range(width):
                if binary_index < len(binary_data):
                    r, g, b = pixels[x, y]
                    r = (r & ~1) | int(binary_data[binary_index])
                    binary_index += 1
                    if binary_index < len(binary_data):
                        g = (g & ~1) | int(binary_data[binary_index])
                        binary_index += 1
                    if binary_index < len(binary_data):
                        b = (b & ~1) | int(binary_data[binary_index])
                        binary_index += 1
                    pixels[x, y] = (r, g, b)
                else:
                    break
        cover_image.save(output_image_path)
        return True
    except Exception as e:
        flash(f"Error hiding data: {e}")
        return False

# Helper functions (generate_otp, is_otp_valid, send_otp_email, etc.) remain the same...

def extract_data_from_image(img_io):
    try:
        img_io.seek(0)
        stego_image = Image.open(img_io)
        pixels = stego_image.load()
        width, height = stego_image.size
        binary_data = ""
        total_pixels = width * height
        
        for y in range(height):
            for x in range(width):
                r, g, b = pixels[x, y]
                binary_data += str(r & 1)
                binary_data += str(g & 1)
                binary_data += str(b & 1)
                if binary_data[-16:] == '1111111111111110':
                    break
                progress = int((y * width + x) / total_pixels * 100)
                socketio.emit('progress_update', {'progress': progress})
            else:
                continue
            break

        extracted_bytes = bytearray()
        for i in range(0, len(binary_data[:-16]), 8):
            byte = binary_data[i:i+8]
            if len(byte) == 8:
                extracted_bytes.append(int(byte, 2))

        return bytes(extracted_bytes)
    except Exception as e:
        flash(f"Error extracting text: {e}")
        return None
def hide_image_in_image(cover_image_path, hidden_image_path, output_image_path):
    try:
        cover_image = Image.open(cover_image_path)
        hidden_image_bytes = get_image_bytes(hidden_image_path)
        binary_hidden_image = ''.join(format(byte, '08b') for byte in hidden_image_bytes) + '1111111111111110'
        width, height = cover_image.size
        pixels = cover_image.load()
        binary_index = 0
        for y in range(height):
            for x in range(width):
                if binary_index < len(binary_hidden_image):
                    r, g, b = pixels[x, y]
                    r = (r & ~1) | int(binary_hidden_image[binary_index])
                    binary_index += 1
                    if binary_index < len(binary_hidden_image):
                        g = (g & ~1) | int(binary_hidden_image[binary_index])
                        binary_index += 1
                    if binary_index < len(binary_hidden_image):
                        b = (b & ~1) | int(binary_hidden_image[binary_index])
                        binary_index += 1
                    pixels[x, y] = (r, g, b)
                else:
                    break
        cover_image.save(output_image_path)
        return True
    except Exception as e:
        flash(f"Error hiding image: {e}")
        return False
def extract_image_from_image(img_io):
    try:
        img_io.seek(0)
        stego_image = Image.open(img_io)
        binary_hidden_image = ""
        total_pixels = stego_image.width * stego_image.height
        pixel_count = 0
        
        for pixel in stego_image.getdata():
            r, g, b = pixel
            binary_hidden_image += str(r & 1)
            binary_hidden_image += str(g & 1)
            binary_hidden_image += str(b & 1)
            pixel_count += 1
            progress = int((pixel_count / total_pixels) * 100)
            socketio.emit('progress_update', {'progress': progress})
            
        binary_hidden_image = binary_hidden_image[:-16]
        hidden_image_bytes = bytearray()
        for i in range(0, len(binary_hidden_image), 8):
            byte = binary_hidden_image[i:i+8]
            if len(byte) == 8:
                hidden_image_bytes.append(int(byte, 2))
                
        return bytes(hidden_image_bytes)
    except Exception as e:
        flash(f"Error extracting image: {e}")
        return None
def hide_audio_in_image(cover_image_path, audio_path, output_image_path):
    try:
        cover_image = Image.open(cover_image_path)
        audio_bytes = get_audio_bytes(audio_path)
        binary_audio = ''.join(format(byte, '08b') for byte in audio_bytes) + '1111111111111110'
        width, height = cover_image.size
        pixels = cover_image.load()
        binary_index = 0
        for y in range(height):
            for x in range(width):
                if binary_index < len(binary_audio):
                    r, g, b = pixels[x, y]
                    r = (r & ~1) | int(binary_audio[binary_index])
                    binary_index += 1
                    if binary_index < len(binary_audio):
                        g = (g & ~1) | int(binary_audio[binary_index])
                        binary_index += 1
                    if binary_index < len(binary_audio):
                        b = (b & ~1) | int(binary_audio[binary_index])
                        binary_index += 1
                    pixels[x, y] = (r, g, b)
                else:
                    break
        cover_image.save(output_image_path)
        return True
    except Exception as e:
        flash(f"Error hiding audio: {e}")
        return False
def extract_audio_from_image(img_io):
    try:
        img_io.seek(0)
        stego_image = Image.open(img_io)
        binary_audio = ""
        total_pixels = stego_image.width * stego_image.height
        pixel_count = 0
        
        for pixel in stego_image.getdata():
            r, g, b = pixel
            binary_audio += str(r & 1)
            binary_audio += str(g & 1)
            binary_audio += str(b & 1)
            pixel_count += 1
            progress = int((pixel_count / total_pixels) * 100)
            socketio.emit('progress_update', {'progress': progress})
            
        binary_audio = binary_audio[:-16]
        audio_bytes = bytearray()
        for i in range(0, len(binary_audio), 8):
            byte = binary_audio[i:i+8]
            if len(byte) == 8:
                audio_bytes.append(int(byte, 2))
                
        return bytes(audio_bytes)
    except Exception as e:
        flash(f"Error extracting audio: {e}")
        return None
def hide_video_in_image(cover_image_path, video_path, output_image_path):
    try:
        cover_image = Image.open(cover_image_path)
        video_bytes = get_video_bytes(video_path)
        binary_video = ''.join(format(byte, '08b') for byte in video_bytes) + '1111111111111110'
        width, height = cover_image.size
        pixels = cover_image.load()
        binary_index = 0
        for y in range(height):
            for x in range(width):
                if binary_index < len(binary_video):
                    r, g, b = pixels[x, y]
                    r = (r & ~1) | int(binary_video[binary_index])
                    binary_index += 1
                    if binary_index < len(binary_video):
                        g = (g & ~1) | int(binary_video[binary_index])
                        binary_index += 1
                    if binary_index < len(binary_video):
                        b = (b & ~1) | int(binary_video[binary_index])
                        binary_index += 1
                    pixels[x, y] = (r, g, b)
                else:
                    break
        cover_image.save(output_image_path)
        return True
    except Exception as e:
        flash(f"Error hiding video: {e}")
        return False
def extract_video_from_image(img_io):
    try:
        img_io.seek(0)
        stego_image = Image.open(img_io)
        binary_video = ""
        total_pixels = stego_image.width * stego_image.height
        pixel_count = 0
        
        for pixel in stego_image.getdata():
            r, g, b = pixel
            binary_video += str(r & 1)
            binary_video += str(g & 1)
            binary_video += str(b & 1)
            pixel_count += 1
            progress = int((pixel_count / total_pixels) * 100)
            socketio.emit('progress_update', {'progress': progress})
            
        binary_video = binary_video[:-16]
        video_bytes = bytearray()
        for i in range(0, len(binary_video), 8):
            byte = binary_video[i:i+8]
            if len(byte) == 8:
                video_bytes.append(int(byte, 2))
                
        return bytes(video_bytes)
    except Exception as e:
        flash(f"Error extracting video: {e}")
        return None
def get_unique_filename(base_path, filename):
    name, ext = os.path.splitext(filename)
    counter = 1
    new_filename = filename
    while os.path.exists(os.path.join(base_path, new_filename)):
        new_filename = f"{name}_{counter}{ext}"
        counter += 1
    return new_filename

def delete_expired_images(image_folder):
    for filename in os.listdir(image_folder):
        file_path = os.path.join(image_folder, filename)
        creation_time = os.path.getctime(file_path)
        if time.time() - creation_time > 24 * 3600:
            os.remove(file_path)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/hide', methods=['GET', 'POST'])
def hide():
    if request.method == 'POST':
        try:
            if not all(key in request.form for key in ['email', 'data_type']) or \
               not all(key in request.files for key in ['cover_image', 'hidden_file']):
                flash("All fields are required", "error")
                return redirect(url_for('hide'))

            receiver_email = request.form['email']
            data_type = request.form['data_type']
            cover_image = request.files['cover_image']
            hidden_file = request.files['hidden_file']

            # Secure filename handling
            cover_image_filename = secure_filename(f"cover_{time.time()}.png")
            cover_image_path = os.path.join(app.config['UPLOAD_FOLDER'], cover_image_filename)
            cover_image.save(cover_image_path)

            if os.path.getsize(cover_image_path) < COVER_IMAGE_MIN_SIZE:
                flash("Cover image too small", "error")
                return redirect(url_for('hide'))

            # Process hidden file
            hidden_file_ext = os.path.splitext(hidden_file.filename)[1]
            hidden_file_filename = secure_filename(f"hidden_{time.time()}{hidden_file_ext}")
            hidden_file_path = os.path.join(app.config['UPLOAD_FOLDER'], hidden_file_filename)
            hidden_file.save(hidden_file_path)

            # Create output image
            output_image_filename = secure_filename(f"stego_{data_type}_{time.time()}.png")
            output_image_path = os.path.join(app.config['UPLOAD_FOLDER'], output_image_filename)

            # Processing based on data type
            process_functions = {
                'text': hide_data_in_image,
                'image': hide_image_in_image,
                'audio': hide_audio_in_image,
                'video': hide_video_in_image
            }
            
            if not process_functions[data_type](cover_image_path, hidden_file_path, output_image_path):
                return redirect(url_for('hide'))

            # Email handling
            if not send_otp_email(receiver_email, output_image_path):
                return render_template('email_failed.html', 
                                     email=receiver_email,
                                     output_image_path=output_image_path)

            return redirect(url_for('thank_you', action='hide'))
            
        except Exception as e:
            flash(f"Error: {str(e)}", "error")
            return redirect(url_for('hide'))

    return render_template('hide.html')

@app.route('/extract', methods=['GET', 'POST'])
def extract():
    if request.method == 'POST':
        otp = request.form.get('otp', '')
        if is_otp_valid(otp):
            # Store verification in session
            session['otp_verified'] = True
            return redirect(url_for('extract_data_type'))
        flash("Invalid OTP", "error")
    return render_template('extract.html')

@app.route('/extract_data_type', methods=['GET', 'POST'])
def extract_data_type():
    # Check if OTP was verified
    if not session.get('otp_verified'):
        return redirect(url_for('extract'))
    
    if request.method == 'POST':
        try:
            # Validate form submission
            if 'stego_image' not in request.files:
                flash('No file uploaded', 'error')
                return redirect(request.url)
                
            stego_image = request.files['stego_image']
            if stego_image.filename == '':
                flash('No file selected', 'error')
                return redirect(request.url)
                
            data_type = request.form.get('data_type', 'text')

            # Process image in memory
            img_bytes = stego_image.read()
            img_io = io.BytesIO(img_bytes)

            # Perform extraction
            if data_type == 'text':
                extracted_data = extract_data_from_image(img_io)
                mimetype = 'text/plain'
                ext = 'txt'
            elif data_type == 'image':
                extracted_data = extract_image_from_image(img_io)
                mimetype = 'image/png'
                ext = 'png'
            elif data_type == 'audio':
                extracted_data = extract_audio_from_image(img_io)
                mimetype = 'audio/wav'
                ext = 'wav'
            elif data_type == 'video':
                extracted_data = extract_video_from_image(img_io)
                mimetype = 'video/mp4'
                ext = 'mp4'
            else:
                flash('Invalid data type selected', 'error')
                return redirect(request.url)

            if not extracted_data:
                flash('Extraction failed', 'error')
                return redirect(request.url)

            # Clear OTP verification after successful extraction
            session.pop('otp_verified', None)
            
            # Send file to user
            mem_file = io.BytesIO(extracted_data)
            return Response(
                mem_file,
                mimetype=mimetype,
                headers={
                    'Content-Disposition': f'attachment; filename=extracted.{ext}',
                    'Content-Length': len(extracted_data)
                }
            )
            
        except Exception as e:
            flash(f'Extraction failed: {str(e)}', 'error')
            app.logger.error(f'Extraction error: {str(e)}')
            return redirect(request.url)

    # GET request - show the form
    return render_template('extract_data_type.html')
@app.route('/thank_you')
def thank_you():
    action = request.args.get('action', 'exit')
    return render_template('thank_you.html', action=action)

@app.route('/success')
def success():
    return render_template('success.html')

@app.route('/resend_email', methods=['POST'])
def resend_email():
    email = request.form['email']
    output_image_path = request.form['output_image_path']
    if send_otp_email(email, output_image_path):
        return redirect(url_for('thank_you', action='hide'))
    return redirect(url_for('hide'))

if __name__ == '__main__':
    socketio.run(app, host='127.0.0.1', port=5000, debug=True)
# Other routes (index, hide, extract, thank_you, etc.) remain the same...
