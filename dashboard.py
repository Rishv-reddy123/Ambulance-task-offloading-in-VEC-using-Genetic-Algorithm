from flask import Flask, render_template, request, jsonify
import requests

app = Flask(__name__)

# Home page with input form
@app.route("/", methods=["GET", "POST"])
def home():
    hospital_data = None
    if request.method == "POST":
        lat = float(request.form["latitude"])
        lon = float(request.form["longitude"])
        condition = request.form["condition"]

        # Call your API
        url = "http://127.0.0.1:5000/nearest_hospital"
        payload = {"latitude": lat, "longitude": lon, "condition": condition}
        res = requests.post(url, json=payload)

        if res.status_code == 200:
            hospital_data = res.json()
        else:
            hospital_data = {"error": "No hospital found"}

    return render_template("dashboard.html", hospital=hospital_data)

if __name__ == "__main__":
    app.run(port=5001, debug=True)
