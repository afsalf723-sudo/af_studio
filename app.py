from flask import Flask, render_template, request, redirect, url_for
from werkzeug.utils import secure_filename
from datetime import date
import csv
import os

app = Flask(__name__)

# =====================================
# SETTINGS
# =====================================

BOOKING_FILE = "bookings.csv"

UPLOAD_FOLDER = os.path.join("static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

BOOKING_FIELDS = [
    "Name",
    "Phone",
    "Service",
    "Date",
    "Time",
    "Details",
    "Status"
]

ALLOWED_TIMES = {"10:00", "12:00", "15:00", "17:00"}


# =====================================
# HELPER FUNCTIONS
# =====================================

def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def get_photos():
    return [
        filename
        for filename in sorted(os.listdir(UPLOAD_FOLDER))
        if allowed_file(filename)
        and os.path.isfile(os.path.join(UPLOAD_FOLDER, filename))
    ]


def get_bookings():
    bookings = []

    if not os.path.exists(BOOKING_FILE):
        return bookings

    with open(
        BOOKING_FILE, "r", newline="", encoding="utf-8-sig"
    ) as file:
        reader = csv.DictReader(file)

        for row in reader:
            # Support older booking files without a Status column.
            row.setdefault("Status", "Pending")
            row["Status"] = row.get("Status") or "Pending"
            bookings.append(row)

    return bookings


def save_bookings(bookings):
    with open(
        BOOKING_FILE, "w", newline="", encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(file, fieldnames=BOOKING_FIELDS)
        writer.writeheader()

        for booking in bookings:
            writer.writerow({
                field: booking.get(field, "")
                for field in BOOKING_FIELDS
            })


# =====================================
# HOME PAGE
# =====================================

@app.route("/")
def home():
    return render_template(
        "index.html",
        gallery_photos=get_photos()
    )


# =====================================
# BOOKING PAGE
# =====================================

@app.route("/booking")
def booking():
    bookings = get_bookings()
    booked_slots = []

    for item in bookings:
        status = item.get("Status", "Pending").lower()

        if status in ("pending", "accepted"):
            booked_slots.append({
                "date": item.get("Date", ""),
                "time": item.get("Time", "")
            })

    return render_template(
        "booking.html",
        booked_slots=booked_slots
    )


# =====================================
# CUSTOMER SUBMITS BOOKING
# =====================================

@app.route("/book", methods=["POST"])
def book():
    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    service = request.form.get("service", "").strip()
    booking_date = request.form.get("date", "").strip()
    booking_time = request.form.get("time", "").strip()
    details = request.form.get("details", "").strip()

    if not all([
        name, phone, service, booking_date, booking_time
    ]):
        return "Please complete all required fields.", 400

    try:
        parsed_date = date.fromisoformat(booking_date)
    except ValueError:
        return "Invalid booking date.", 400

    if parsed_date < date.today():
        return "You cannot book a date in the past.", 400

    if booking_time not in ALLOWED_TIMES:
        return "Invalid booking time.", 400

    bookings = get_bookings()

    # Pending and accepted requests reserve the selected slot.
    for item in bookings:
        status = item.get("Status", "Pending").lower()

        if (
            item.get("Date") == booking_date
            and item.get("Time") == booking_time
            and status in ("pending", "accepted")
        ):
            return """
                <!DOCTYPE html>
                <html>
                <head><title>Time Unavailable</title></head>
                <body style="background:#080808;color:white;
                             font-family:Arial;text-align:center;padding:40px;">
                    <h1 style="color:#d2b47c;">Time Unavailable</h1>
                    <p>This date and time is already reserved.</p>
                    <a style="color:#d2b47c;" href="/booking">
                        Choose another time
                    </a>
                </body>
                </html>
            """, 409

    new_booking = {
        "Name": name,
        "Phone": phone,
        "Service": service,
        "Date": booking_date,
        "Time": booking_time,
        "Details": details,
        "Status": "Pending"
    }

    bookings.append(new_booking)
    save_bookings(bookings)

    return """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport"
                  content="width=device-width, initial-scale=1.0">
            <title>Booking Received | AF Studio</title>
        </head>
        <body style="background:#080808;color:white;
                     font-family:Arial;text-align:center;padding:40px;">
            <h1 style="color:#d2b47c;">Booking Request Received!</h1>
            <p>Your request is pending confirmation from AF Studio.</p>
            <a href="/" style="color:#d2b47c;">Back to Home</a>
        </body>
        </html>
    """


# =====================================
# ADMIN: VIEW BOOKINGS
# =====================================

@app.route("/admin")
def admin():
    bookings = get_bookings()

    return render_template(
        "admin.html",
        bookings=bookings
    )


# =====================================
# ADMIN: ACCEPT OR DECLINE BOOKINGS
# =====================================

@app.route(
    "/admin/booking/<int:booking_id>/<action>",
    methods=["POST"]
)
def update_booking(booking_id, action):
    if action not in ("accept", "decline"):
        return "Invalid action.", 400

    bookings = get_bookings()

    if booking_id < 0 or booking_id >= len(bookings):
        return "Booking not found.", 404

    if action == "accept":
        selected = bookings[booking_id]
        selected_date = selected.get("Date", "")
        selected_time = selected.get("Time", "")

        # Don't accept a slot that another active booking occupies.
        for index, item in enumerate(bookings):
            if index == booking_id:
                continue

            if (
                item.get("Date") == selected_date
                and item.get("Time") == selected_time
                and item.get("Status", "Pending").lower()
                == "accepted"
            ):
                return (
                    "This time already has an accepted booking.",
                    409
                )

        bookings[booking_id]["Status"] = "Accepted"

    else:
        bookings[booking_id]["Status"] = "Declined"

    save_bookings(bookings)

    return redirect(url_for("admin"))


# =====================================
# ADMIN: PHOTO UPLOAD PAGE
# =====================================

@app.route("/admin/photos", methods=["GET", "POST"])
def manage_photos():
    if request.method == "POST":
        if "photo" not in request.files:
            return "Please select a photo.", 400

        photo = request.files["photo"]

        if not photo.filename:
            return "Please select a photo.", 400

        if not allowed_file(photo.filename):
            return "Only JPG, JPEG, PNG and WEBP photos are allowed.", 400

        filename = secure_filename(photo.filename)

        if not filename:
            return "Invalid filename.", 400

        name, extension = os.path.splitext(filename)
        counter = 1

        # Avoid overwriting a photo with the same filename.
        while os.path.exists(os.path.join(UPLOAD_FOLDER, filename)):
            filename = f"{name}_{counter}{extension}"
            counter += 1

        photo.save(os.path.join(UPLOAD_FOLDER, filename))

        return redirect(url_for("manage_photos"))

    return render_template(
        "manage_photos.html",
        photos=get_photos()
    )


# =====================================
# ADMIN: DELETE PHOTO
# =====================================

@app.route(
    "/admin/photos/delete/<filename>",
    methods=["POST"]
)
def delete_photo(filename):
    safe_filename = secure_filename(filename)

    if safe_filename != filename or not allowed_file(filename):
        return "Invalid filename.", 400

    file_path = os.path.join(UPLOAD_FOLDER, filename)

    if os.path.isfile(file_path):
        os.remove(file_path)

    return redirect(url_for("manage_photos"))


# =====================================
# RUN WEBSITE
# =====================================

if __name__ == "__main__":
    app.run(debug=True)