import requests

res = requests.post("http://127.0.0.1:5000/nearest_hospital", json={
    "lat": 12.9716,
    "lon": 77.5946,
    "condition": "critical"
})

print("Status code:", res.status_code)
print("Raw text:", res.text)   # 🔑 see what the server actually sent
