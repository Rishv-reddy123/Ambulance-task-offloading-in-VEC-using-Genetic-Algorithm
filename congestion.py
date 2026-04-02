import traci
import math
import csv
import os
import random

# ----------------- CONFIG -----------------
SUMO_CONFIG = "mgroad.sumocfg"
RSU_RANGE = 50        # meters
CSV_FILE = "ambulance_tasks.csv"
SIM_STEPS = 1000
TASK_PROCESS_TIME = 5

# ----------------- HELPER FUNCTIONS -----------------
def distance(p1, p2):
    return math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)

# ---------- DYNAMIC CONGESTION CALCULATION ----------
def get_congestion(edge_id):
    """Calculate congestion on the given edge using live SUMO data."""
    try:
        veh_count = traci.edge.getLastStepVehicleNumber(edge_id)
        mean_speed = traci.edge.getLastStepMeanSpeed(edge_id)
        lanes = traci.edge.getLaneNumber(edge_id)
        length = traci.lane.getLength(f"{edge_id}_0") if lanes > 0 else 100
        max_speed = traci.lane.getMaxSpeed(f"{edge_id}_0") if lanes > 0 else 13.9  # default 50 km/h

        if max_speed == 0 or length == 0:
            return 0.0

        # Calculate density (#vehicles per 100m)
        density = veh_count / (length / 100.0)
        speed_ratio = mean_speed / max_speed

        # Weighted congestion factor between 0 and 1
        congestion_factor = min(1.0, max(0.0, (1 - speed_ratio) + (0.1 * density)))
        return congestion_factor

    except Exception:
        return 0.0

# ----------------- FITNESS FUNCTION -----------------
def fitness_function(dist, beds, specialization_match, congestion):
    """
    Multi-objective fitness combining:
    - Distance/time efficiency
    - Bed availability
    - Specialist match
    - Real-time congestion penalty
    """
    eta = (dist / 1000) / 50 * 60  # Estimated time at 50 km/h
    max_eta = 20
    eta_score = max(0, 1 - (eta / max_eta))
    bed_score = min(1, beds / 5)
    spec_score = 1 if specialization_match else 0
    congestion_penalty = 1 - congestion  # lower congestion → higher score

    fitness = (0.5 * eta_score) + (0.2 * bed_score) + (0.1 * spec_score) + (0.2 * congestion_penalty)
    return fitness

# ----------------- HOSPITAL DATA -----------------
hospital_positions = {
    'hosmat': (749.94, 674.95),
    'stmarthas': (349.34, 924.17),
    'bowring': (506.25, 270.55),
    'mallya': (273.17, 1590.72),
    'manipal': (1522.13, 128.08)
}

hospital_edges = {
    'hosmat': '638531681#3',
    'stmarthas': '1168178847#2',
    'bowring': '1168178845#1',
    'mallya': '169711263#3',
    'manipal': '-112657837#1'
}

hospitals = {
    'hosmat': {'position': hospital_positions['hosmat'], 'beds': 5, 'doctors': ['trauma', 'cardiology']},
    'stmarthas': {'position': hospital_positions['stmarthas'], 'beds': 3, 'doctors': ['neurology']},
    'bowring': {'position': hospital_positions['bowring'], 'beds': 2, 'doctors': ['orthopedic', 'trauma']},
    'mallya': {'position': hospital_positions['mallya'], 'beds': 4, 'doctors': ['cardiology']},
    'manipal': {'position': hospital_positions['manipal'], 'beds': 6, 'doctors': ['trauma', 'neurology']}
}

# ----------------- PATIENT DATA -----------------
patients = {
    "ambulance_501": {"severity": "critical", "required_specialist": "trauma"},
    "ambulance_502": {"severity": "high", "required_specialist": "cardiology"},
    "ambulance_503": {"severity": "medium", "required_specialist": "neurology"},
    "ambulance_504": {"severity": "high", "required_specialist": "orthopedic"},
    "ambulance_505": {"severity": "critical", "required_specialist": "neurology"},
}

severity_rank = {'critical': 3, 'high': 2, 'medium': 1, 'low': 0}

# ----------------- GA HOSPITAL SELECTION -----------------
def run_ga(amb_pos, patient, hospitals, locked_hospitals):
    valid_hospitals = []
    for hosp_id, hosp in hospitals.items():
        if hosp_id in locked_hospitals or patient['required_specialist'] not in hosp['doctors'] or hosp['beds'] <= 0:
            continue

        dist = distance(amb_pos, hosp['position'])
        congestion = get_congestion(hospital_edges[hosp_id])
        fitness = fitness_function(dist, hosp['beds'], True, congestion)

        valid_hospitals.append((hosp_id, fitness, dist, congestion))

    valid_hospitals.sort(key=lambda x: x[1], reverse=True)

    if valid_hospitals:
        nearest_for_print = [(h[0], round(h[1],3), round(h[3],2)) for h in valid_hospitals[:2]]
        print(f"    🏥 Top Hospitals (by Fitness): {nearest_for_print}")
        selected_hospital = valid_hospitals[0][0]
        print(f"    ✅ Selected: {selected_hospital} | Fitness: {valid_hospitals[0][1]:.3f} | Congestion: {valid_hospitals[0][3]:.2f}")
        return selected_hospital
    else:
        print(f"    ⚠️ No suitable hospital found (full, locked, or specialization mismatch).")
        return None

# ----------------- CSV LOGGING -----------------
if os.path.exists(CSV_FILE):
    os.remove(CSV_FILE)
csv_file = open(CSV_FILE, mode='w', newline='')
csv_writer = csv.DictWriter(csv_file, fieldnames=[
    'step', 'ambulance_id', 'x', 'y', 'nearest_rsu',
    'task_status', 'target_hospital', 'patient_severity', 'required_specialist'
])
csv_writer.writeheader()

# ----------------- SUMO SIMULATION -----------------
traci.start(["sumo-gui", "-c", SUMO_CONFIG])
rsus = traci.trafficlight.getIDList()
tasks = {}
ambulance_status = {}
locked_hospitals = set()

print("\n🚦 Simulation Started...\n")

for step in range(SIM_STEPS):
    traci.simulationStep()
    ambulance_list = [v for v in traci.vehicle.getIDList() if "ambulance" in v]
    ambulance_list.sort(key=lambda v: severity_rank[patients[v]['severity']], reverse=True)

    for veh in ambulance_list:
        patient_info = patients[veh]
        x, y = traci.vehicle.getPosition(veh)

        # Nearest RSU
        nearest_rsu = None
        min_dist = float("inf")
        for rsu in rsus:
            rsu_x, rsu_y = traci.junction.getPosition(rsu)
            d = distance((x, y), (rsu_x, rsu_y))
            if d < min_dist:
                min_dist = d
                nearest_rsu = rsu

        if veh not in ambulance_status:
            ambulance_status[veh] = 'pending'

        # ----------------- TASK OFFLOADING -----------------
        if ambulance_status[veh] == 'pending' and nearest_rsu and min_dist <= RSU_RANGE:
            print(f"\n🚑 Step {step} | Ambulance: {veh}")
            print(f"    ➤ Condition: {patient_info['severity'].upper()} | Needs: {patient_info['required_specialist']}")
            print(f"    📍 Position: ({x:.2f}, {y:.2f}) | Nearest RSU: {nearest_rsu}")

            best_hospital = run_ga((x, y), patient_info, hospitals, locked_hospitals)
            if best_hospital:
                hospitals[best_hospital]['beds'] -= 1
                locked_hospitals.add(best_hospital)
                task_id = f"{veh}_{best_hospital}"
                tasks[task_id] = {'ambulance': veh, 'hospital': best_hospital, 'status': 'offloaded'}
                ambulance_status[veh] = 'offloaded'

                dist_km = distance((x, y), hospitals[best_hospital]['position']) / 1000
                normal_eta = (dist_km / 30) * 60
                ga_eta = (dist_km / 50) * 60
                print(f"    ⏱️ Normal ETA: {normal_eta:.1f} min | ⚡ GA ETA: {ga_eta:.1f} min | ⬇ Saved: {normal_eta - ga_eta:.1f} min")

                try:
                    traci.vehicle.changeTarget(veh, hospital_edges[best_hospital])
                except:
                    pass

        # Check Arrival
        for task_id, task in list(tasks.items()):
            if task['ambulance'] == veh and ambulance_status[veh] == 'offloaded':
                current_edge = traci.vehicle.getRoadID(veh)
                if current_edge == hospital_edges[task['hospital']]:
                    ambulance_status[veh] = 'completed'
                    locked_hospitals.discard(task['hospital'])
                    traci.vehicle.setColor(veh, (255, 255, 255))
                    print(f"\n✅ {veh} reached hospital {task['hospital']}.")

        # Color Update
        if ambulance_status[veh] == 'pending':
            sev = patient_info['severity']
            if sev == 'critical':
                traci.vehicle.setColor(veh, (255, 0, 0))
            elif sev == 'high':
                traci.vehicle.setColor(veh, (255, 165, 0))
            elif sev == 'medium':
                traci.vehicle.setColor(veh, (255, 255, 0))
        elif ambulance_status[veh] == 'offloaded':
            traci.vehicle.setColor(veh, (0, 255, 0))
        elif ambulance_status[veh] == 'completed':
            traci.vehicle.setColor(veh, (255, 255, 255))

        # CSV Logging
        assigned_hosp = "None"
        for t in tasks.values():
            if t['ambulance'] == veh:
                assigned_hosp = t['hospital']
        csv_writer.writerow({
            'step': step,
            'ambulance_id': veh,
            'x': round(x, 2),
            'y': round(y, 2),
            'nearest_rsu': nearest_rsu if nearest_rsu else "None",
            'task_status': ambulance_status[veh],
            'target_hospital': assigned_hosp,
            'patient_severity': patient_info['severity'],
            'required_specialist': patient_info['required_specialist']
        })

# ----------------- END OF SIMULATION -----------------
traci.close()
csv_file.close()

print(f"\n✅ Simulation finished. Task log saved to '{CSV_FILE}'")
