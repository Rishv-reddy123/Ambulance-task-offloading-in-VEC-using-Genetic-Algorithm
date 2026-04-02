import traci
import math
import csv
import os
from sumolib import net  # Added for edge mapping

# ----------------- CONFIG -----------------
SUMO_CONFIG = "mgroad.sumocfg"       # path to your SUMO config file
NET_FILE = "bangalore_mgroad.net.xml"          # path to your SUMO network file
RSU_RANGE = 50                        # meters, RSU detection range
CSV_FILE = "ambulance_tasks.csv"
SIM_STEPS = 500
TASK_PROCESS_TIME = 5                 # simulation steps for RSU to complete task
# ------------------------------------------

# Load SUMO network
sumo_net = net.readNet(NET_FILE)

# Function to calculate Euclidean distance
def distance(p1, p2):
    return math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)

# Remove previous CSV if exists
if os.path.exists(CSV_FILE):
    os.remove(CSV_FILE)

# Open CSV for logging
csv_file = open(CSV_FILE, mode='w', newline='')
csv_writer = csv.DictWriter(csv_file, fieldnames=['step','ambulance_id','x','y','nearest_rsu','task_status','hospital'])
csv_writer.writeheader()

# Start SUMO
traci.start(["sumo-gui", "-c", SUMO_CONFIG])

# Get RSUs (traffic lights)
rsus = traci.trafficlight.getIDList()
print("RSUs found:", rsus)

# Load hospitals
hospital_ids = traci.poi.getIDList()
hospital_positions = {h: traci.poi.getPosition(h) for h in hospital_ids}

# Example hospital info: beds and doctors
hospitals = {
    h: {'position': hospital_positions[h], 'beds': 5, 'doctors': ['trauma','cardiology']} for h in hospital_ids
}

# Task and RSU queues
tasks = {}
rsu_queue = {rsu: [] for rsu in rsus}

# ----------------- SIMULATION LOOP -----------------
for step in range(SIM_STEPS):
    traci.simulationStep()
    vehicles = traci.vehicle.getIDList()

    for veh in vehicles:
        if "ambulance" in veh:
            # Force ambulance to max speed
            traci.vehicle.setSpeed(veh, traci.vehicle.getMaxSpeed(veh))
            x, y = traci.vehicle.getPosition(veh)

            # ---- NEAREST RSU TASK OFFLOAD ----
            nearest_rsu = None
            min_dist = float("inf")
            for rsu in rsus:
                rsu_x, rsu_y = traci.junction.getPosition(rsu)
                d = distance((x,y),(rsu_x,rsu_y))
                if d < min_dist:
                    min_dist = d
                    nearest_rsu = rsu

            task_status = "not in range"
            if nearest_rsu and min_dist <= RSU_RANGE:
                task_id = f"{veh}_{nearest_rsu}"
                if task_id not in tasks:
                    tasks[task_id] = {'ambulance': veh, 'rsu': nearest_rsu, 'status':'offloaded', 'remaining_steps': TASK_PROCESS_TIME}
                    rsu_queue[nearest_rsu].append(task_id)
                    task_status = "offloaded"
                else:
                    task_status = tasks[task_id]['status']

                # ---- PRIORITIZE TRAFFIC LIGHT ----
                traci.trafficlight.setPhase(nearest_rsu, 0)  # 0=green for main road

            # ---- HOSPITAL SELECTION ----
            patient_severity = "critical"
            selected_hospital = min(hospitals.keys(), key=lambda h: distance((x,y), hospitals[h]['position']))
            hospital_pos = hospitals[selected_hospital]['position']
            nearest_edges = sumo_net.getNeighboringEdges(hospital_pos[0], hospital_pos[1], radius=50)

            if nearest_edges:
                best_edge = nearest_edges[0][0].getID()
                traci.vehicle.changeTarget(veh, best_edge)
            else:
                print(f"No valid edge found near hospital {selected_hospital}")

            # ---- COLOR AMBULANCE BASED ON TASK ----
            color_map = {
                "not in range": (128,128,128),
                "offloaded": (255,255,0),
                "processing": (255,165,0),
                "completed": (0,255,0)
            }
            if task_status in ["offloaded","processing"]:
                tasks[task_id]['status'] = 'processing'
            traci.vehicle.setColor(veh, color_map.get(task_status,(255,0,0)))

            # ---- LOG TO CSV ----
            csv_writer.writerow({
                'step': step,
                'ambulance_id': veh,
                'x': round(x,2),
                'y': round(y,2),
                'nearest_rsu': nearest_rsu if nearest_rsu else "None",
                'task_status': task_status,
                'hospital': selected_hospital
            })

    # ---- PROCESS RSU TASKS ----
    for rsu, queue in rsu_queue.items():
        for task_id in queue[:]:
            task = tasks[task_id]
            if task['status'] in ['offloaded','processing']:
                task['status'] = 'processing'
                task['remaining_steps'] -= 1
                if task['remaining_steps'] <= 0:
                    task['status'] = 'completed'
                    queue.remove(task_id)

# ----------------- END SIMULATION -----------------
traci.close()
csv_file.close()
print(f"Simulation finished. CSV saved at {CSV_FILE}")