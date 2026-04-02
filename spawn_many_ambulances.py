import traci
import traci.constants as tc
import random

# Connect to SUMO (make sure you start sumo-gui with --remote-port 8813)
traci.init(8813)

# First, define an ambulance type so SUMO knows it
traci.vehicletype.copy("DEFAULT_VEHTYPE", "ambulanceType")
traci.vehicletype.setColor("ambulanceType", (255, 0, 0, 255))  # red
traci.vehicletype.copy("DEFAULT_VEHTYPE", "ambulanceType")
traci.vehicletype.setColor("ambulanceType", (255, 0, 0, 255))

traci.vehicletype.setParameter("ambulanceType", "has.bluelight.device", "true")
traci.vehicletype.setParameter("ambulanceType", "has.siren.device", "true")

# Example edges you gave me
ambulance_edges = [
    "549187830",        # from=431524048 to=428847118
    "544759837#0",      # from=11854316017 to=11283487998
    "1347077897#0"      # from=12460840975 to=61748543
]

# Spawn 5 ambulances
for i in range(5):
    edge = random.choice(ambulance_edges)
    veh_id = f"ambulance_{i}"
    try:
        # Create a simple one-edge route for the ambulance
        route_id = f"route_{veh_id}"
        traci.route.add(route_id, [edge])

        # Add the ambulance vehicle
        traci.vehicle.add(
            veh_id,
            routeID=route_id,
            typeID="ambulanceType",
            depart=str(10 + i * 5)  # stagger departures
        )
        print(f"Spawned {veh_id} at edge {edge}")
    except Exception as e:
        print(f"Error spawning {veh_id}: {e}")

# Run simulation for 200 steps
for step in range(200):
    traci.simulationStep()

traci.close()
