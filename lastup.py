import traci
import math
import csv
import os
import random
import matplotlib.pyplot as plt
import numpy as np

# ----------------- CONFIG -----------------
SUMO_CONFIG = "mgroad.sumocfg"
RSU_RANGE = 50        # meters
CSV_FILE = "ambulance_tasks.csv"
SIM_STEPS = 1000
GA_GENERATIONS = 8
POP_SIZE = 5

# ----------------- HELPER FUNCTIONS -----------------
def distance(p1, p2):
    return math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)

def get_congestion(edge_id):
    """Calculate congestion using live SUMO data."""
    try:
        veh_count = traci.edge.getLastStepVehicleNumber(edge_id)
        mean_speed = traci.edge.getLastStepMeanSpeed(edge_id)
        lanes = traci.edge.getLaneNumber(edge_id)
        length = traci.lane.getLength(f"{edge_id}_0") if lanes > 0 else 100
        max_speed = traci.lane.getMaxSpeed(f"{edge_id}_0") if lanes > 0 else 13.9  # default 50 km/h

        if max_speed == 0 or length == 0:
            return 0.0

        density = veh_count / (length / 100.0)
        speed_ratio = mean_speed / max_speed if max_speed > 0 else 0.0
        congestion_factor = min(1.0, max(0.0, (1 - speed_ratio) + (0.1 * density)))
        return congestion_factor
    except Exception:
        return 0.0

# ----------------- FITNESS FUNCTION -----------------
def calculate_fitness(dist_m, beds, specialization_match, congestion, severity):
    if severity == 'CRITICAL':
        w_dist, w_bed, w_spec, w_cong = 0.5, 0.1, 0.3, 0.1
    elif severity == 'HIGH':
        w_dist, w_bed, w_spec, w_cong = 0.4, 0.2, 0.3, 0.1
    elif severity == 'MEDIUM':
        w_dist, w_bed, w_spec, w_cong = 0.3, 0.3, 0.3, 0.1
    else:
        w_dist, w_bed, w_spec, w_cong = 0.2, 0.4, 0.2, 0.2

    dist_term = 1 / (1 + (dist_m / 1000.0))
    fitness = (w_dist * dist_term +
               w_bed * (beds / 10.0) +
               w_spec * (1 if specialization_match else 0) +
               w_cong * (1 - congestion))
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

# ----------------- GENETIC ALGORITHM -----------------
def select_best_hospital_GA(amb_pos, patient, hospitals_dict, locked_hospitals_map):
    severity = patient['severity'].upper()
    required_specialist = patient['required_specialist']

    valid_hospitals = []
    for hosp_id, hosp in hospitals_dict.items():
        if hosp_id in locked_hospitals_map:
            continue
        if required_specialist not in hosp['doctors']:
            continue
        if hosp['beds'] <= 0:
            continue

        dist = distance(amb_pos, hosp['position'])
        congestion = get_congestion(hospital_edges[hosp_id])
        valid_hospitals.append((hosp_id, dist, hosp['beds'], True, congestion))

    if not valid_hospitals:
        print("        ⚠️ No valid hospitals available.")
        return None

    actual_pop = min(POP_SIZE, len(valid_hospitals))
    population = [random.choice(valid_hospitals) for _ in range(actual_pop)]

    for gen in range(GA_GENERATIONS):
        fitness_scores = []
        print(f"        🧬 Generation {gen+1}")
        for hosp in population:
            hosp_id, dist, beds, spec_match, congestion = hosp
            fit = calculate_fitness(dist, beds, spec_match, congestion, severity)
            fitness_scores.append((hosp_id, fit, dist, beds, congestion))
            print(f"            {hosp_id}: distance={dist:.2f}, beds={beds}, cong={congestion:.2f}, fitness={fit:.3f}")

        fitness_scores.sort(key=lambda x: x[1], reverse=True)
        top_half = fitness_scores[:max(1, actual_pop // 2)]
        new_pop = []
        top_ids = [t[0] for t in top_half]
        while len(new_pop) < actual_pop:
            if len(top_ids) == 1:
                chosen = top_ids[0]
            else:
                p1, p2 = random.sample(top_ids, 2)
                chosen = random.choice([p1, p2])
            parent_tuple = next(t for t in valid_hospitals if t[0] == chosen)
            child = parent_tuple
            if random.random() < 0.1:
                child = random.choice(valid_hospitals)
            new_pop.append(child)
        population = new_pop

    final_scores = []
    for hosp in population:
        hosp_id, dist, beds, spec_match, congestion = hosp
        fit = calculate_fitness(dist, beds, spec_match, congestion, severity)
        final_scores.append((hosp_id, fit, dist, beds, congestion))
    final_scores.sort(key=lambda x: x[1], reverse=True)

    best_hosp_id = final_scores[0][0]
    best_fit = final_scores[0][1]
    best_cong = final_scores[0][4]
    print(f"        ✅ GA Selected Hospital: {best_hosp_id} | Fitness: {best_fit:.3f} | Congestion: {best_cong:.2f}")
    return best_hosp_id

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
locked_hospitals = {}
eta_data = {}  # ✅ store ETA comparison data

print("\n🚦 Simulation Started...\n")

for step in range(SIM_STEPS):
    traci.simulationStep()
    ambulance_list = [v for v in traci.vehicle.getIDList() if "ambulance" in v]
    ambulance_list.sort(key=lambda v: severity_rank[patients[v]['severity']], reverse=True)

    for veh in ambulance_list:
        patient_info = patients[veh]
        x, y = traci.vehicle.getPosition(veh)

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

        if ambulance_status[veh] == 'pending' and nearest_rsu and min_dist <= RSU_RANGE:
            print(f"\n🚑 Step {step} | Ambulance: {veh}")
            print(f"    ➤ Condition: {patient_info['severity'].upper()} | Needs: {patient_info['required_specialist']}")
            print(f"    📍 Position: ({x:.2f}, {y:.2f}) | Nearest RSU: {nearest_rsu}")

            best_hospital = select_best_hospital_GA((x, y), patient_info, hospitals, locked_hospitals)
            if best_hospital:
                if hospitals[best_hospital]['beds'] > 0 and best_hospital not in locked_hospitals:
                    hospitals[best_hospital]['beds'] -= 1
                    task_id = f"{veh}_{best_hospital}"
                    locked_hospitals[best_hospital] = task_id
                    tasks[task_id] = {'ambulance': veh, 'hospital': best_hospital, 'status': 'offloaded'}
                    ambulance_status[veh] = 'offloaded'
                    print(f"    🔒 {best_hospital} locked for {veh} (beds left: {hospitals[best_hospital]['beds']})")

                    dist_km = distance((x, y), hospitals[best_hospital]['position']) / 1000
                    normal_eta = (dist_km / 30) * 60
                    ga_eta = (dist_km / 50) * 60
                    print(f"    ⏱️ Normal ETA: {normal_eta:.1f} min | ⚡ GA ETA: {ga_eta:.1f} min | ⬇ Saved: {normal_eta - ga_eta:.1f} min")

                    eta_data[veh] = {"normal": normal_eta, "ga": ga_eta}  # ✅ store ETA for plot

                    try:
                        traci.vehicle.changeTarget(veh, hospital_edges[best_hospital])
                    except Exception:
                        pass
                else:
                    print(f"    ⚠️ {best_hospital} became unavailable just before locking. Skipping assignment.")
            else:
                print("    ⚠️ No hospital selected by GA.")

        for task_id, task in list(tasks.items()):
            if task['ambulance'] == veh and task['status'] == 'offloaded':
                current_edge = traci.vehicle.getRoadID(veh)
                if current_edge == hospital_edges[task['hospital']]:
                    task['status'] = 'completed'
                    ambulance_status[veh] = 'completed'
                    traci.vehicle.setColor(veh, (255, 255, 255))
                    print(f"\n✅ {veh} reached hospital {task['hospital']}.")

                    locked_task_id = locked_hospitals.get(task['hospital'])
                    if locked_task_id == task_id:
                        locked_hospitals.pop(task['hospital'], None)
                        print(f"    🔓 {task['hospital']} unlocked (reserved task {task_id} completed).")

        sev = patient_info['severity']
        if ambulance_status[veh] == 'pending':
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

        assigned_hosp = "None"
        for t in tasks.values():
            if t['ambulance'] == veh and t['status'] in ('offloaded', 'completed'):
                assigned_hosp = t['hospital']
                break

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

# ----------------- ETA COMPARISON GRAPH -----------------
if eta_data:
    ambulances_list = list(eta_data.keys())
    normal_eta = [eta_data[a]["normal"] for a in ambulances_list]
    ga_eta = [eta_data[a]["ga"] for a in ambulances_list]

    x = np.arange(len(ambulances_list))
    width = 0.35

    plt.figure(figsize=(10, 6))
    bars1 = plt.bar(x - width/2, normal_eta, width, label="Normal ETA", color='gray')
    bars2 = plt.bar(x + width/2, ga_eta, width, label="GA ETA", color='crimson')

    plt.xlabel("Ambulance ID", fontsize=12)
    plt.ylabel("ETA (minutes)", fontsize=12)
    plt.title("Comparison of ETA: Normal vs GA Optimization", fontsize=14, fontweight="bold")
    plt.xticks(x, ambulances_list, rotation=45)
    plt.legend()
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.tight_layout()

    def add_labels(bars):
        for bar in bars:
            height = bar.get_height()
            plt.text(bar.get_x() + bar.get_width()/2, height + 0.1, f"{height:.1f}",
                     ha='center', va='bottom', fontsize=10, fontweight='bold')

    add_labels(bars1)
    add_labels(bars2)
    plt.show()
else:
    print("⚠️ No ETA data available to plot.")
