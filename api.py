from flask import Flask, request, jsonify
import sqlite3, math

app = Flask(__name__)

# Haversine formula for distance between two GPS points
def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

@app.route('/nearest_hospital', methods=['POST'])
def nearest_hospital():
    data = request.json
    ambulance_lat = data['lat']
    ambulance_lon = data['lon']
    condition = data['condition']  # critical / medium / low

    conn = sqlite3.connect("hospital_db.sqlite")
    cursor = conn.cursor()
    cursor.execute("SELECT name, lat, lon, contact, condition FROM hospitals")
    hospitals = cursor.fetchall()
    conn.close()

    best_hospital = None
    best_dist = float("inf")

    for name, lat, lon, contact, hosp_cond in hospitals:
        if hosp_cond.lower() == condition.lower():  # match condition
            dist = haversine(ambulance_lat, ambulance_lon, lat, lon)
            if dist < best_dist:
                best_dist = dist
                best_hospital = {
                    "name": name,
                    "lat": lat,
                    "lon": lon,
                    "contact": contact,
                    "distance_km": round(dist, 2)
                }

    return jsonify(best_hospital)


# 🔑 Start server
if __name__ == "__main__":
    app.run(debug=True)
