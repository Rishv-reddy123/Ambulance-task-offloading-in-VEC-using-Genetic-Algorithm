import sqlite3

# 1. Connect (this will create hospitals.db if it doesn't exist)
conn = sqlite3.connect("hospitals.db")
cursor = conn.cursor()

# 2. Create table (only once)
cursor.execute('''
CREATE TABLE IF NOT EXISTS hospitals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    type TEXT,
    capacity INTEGER,
    availability INTEGER,
    contact_number TEXT,
    specialization TEXT,
    level TEXT,
    poi_id TEXT
)
''')

# 3. Insert sample hospitals
hospitals_data = [
    ("Hosmat Hospital", 12.9715, 77.6191, "Private", 150, 40, "080-11111111", "Orthopedic, Trauma", "critical", "hosmat"),
    ("St. Martha’s Hospital", 12.9609, 77.5957, "Private", 120, 30, "080-22222222", "General, Emergency", "medium", "stmarthas"),
    ("Bowring & Lady Curzon Hospital", 12.9834, 77.6056, "Government", 200, 50, "080-33333333", "Trauma, General", "critical", "bowring"),
    ("Mallya Hospital", 12.9716, 77.5993, "Private", 180, 35, "080-44444444", "Cardiac, General", "medium", "mallya"),
    ("Manipal Hospital (Old Airport Rd)", 12.9601, 77.6480, "Private", 300, 60, "080-55555555", "Multi-specialty", "critical", "manipal"),
]

cursor.executemany('''
INSERT INTO hospitals 
(name, latitude, longitude, type, capacity, availability, contact_number, specialization, level, poi_id)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
''', hospitals_data)

# 4. Commit and close
conn.commit()
conn.close()

print("✅ Database hospitals.db created and hospitals inserted successfully.")
