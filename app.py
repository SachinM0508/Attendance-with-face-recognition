# app.py
from flask import Flask, render_template, request, jsonify, send_from_directory
import sqlite3
from flask import Response
import csv
import os
import base64
import datetime
import io
import threading
from PIL import Image
import tempfile
import shutil

# optional libs
try:
    import numpy as np
    import face_recognition
    FACE_LIB_AVAILABLE = True
except Exception as e:
    FACE_LIB_AVAILABLE = False
    print("face_recognition (or numpy) not available:", e)

# --- Paths & Flask app ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
PHOTO_DIR = os.path.join(BASE_DIR, "static", "photos")
DB_DIR = os.path.join(BASE_DIR, "database")
DB_PATH = os.path.join(DB_DIR, "attendance.db")

os.makedirs(PHOTO_DIR, exist_ok=True)
os.makedirs(DB_DIR, exist_ok=True)

app = Flask(__name__, template_folder="templates", static_folder="static")

# cache of encodings: {abs_path: np.array}
ENCODING_CACHE = {}
ENCODING_CACHE_LOCK = threading.Lock()

# -----------------------
# Database initialization
# -----------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS students (
            student_id INTEGER PRIMARY KEY AUTOINCREMENT,
            roll_no TEXT UNIQUE,
            name TEXT NOT NULL,
            gender TEXT,
            dob TEXT,
            department TEXT,
            year TEXT,
            semester TEXT,
            class_div TEXT,
            phone TEXT,
            email TEXT,
            address TEXT,
            guardian_name TEXT,
            guardian_phone TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            photo_path TEXT,
            filename TEXT,
            created_at TEXT,
            FOREIGN KEY(student_id) REFERENCES students(student_id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            date TEXT,
            time_in TEXT,
            status TEXT,
            created_at TEXT,
            FOREIGN KEY(student_id) REFERENCES students(student_id)
        )
    """)

    conn.commit()
    conn.close()

init_db()

# -----------------------
# Helpers
# -----------------------
def save_base64_image(base64_data, filename):
    """
    Save base64 / dataURL to static/photos/filename and return absolute path.
    """
    if "," in base64_data:
        base64_data = base64_data.split(",", 1)[1]
    img_bytes = base64.b64decode(base64_data)
    path = os.path.join(PHOTO_DIR, filename)
    with open(path, "wb") as f:
        f.write(img_bytes)
    return path

def compute_face_encoding_from_file(path):
    """
    Return a 1-d numpy array encoding or None.
    Uses in-memory cache to speed repeated lookups.
    """
    if not FACE_LIB_AVAILABLE:
        return None
    with ENCODING_CACHE_LOCK:
        if path in ENCODING_CACHE:
            return ENCODING_CACHE[path]
    try:
        img = face_recognition.load_image_file(path)
        encs = face_recognition.face_encodings(img)
        if encs:
            enc = encs[0]
            with ENCODING_CACHE_LOCK:
                ENCODING_CACHE[path] = enc
            return enc
    except Exception as e:
        print("Encoding error for", path, ":", e)
    return None

def compute_face_encodings_from_pil(pil_img):
    """
    Given PIL.Image, return list of encodings found (may be empty).
    """
    if not FACE_LIB_AVAILABLE:
        return []
    arr = np.array(pil_img.convert("RGB"))
    return face_recognition.face_encodings(arr)

def filename_exists_in_db(conn, filename):
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM photos WHERE filename=?", (filename,))
    r = c.fetchone()
    return (r[0] if r else 0) > 0

def student_has_photo(conn, student_id):
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM photos WHERE student_id=?", (student_id,))
    r = c.fetchone()
    return (r[0] if r else 0) > 0

# -----------------------
# Motion-based liveness check (Option C)
# -----------------------
def frames_have_motion(frames_b64_list, threshold_pixels=1000, diff_threshold=30):
    """
    Simple server-side motion check:
    - frames_b64_list: list of dataURLs or base64 strings (len >= 2 recommended)
    - Convert to grayscale, compute absolute difference between consecutive frames,
      count number of pixels with diff > diff_threshold. If **any** consecutive pair
      has count > threshold_pixels -> treat as motion (live).
    Returns True if motion detected, False otherwise.

    NOTE: This is a heuristic fallback — client should send 2-4 frames captured a short time apart.
    """
    if not frames_b64_list or len(frames_b64_list) < 2:
        # Not enough frames to judge motion
        return False

    gray_frames = []
    for b64 in frames_b64_list:
        if "," in b64:
            b64 = b64.split(",", 1)[1]
        try:
            im = Image.open(io.BytesIO(base64.b64decode(b64))).convert("L")  # grayscale
            arr = np.array(im)
            gray_frames.append(arr)
        except Exception:
            return False

    for i in range(len(gray_frames)-1):
        a = gray_frames[i].astype("int16")
        b = gray_frames[i+1].astype("int16")
        diff = np.abs(a - b)
        # count pixels above threshold
        cnt = int((diff > diff_threshold).sum())
        if cnt > threshold_pixels:
            return True
    return False

# -----------------------
# Page routes
# -----------------------
@app.route("/")
def home():
    return render_template("web_index.html")

@app.route("/students")
def students_page():
    return render_template("student_management.html")

@app.route("/attendance")
def attendance_page():
    return render_template("attendance.html")

@app.route("/photos/<path:filename>")
def photos(filename):
    return send_from_directory(PHOTO_DIR, filename)

# -----------------------
# API: Students & Photos
# -----------------------
@app.route("/api/add_student", methods=["POST"])
def api_add_student():
    data = request.get_json() or {}
    name = data.get("name")
    if not name:
        return jsonify({"success": False, "message": "Name required"}), 400

    fields = (
        data.get("roll_no"),
        name,
        data.get("gender"),
        data.get("dob"),
        data.get("department"),
        data.get("year"),
        data.get("semester"),
        data.get("class_div"),
        data.get("phone"),
        data.get("email"),
        data.get("address"),
        data.get("guardian_name"),
        data.get("guardian_phone")
    )

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO students (roll_no, name, gender, dob, department, year, semester, class_div,
                                  phone, email, address, guardian_name, guardian_phone)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, fields)
        student_id = c.lastrowid
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"success": False, "message": "roll_no already exists"}), 409
    conn.close()
    return jsonify({"success": True, "student_id": student_id})

@app.route("/api/add_student_with_photo", methods=["POST"])
def api_add_student_with_photo():
    """
    Accepts JSON:
      {
        "name": "Full Name",
        "roll_no": "ROLL123",
        "photo": "<dataURL or base64>"   <-- optional but recommended
      }

    Behavior:
      - If roll exists and student already has a photo -> reject (409).
      - If roll exists and student has no photo -> attach provided photo.
      - If roll does not exist -> create student and attach photo if provided.
      - Primary filename: <roll>.png ; reject if file with same name already exists on disk/DB.
    """
    data = request.get_json() or {}
    name = data.get("name")
    roll = data.get("roll_no")
    photo_b64 = data.get("photo")

    if not name or not roll:
        return jsonify({"success": False, "message": "name and roll_no required"}), 400

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # check if roll exists
    c.execute("SELECT student_id FROM students WHERE roll_no=?", (roll,))
    row = c.fetchone()
    if row:
        student_id = row[0]
        # if student already has photo => reject
        c.execute("SELECT COUNT(*) FROM photos WHERE student_id=?", (student_id,))
        if (c.fetchone()[0] or 0) > 0:
            conn.close()
            return jsonify({"success": False, "message": "Student already has a photo - upload refused"}), 409
        # attach photo to existing student
        if not photo_b64:
            conn.close()
            return jsonify({"success": False, "message": "No photo provided to attach"}), 400
        safe_filename = f"{roll}.png"
        fs_path = os.path.join(PHOTO_DIR, safe_filename)
        if os.path.exists(fs_path) or filename_exists_in_db(conn, safe_filename):
            conn.close()
            return jsonify({"success": False, "message": "Filename collision - upload refused"}), 409
        try:
            saved = save_base64_image(photo_b64, safe_filename)
            created_at = datetime.datetime.now().isoformat()
            c.execute("INSERT INTO photos (student_id, photo_path, filename, created_at) VALUES (?, ?, ?, ?)",
                      (student_id, saved, safe_filename, created_at))
            conn.commit()
            # warm encoding cache
            if FACE_LIB_AVAILABLE:
                threading.Thread(target=compute_face_encoding_from_file, args=(saved,)).start()
            conn.close()
            return jsonify({"success": True, "student_id": student_id, "photo_url": f"/photos/{safe_filename}", "message": "Photo attached"}), 201
        except Exception as e:
            conn.close()
            return jsonify({"success": False, "message": f"Error saving photo: {e}"}), 500

    # create new student
    try:
        c.execute("""
            INSERT INTO students (roll_no, name, gender, dob, department, year, semester, class_div,
                                  phone, email, address, guardian_name, guardian_phone)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            roll,
            name,
            data.get("gender"),
            data.get("dob"),
            data.get("department"),
            data.get("year"),
            data.get("semester"),
            data.get("class_div"),
            data.get("phone"),
            data.get("email"),
            data.get("address"),
            data.get("guardian_name"),
            data.get("guardian_phone")
        ))
        student_id = c.lastrowid
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"success": False, "message": "roll_no conflict"}), 409

    photo_saved = False
    safe_filename = None
    if photo_b64:
        safe_filename = f"{roll}.png"
        fs_path = os.path.join(PHOTO_DIR, safe_filename)
        if os.path.exists(fs_path) or filename_exists_in_db(conn, safe_filename):
            # we leave the student row but inform user
            conn.close()
            return jsonify({"success": True, "student_id": student_id, "message": "Student created but photo filename exists - attach later"}), 201
        try:
            saved = save_base64_image(photo_b64, safe_filename)
            created_at = datetime.datetime.now().isoformat()
            c.execute("INSERT INTO photos (student_id, photo_path, filename, created_at) VALUES (?, ?, ?, ?)",
                      (student_id, saved, safe_filename, created_at))
            conn.commit()
            photo_saved = True
            if FACE_LIB_AVAILABLE:
                threading.Thread(target=compute_face_encoding_from_file, args=(saved,)).start()
        except Exception as e:
            print("photo save error:", e)

    conn.close()
    return jsonify({"success": True, "student_id": student_id, "photo_url": (f"/photos/{safe_filename}" if photo_saved else None), "message": "Student created"}), 201

@app.route("/api/upload_photo", methods=["POST"])
def api_upload_photo():
    """
    Upload an extra photo for an existing student.
    Option: reject if student already has any photo (Option A).
    Request JSON: { "student_id": 12, "photo": "<dataURL>" }
    """
    data = request.get_json() or {}
    student_id = data.get("student_id")
    photo_b64 = data.get("photo")
    if not student_id or not photo_b64:
        return jsonify({"success": False, "message": "student_id and photo required"}), 400

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT roll_no FROM students WHERE student_id=?", (student_id,))
    r = c.fetchone()
    if not r:
        conn.close()
        return jsonify({"success": False, "message": "student_id not found"}), 404
    roll = r[0] or str(student_id)

    # Option A: reject if student already has ANY photo
    c.execute("SELECT COUNT(*) FROM photos WHERE student_id=?", (student_id,))
    if (c.fetchone()[0] or 0) > 0:
        conn.close()
        return jsonify({"success": False, "message": "Student already has a photo - upload refused"}), 409

    ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    filename = f"{student_id}_{ts}.png"
    fs_path = os.path.join(PHOTO_DIR, filename)
    if os.path.exists(fs_path) or filename_exists_in_db(conn, filename):
        conn.close()
        return jsonify({"success": False, "message": "filename collision"}), 500

    try:
        saved = save_base64_image(photo_b64, filename)
        created_at = datetime.datetime.now().isoformat()
        c.execute("INSERT INTO photos (student_id, photo_path, filename, created_at) VALUES (?, ?, ?, ?)",
                  (student_id, saved, filename, created_at))
        conn.commit()
        if FACE_LIB_AVAILABLE:
            threading.Thread(target=compute_face_encoding_from_file, args=(saved,)).start()
        conn.close()
        return jsonify({"success": True, "photo_url": f"/photos/{filename}", "message": "Photo uploaded"}), 201
    except Exception as e:
        conn.close()
        return jsonify({"success": False, "message": f"Error saving photo: {e}"}), 500

@app.route("/api/replace_photo", methods=["POST"])
def api_replace_photo():
    """
    Replace existing photos for a student with provided photo.
    Request JSON: { "student_id": 12, "photo": "<dataURL>" }
    """
    data = request.get_json() or {}
    student_id = data.get("student_id")
    photo_b64 = data.get("photo")
    if not student_id or not photo_b64:
        return jsonify({"success": False, "message": "student_id and photo required"}), 400

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT roll_no FROM students WHERE student_id=?", (student_id,))
    r = c.fetchone()
    if not r:
        conn.close()
        return jsonify({"success": False, "message": "student_id not found"}), 404

    # delete existing files & rows
    c.execute("SELECT photo_path FROM photos WHERE student_id=?", (student_id,))
    old = c.fetchall()
    for (p,) in old:
        try:
            if p and os.path.exists(p):
                os.remove(p)
        except Exception:
            pass
    c.execute("DELETE FROM photos WHERE student_id=?", (student_id,))
    conn.commit()

    ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    filename = f"{student_id}_{ts}.png"
    try:
        saved = save_base64_image(photo_b64, filename)
        created_at = datetime.datetime.now().isoformat()
        c.execute("INSERT INTO photos (student_id, photo_path, filename, created_at) VALUES (?, ?, ?, ?)",
                  (student_id, saved, filename, created_at))
        conn.commit()
        if FACE_LIB_AVAILABLE:
            threading.Thread(target=compute_face_encoding_from_file, args=(saved,)).start()
        conn.close()
        return jsonify({"success": True, "photo_url": f"/photos/{filename}", "message": "Photo replaced"}), 200
    except Exception as e:
        conn.close()
        return jsonify({"success": False, "message": f"Error saving replacement photo: {e}"}), 500

@app.route("/api/get_students", methods=["GET"])
def api_get_students():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM students ORDER BY student_id DESC")
    rows = c.fetchall()
    students = []
    for row in rows:
        sid = row[0]
        c.execute("SELECT filename FROM photos WHERE student_id=? ORDER BY id LIMIT 1", (sid,))
        p = c.fetchone()
        photo_url = f"/photos/{p[0]}" if p and p[0] else None
        students.append({
            "student_id": sid,
            "roll_no": row[1],
            "name": row[2],
            "gender": row[3],
            "dob": row[4],
            "department": row[5],
            "year": row[6],
            "semester": row[7],
            "class_div": row[8],
            "phone": row[9],
            "email": row[10],
            "address": row[11],
            "guardian_name": row[12],
            "guardian_phone": row[13],
            "photo_path": photo_url
        })
    conn.close()
    return jsonify(students)

@app.route("/api/update_student/<int:student_id>", methods=["PUT"])
def api_update_student(student_id):
    data = request.get_json() or {}
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("""
            UPDATE students SET roll_no=?, name=?, gender=?, dob=?, department=?, year=?, semester=?,
                class_div=?, phone=?, email=?, address=?, guardian_name=?, guardian_phone=?
            WHERE student_id=?
        """, (
            data.get("roll_no"),
            data.get("name"),
            data.get("gender"),
            data.get("dob"),
            data.get("department"),
            data.get("year"),
            data.get("semester"),
            data.get("class_div"),
            data.get("phone"),
            data.get("email"),
            data.get("address"),
            data.get("guardian_name"),
            data.get("guardian_phone"),
            student_id
        ))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"success": False, "message": "roll_no conflict"}), 409
    conn.close()
    return jsonify({"success": True, "message": "Student updated"})

@app.route("/api/delete_student/<int:student_id>", methods=["DELETE"])
def api_delete_student(student_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT photo_path FROM photos WHERE student_id=?", (student_id,))
    rows = c.fetchall()
    for (path,) in rows:
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except Exception:
            pass
    c.execute("DELETE FROM photos WHERE student_id=?", (student_id,))
    c.execute("DELETE FROM attendance WHERE student_id=?", (student_id,))
    c.execute("DELETE FROM students WHERE student_id=?", (student_id,))
    conn.commit()
    conn.close()

    # clear encoding cache
    with ENCODING_CACHE_LOCK:
        for k in list(ENCODING_CACHE.keys()):
            if f"{os.sep}{student_id}_" in k or f"{student_id}." in k or f"{student_id}_" in k:
                ENCODING_CACHE.pop(k, None)

    return jsonify({"success": True, "message": "Deleted"})

# -----------------------
# API: Attendance (face match) with motion-based liveness (Option C)
# -----------------------
@app.route("/api/mark_attendance", methods=["POST"])
def api_mark_attendance():
    """
    Accepts JSON:
      - Either { "image": "<dataURL or base64>" }  -> single image (no liveness check performed)
      - Or    { "frames": ["<dataURL>", "<dataURL>", ...] } -> multiple frames for motion-check (recommended)
    Motion-check: server computes pixel differences between consecutive frames.
    If motion detected -> proceed to face recognition.
    If no motion -> reject (403) as likely spoof.
    """
    if not FACE_LIB_AVAILABLE:
        return jsonify({"success": False, "message": "face_recognition / numpy not available on server"}), 500

    data = request.get_json() or {}
    frames = data.get("frames")   # list of dataURL/base64 strings
    image_single = data.get("image")

    liveness_checked = False
    is_live = False

    # prefer frames-based motion check if frames provided
    if frames and isinstance(frames, list) and len(frames) >= 2:
        try:
            is_live = frames_have_motion(frames)
            liveness_checked = True
            if not is_live:
                return jsonify({"success": False, "message": "No motion detected — likely spoof (Option C)"}), 403
            # build a PIL image from middle frame for face matching
            mid = frames[len(frames)//2]
            if "," in mid:
                mid = mid.split(",", 1)[1]
            img_bytes = base64.b64decode(mid)
            pil_img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        except Exception as e:
            return jsonify({"success": False, "message": f"Motion/liveness check failed: {e}"}), 500
    elif image_single:
        # single image posted - cannot run motion-liveness; proceed (but mark not-checked)
        try:
            b64 = image_single.split(",",1)[1] if "," in image_single else image_single
            img_bytes = base64.b64decode(b64)
            pil_img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            liveness_checked = False
        except Exception as e:
            return jsonify({"success": False, "message": f"Failed to decode image: {e}"}), 400
    else:
        return jsonify({"success": False, "message": "Provide 'frames' (recommended) or 'image'"}), 400

    # compute encodings for faces in submitted image
    unknown_encs = compute_face_encodings_from_pil(pil_img)
    if not unknown_encs:
        return jsonify({"success": True, "matched": [], "message": "No faces found"})

    # load all photos from DB and compute / fetch encodings
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, student_id, photo_path FROM photos")
    photos = c.fetchall()
    conn.close()

    known_encodings = []
    known_meta = []
    for pid, sid, ppath in photos:
        enc = compute_face_encoding_from_file(ppath)
        if enc is not None:
            known_encodings.append(enc)
            known_meta.append((pid, sid, ppath))

    matches = []
    for unk in unknown_encs:
        if len(known_encodings) == 0:
            continue
        distances = face_recognition.face_distance(known_encodings, unk)
        best_idx = int(np.argmin(distances))
        best_distance = float(distances[best_idx])
        # threshold (0.5 typical; tune as needed)
        if best_distance < 0.50:
            pid, sid, ppath = known_meta[best_idx]
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT name, roll_no FROM students WHERE student_id=?", (sid,))
            r = c.fetchone()
            conn.close()
            name = r[0] if r else "Unknown"
            roll_no = r[1] if r else "-"
            # insert attendance
            now = datetime.datetime.now()
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("INSERT INTO attendance (student_id, date, time_in, status, created_at) VALUES (?, ?, ?, ?, ?)",
                      (sid, now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), "present", now.isoformat()))
            conn.commit()
            conn.close()

            matches.append({'student_id': sid, 'name': name, 'roll_no': roll_no, 'photo_path': ppath, 'distance': best_distance})

    return jsonify({"success": True, "matched": matches, "liveness_checked": liveness_checked})

@app.route("/api/get_attendance", methods=["GET"])
def api_get_attendance():
    today = datetime.datetime.now().strftime("%Y-%m-%d")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT a.id, a.student_id, s.name, s.roll_no,
               a.date, a.time_in, a.status, a.created_at
        FROM attendance a
        LEFT JOIN students s ON a.student_id = s.student_id
        WHERE a.date = ?
        ORDER BY a.time_in DESC
    """, (today,))
    rows = c.fetchall()
    conn.close()

    records = []
    for r in rows:
        records.append({
            "id": r[0],
            "student_id": r[1],
            "name": r[2],
            "roll_no": r[3],
            "date": r[4],
            "time_in": r[5],
            "status": r[6],
            "created_at": r[7]
        })
    return jsonify(records)


@app.route("/export_csv")
def export_csv():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        SELECT s.roll_no, s.name, a.date, a.time_in, a.status
        FROM attendance a
        LEFT JOIN students s ON a.student_id = s.student_id
        ORDER BY a.date DESC, a.time_in DESC
    """)
    rows = c.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)

    # CSV Header
    writer.writerow(["Roll No", "Name", "Date", "Time In", "Status"])

    # CSV Rows
    for row in rows:
        writer.writerow(row)

    response = Response(
        output.getvalue(),
        mimetype="text/csv"
    )
    response.headers["Content-Disposition"] = "attachment; filename=attendance.csv"

    return response


# -----------------------
# Run
# -----------------------
if __name__ == "__main__":
    print("Starting app. FACE_LIB_AVAILABLE =", FACE_LIB_AVAILABLE)
    print("Photo dir:", PHOTO_DIR)
    app.run(debug=True)
