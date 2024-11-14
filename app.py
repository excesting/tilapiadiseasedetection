import argparse
import io
from PIL import Image

import torch
import cv2
import numpy as np
import tensorflow as tf
from re import DEBUG, sub
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    send_file,
    url_for,
    Response,
    flash,
    session
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from flask_migrate import Migrate
from werkzeug.utils import secure_filename, send_from_directory
from werkzeug.security import check_password_hash
import os
import subprocess
from subprocess import Popen
import re
import requests
import shutil
import time
import glob
import datetime

from ultralytics import YOLO


app = Flask(__name__, static_folder='static')


# Database Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///./aquadetect.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your_secret_key'  # Needed for session management

# Initialize Database and Migrate
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Define User Model
class UserLogin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable = False)

# Define LocationInfo Model
class LocationInfo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    location = db.Column(db.String(120), nullable=False)
    disease = db.Column(db.String(120), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class Card(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    image_path = db.Column(db.String(120), nullable=False)  # Path to the image
    description = db.Column(db.Text, nullable=False)  # Description text for the card

# Function to initialize default cards in the database
def initialize_cards():
    with app.app_context():  # Ensure the application context is available
        # Check if the CardInfo table is empty
        if Card.query.count() == 0:
            # Define default card data
            card1 = Card(image_path='static/images/image-45.png', description='To aid fishermen in discerning the health status of Nile Tilapia, distinguishing between vitality and potential pathogenic conditions.')
            card2 = Card(image_path='static/images/image-43.png', description='To Ensure the provision of high-quality Nile Tilapia fish to consumers.')
            card3 = Card(image_path='static/images/image-44.png', description='To minimize production losses in aquaculture.')
            
            # Add all cards to the session
            db.session.add_all([card1, card2, card3])
            # Commit the session to write data to the database
            db.session.commit()

            print("Default cards added to CardInfo table.")
        else:
            print("CardInfo table already contains data.")

# Create Database Tables
with app.app_context():
    db.create_all()
    initialize_cards()

    

@app.route("/")
def hello_world():
    if 'logged_in' not in session or not session['logged_in']:
        return redirect(url_for('landing'))

    # Fetch all card information from the database
    cards = Card.query.all()
    return render_template('landing.html', cards=cards)

@app.route('/detect')
def detect():
    # return render_template("index.html")
    if "image_path" in request.args:
        image_path = request.args["image_path"]
        return render_template("index.html", image_path=image_path)
    return render_template("index.html")


@app.route("/contact")
def contact():
    # return render_template("index.html")
    return render_template('contact.html')

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form['username']
        password = request.form['password']
        
        user = UserLogin.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            flash('Login successful!', 'success')
            session['logged_in'] = True
            session['username'] = username
            return redirect(url_for('landing'))
        else:
            flash('Invalid credentials. Please try again.', 'danger')
    
    return render_template('login.html')



@app.route("/test")
def test():
    # Get filter parameters from the query string
    filter_location = request.args.get('location', '')
    filter_disease = request.args.get('disease', '')
    
    # Get pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = 10  # Number of records per page
    offset = (page - 1) * per_page

    # Build the query with filters
    query = db.session.query(LocationInfo)

    if filter_location:
        query = query.filter(LocationInfo.location.ilike(f"%{filter_location}%"))
    
    if filter_disease:
        query = query.filter(LocationInfo.disease.ilike(f"%{filter_disease}%"))

    # Sort by timestamp in descending order (LIFO)
    query = query.order_by(LocationInfo.timestamp.desc())

    # Paginate the results
    total = query.count()
    location_info_records = query.offset(offset).limit(per_page).all()

    # Determine URLs for pagination
    base_url = url_for('test', location=filter_location, disease=filter_disease)
    prev_url = url_for('test', location=filter_location, disease=filter_disease, page=page-1) if page > 1 else None
    next_url = url_for('test', location=filter_location, disease=filter_disease, page=page+1) if (page * per_page) < total else None

    return render_template('test.html', 
                           location_info_records=location_info_records, 
                           filter_location=filter_location, 
                           filter_disease=filter_disease, 
                           prev_url=prev_url,
                           next_url=next_url)


@app.route("/logout")
def logout():
    # Clear the session to log out the user
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/landing')
def landing():
    # Fetch all card information from the database
    cards = Card.query.all()
    return render_template('landing.html', cards=cards)

app.config['UPLOAD_FOLDER'] = 'static/images'

@app.route('/edit_cards', methods=['GET', 'POST'])
def edit_cards():
    if request.method == 'POST':
        # Get form data
        card_id = int(request.form['card_id'])
        description = request.form['description']
        image_file = request.files['image']

        # Find the card to update
        card = Card.query.get(card_id)
        if card:
            card.description = description

            if image_file:
                # Save the new image
                image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_file.filename)
                image_file.save(image_path)
                card.image_path = image_path

            # Save changes to the database
            db.session.commit()

        # Redirect back to the landing page
        return redirect(url_for('landing'))

    # Fetch current cards for the form
    cards = Card.query.all()
    return render_template('edit_cards.html', cards=cards)



@app.route("/detect", methods=["GET", "POST"])
def predict_img():
    if request.method == "POST":
        if 'file' in request.files:
            f = request.files['file']
            basepath = os.path.dirname(__file__)
            filepath = os.path.join(basepath, 'uploads', f.filename)
            print("upload folder is ", filepath)
            f.save(filepath)
            predict_img.imgpath = f.filename
            print("printing predict_img :::::: ", predict_img)

            file_extension = f.filename.rsplit('.', 1)[1].lower()

            # Fetch form data
            location = request.form.get('location')  # Fetch the location from the form
            timestamp = request.form.get('timestamp')  # Fetch the timestamp from the form

            # Convert the date from the form to a datetime object if needed
            # If the date format is 'YYYY-MM-DD', you can use strptime to parse it
            try:
                timestamp = datetime.datetime.strptime(timestamp, '%Y-%m-%d')
            except (ValueError, TypeError):
                timestamp = datetime.datetime.now()  # Fallback to current time

            if file_extension == 'jpg':
                # Handle image upload
                img = cv2.imread(filepath)

                # Perform the detection
                model = YOLO('best.pt')
                detections = model(img, save=True)

                # Find the latest subdirectory in the 'runs/detect' folder
                folder_path = os.path.join(basepath, 'runs', 'detect')
                subfolders = [f for f in os.listdir(folder_path) if os.path.isdir(os.path.join(folder_path, f))]
                latest_subfolder = max(subfolders, key=lambda x: os.path.getctime(os.path.join(folder_path, x)))

                # Construct the relative path to the detected image file
                static_folder = os.path.join(basepath, 'static', 'assets')
                relative_image_path = os.path.relpath(os.path.join(folder_path, latest_subfolder, f.filename), static_folder)
                image_path = os.path.join(folder_path, latest_subfolder, f.filename)
                print("Relative image path:", relative_image_path)  # Print the relative_image_path for debugging
                
                # Extract object classes and their labels
                object_classes = detections[0].boxes.cls.to('cpu').tolist()
                # Example class names, you should replace this with your actual class names
                class_names = ['Columnaris Disease','Motile Aeromonad Septicemia','Normal Nile Tilapia','Parasitic Diseases','Streptococcosis','Tilapia Lake virus']
                detected_labels = [class_names[int(cls)] for cls in object_classes]

                # Save the data only if it hasn't been saved already during this request
                if 'data_saved' not in session:
                    for disease in detected_labels:
                        if location and disease:
                            location_info = LocationInfo(location=location, disease=disease, timestamp=timestamp)
                            db.session.add(location_info)
                    db.session.commit()  # Commit the changes to the database 

                    # Mark the data as saved in the session
                    session['data_saved'] = True

                # Debug output
                print("Detected Object Classes:", object_classes)
                print("Detected Labels:", detected_labels)

                return render_template('result.html', image_path=relative_image_path, media_type='image', detected_labels=detected_labels)

            elif file_extension == "mp4":
                # Handle video upload
                video_path = filepath  # replace with your video path
                cap = cv2.VideoCapture(video_path)

                # get video dimensions
                frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

                # Define the codec and create VideoWriter object
                fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                out = cv2.VideoWriter(
                    "output.mp4", fourcc, 30.0, (frame_width, frame_height)
                )

                # initialize the YOLOv8 model here
                model = YOLO("best.pt")

                while cap.isOpened():
                    ret, frame = cap.read()
                    if not ret:
                        break

                    # do YOLO detection on the frame
                    results = model(frame, save=True)
                    print(results)
                    cv2.waitKey(1)

                    res_plotted = results[0].plot()
                    cv2.imshow("result", res_plotted)

                    # write the frame to the output video
                    out.write(res_plotted)

                    if cv2.waitKey(1) == ord("q"):
                        break

                return render_template('result.html', video_path='output.mp4', media_type='video')

    # If no file uploaded or GET request, return the template with default values
    return render_template("result.html", image_path="", media_type='image')

@app.route("/<path:filename>")
def display(filename):
    folder_path = "runs/detect"
    subfolders = [
        f
        for f in os.listdir(folder_path)
        if os.path.isdir(os.path.join(folder_path, f))
    ]
    latest_subfolder = max(
        subfolders, key=lambda x: os.path.getctime(os.path.join(folder_path, x))
    )
    directory = os.path.join(folder_path, latest_subfolder)
    print("printing directory: ", directory)
    files = os.listdir(directory)
    latest_file = files[0]

    print(latest_file)

    image_path = os.path.join(directory, latest_file)

    file_extension = latest_file.rsplit(".", 1)[1].lower()

    if file_extension == "jpg":
        return send_file(image_path, mimetype="image/jpeg")
    elif file_extension == "mp4":
        return send_file(image_path, mimetype="video/mp4")
    else:
        return "Invalid file format"


def get_frame():
    folder_path = os.getcwd()
    mp4_files = "output.mp4"
    print("files being read...")
    video = cv2.VideoCapture(mp4_files)  # detected video path
    while True:
        success, frame = video.read()
        if not success:
            print("file not being read")
            break
        else:
            ret, buffer = cv2.imencode(".jpg", frame)
            frame = buffer.tobytes()

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n\r\n"
        )
        time.sleep(0.1)  # Control the frame rate to display one frame every 100 milliseconds:



# function to display the detected objects video on html page
@app.route("/video_feed")
def video_feed():
    # folder_path = os.getcwd()
    # mp4_file = "output.mp4"
    # video_path = os.path.join(folder_path, mp4_file)
    # return send_file(video_path, mimetype="video")
    return Response(get_frame(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/webcam_feed")
def webcam_feed():
    cap = cv2.VideoCapture(0) # 0 for camera

    def generate():
        while True:
            success, frame = cap.read()
            if not success:
                break

            # Perform object detection on the frame
            img = Image.fromarray(frame)
            model = YOLO("best.pt")
            results = model(img, save=True)

            # Plot the detected objects on the frame
            res_plotted = results[0].plot()
            img_BGR = cv2.cvtColor(res_plotted, cv2.COLOR_RGB2BGR)

            # Convert the frame to JPEG format for streaming
            ret, buffer = cv2.imencode(".jpg", img_BGR)
            frame = buffer.tobytes()

            yield (
                b"--frame\r\n" b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n\r\n"
            )

    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Flask app exposing yolov8 models")
    parser.add_argument("--port", default=5000, type=int, help="port number")
    args = parser.parse_args()
    model = YOLO("best.pt")
    app.run(host="0.0.0.0", port=args.port, debug=True)
