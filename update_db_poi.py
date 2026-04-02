# update_db_poi.py
import sqlite3

hospitals = [
    {'poi_id':'hosmat',   'name':'Hosmat Hospital',               'lat':12.9715, 'lon':77.6191, 'type':'Private',   'capacity':150, 'availability':40, 'contact':'080-11111111', 'specialization':'Orthopedic, Trauma', 'level':'critical'},
    {'poi_id':'stmarthas','name':"St. Martha's Hospital",         'lat':12.9609, 'lon':77.5957, 'type':'Private',   'capacity':120, 'availability':30, 'contact':'080-22222222', 'specialization':'General, Emergency', 'level':'medium'},
    {'poi_id':'bowring',  'name':'Bowring & Lady Curzon Hospital','lat':12.9834, 'lon':77.6056, 'type':'Government','capacity':200, 'availability':50, 'contact':'080-33333333', 'specialization':'Trauma, General', 'level':'critical'},
    {'poi_id':'mallya',   'name':'Mallya Hospital',               'lat':12.9716, 'lon':77.5993, 'type':'Private',   'capacity':180, 'availability':35, 'contact':'080-44444444', 'specialization':'Cardiac, General', 'level':'medium'},
    {'poi_id':'manipal',  'name':'Manipal Hospital (Old Airport Rd)','lat':12.9601, 'lon':77.6480, 'type':'Private', 'capacity':300, 'availability':60, 'contact':'080-55555555', 'specialization':'Multi-specialty', 'level':'critical'}
]

conn = sqlite3.connect("hospitals.db")
cur = conn.cursor()

# ensure hospitals table exists
cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='hospitals'")
if not cur.fetchone():
    raise SystemExit("ERROR: 'hospitals' table not found in hospitals.db. Run init_db.py first.")

# add poi_id column if missing
cur.execute("PRAGMA table_info(hospitals)")
cols = [row[1] for row in cur.fetchall()]
if 'poi_id' not in cols:
    cur.execute("ALTER TABLE hospitals ADD COLUMN poi_id TEXT;")
    print("Added column: poi_id")

added = 0
updated = 0

for h in hospitals:
    cur.execute("SELECT hospital_id FROM hospitals WHERE name = ?", (h['name'],))
    row = cur.fetchone()
    if row:
        cur.execute("""
            UPDATE hospitals SET latitude=?, longitude=?, type=?, capacity=?, availability=?, contact_number=?, specialization=?, level=?, poi_id=?
            WHERE name=?""",
            (h['lat'], h['lon'], h['type'], h['capacity'], h['availability'], h['contact'], h['specialization'], h['level'], h['poi_id'], h['name'])
        )
        updated += 1
    else:
        cur.execute("""
            INSERT INTO hospitals (name, latitude, longitude, type, capacity, availability, contact_number, specialization, level, poi_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (h['name'], h['lat'], h['lon'], h['type'], h['capacity'], h['availability'], h['contact'], h['specialization'], h['level'], h['poi_id'])
        )
        added += 1

conn.commit()
print(f"Done. Added: {added}, Updated: {updated}")
conn.close()
