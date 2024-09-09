import os
import cv2
import face_recognition
import numpy as np
import ast
import mysql.connector
import re, requests, json
from collections import defaultdict
import time
from datetime import datetime, timedelta

def connect_to_database():
    try:
        connection = mysql.connector.connect(
            host=LOCAL_HOST,
            user=USER,
            password=PASS,
            database=DB_NAME
        )
        print("Database connection established")
        return connection
    except mysql.connector.Error as error:
        print("Failed to connect to the database: {}".format(error))
        return None
    
def read_encoded_face(connection):
    try:
        username = []
        encoded_face = []

        cursor = connection.cursor()
        cursor.execute("SELECT * FROM encoded_face")
        rows = cursor.fetchall()

        for row in rows:
            username.append(row[1])
            numbers = re.findall(r'-?\d+\.?\d*(?:[Ee][+\-]?\d+)?', row[2])
            numpy_array = np.array([float(num) for num in numbers])
            encoded_face.append(numpy_array)

        cursor.close()

        return username, encoded_face
    
    except mysql.connector.Error as error:
        print("Failed to fetch data from the table: {}".format(error))


def record_attendance(connection, name, tmid, unit, division, email):
    try:
        cursor = connection.cursor()
        sql = f"""
                INSERT INTO attendance(attendance_name, attendance_tmid, attendance_unit, attendance_division, attendance_email) 
                VALUES 
                ('{tmid}','{name}','{unit}','{division}','{email}')   
                """
        cursor.execute(sql)
        connection.commit()
        print("Data inserted successfully.")
    except mysql.connector.Error as error:
        connection.rollback()
        print("Failed to insert data into the table: {}".format(error))

# Initialize and load data
username_db = []
last_attendance_time = defaultdict(lambda: datetime.now())  # Initialize last attendance time for each user
connection = connect_to_database()
if connection:
    username_db, face_encoding_db = read_encoded_face(connection=connection)

name_counts = defaultdict(int)

# Initialize webcam
cap = cv2.VideoCapture(0)

while True:
    start_time = time.time()
    success, img = cap.read()
    imgS = cv2.resize(img, (0, 0), None, 0.25, 0.25)
    imgS = cv2.cvtColor(imgS, cv2.COLOR_BGR2RGB)
    faces_in_frame = face_recognition.face_locations(imgS)
    encoded_faces = face_recognition.face_encodings(imgS, faces_in_frame)

    for encode_face, faceloc in zip(encoded_faces, faces_in_frame):
        matches = face_recognition.compare_faces(face_encoding_db, encode_face, tolerance=0.35)
        faceDist = face_recognition.face_distance(face_encoding_db, encode_face)
        matchIndex = np.argmin(faceDist)

        if matches[matchIndex]:
            name = username_db[matchIndex].lower()
            name_counts[name] += 1
            current_time = datetime.now()
            
            # Check if 5 minute has passed since the last recorded attendance
            if current_time - last_attendance_time[name] > timedelta(minutes=5):
                print('5 minute has passed')
                name_counts[name] = 10

            if name_counts[name] < 10:
                    verification = "verifying..."
                    print(f"{name} is present, verifying... ({name_counts[name]}/10)")
            else:
                    if name_counts[name] == 10:
                        print(f"recorded attendance for user: {name}")
                        url = f"http://localhost/faceattendance-main/capture.php?name={name}"
                        response = requests.get(url)

                        if response.status_code == 200:
                            res = json.loads(response.text)
                            if res:
                                record_attendance(connection, res['staff_id'], res['full_name'], res['unit'], res['division'], res['email'])
                                print(res)
                            else:
                                print("User not registered")
                                record_attendance(connection, name, "", "", "", "")
                        
                        # Update the last attendance time after recording
                        last_attendance_time[name] = current_time
                    verification = name
                    
            y1, x2, y2, x1 = faceloc
            y1, x2, y2, x1 = y1 * 4, x2 * 4, y2 * 4, x1 * 4
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.rectangle(img, (x1, y2 - 35), (x2, y2), (0, 255, 0), cv2.FILLED)
            cv2.putText(img, verification, (x1 + 6, y2 - 5), cv2.FONT_HERSHEY_COMPLEX, 1, (255, 255, 255), 2)
        else:
            name = "unknown"
            y1, x2, y2, x1 = faceloc
            y1, x2, y2, x1 = y1 * 4, x2 * 4, y2 * 4, x1 * 4
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.rectangle(img, (x1, y2 - 35), (x2, y2), (0, 255, 0), cv2.FILLED)
            cv2.putText(img, name, (x1 + 6, y2 - 5), cv2.FONT_HERSHEY_COMPLEX, 1, (255, 255, 255), 2)

    cv2.imshow('webcam', img)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

    # Calculate and print FPS
    end_time = time.time()
    fps = 1 / (end_time - start_time)
    print(f"FPS: {fps:.2f}")

# Release resources
cap.release()
cv2.destroyAllWindows()
