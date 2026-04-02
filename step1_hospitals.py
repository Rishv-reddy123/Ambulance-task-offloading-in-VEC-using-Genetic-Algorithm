import traci

# Path to your SUMO configuration
SUMO_CONFIG = "mgroad.sumocfg"

# Start SUMO with GUI
traci.start(["sumo-gui", "-c", SUMO_CONFIG])

# Advance one simulation step so POIs are available
traci.simulationStep()

# Get all POIs (Points of Interest)
hospital_ids = traci.poi.getIDList()
print("Hospitals found:", hospital_ids)

# Dictionary to store hospital positions
hospital_positions = {}
for h in hospital_ids:
    pos = traci.poi.getPosition(h)
    hospital_positions[h] = pos
    print(f"Hospital {h} at position {pos}")

# Close TraCI connection
traci.close()
