import traci
import math

# Function to calculate distance between 2 points
def distance(p1, p2):
    return math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)

sumoCmd = ["sumo-gui", "-c", "mgroad.sumocfg"]
traci.start(sumoCmd)

# Get all traffic light IDs (these will act as RSUs)
rsus = traci.trafficlight.getIDList()
print("Traffic Light RSUs:", rsus)

# Main simulation loop
step = 0
while step < 500:
    traci.simulationStep()
    step += 1


    vehicles = traci.vehicle.getIDList()

    for veh in vehicles:
        # Check if vehicle is an ambulance
        if "ambulance" in veh:  # vehicle IDs with "ambulance" are treated as emergency
            ambu_pos = traci.vehicle.getPosition(veh)

           
            nearest_rsu = None
            min_dist = float("inf")

            for rsu in rsus:
                rsu_pos = traci.junction.getPosition(rsu)
                d = distance(ambu_pos, rsu_pos)
                if d < min_dist:
                    min_dist = d
                    nearest_rsu = rsu

            if nearest_rsu:
                print(f"Ambulance {veh} is near RSU {nearest_rsu} at distance {min_dist:.2f}")

                # RSU decision: Give ambulance priority → set traffic light to GREEN
                traci.trafficlight.setPhase(nearest_rsu, 0)  # 0 = green for main road
                print(f"RSU {nearest_rsu} switched to GREEN for ambulance {veh}")

traci.close()
