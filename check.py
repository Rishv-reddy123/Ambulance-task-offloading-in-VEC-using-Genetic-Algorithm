import sumolib

# Load your SUMO network
net = sumolib.net.readNet("bangalore_mgroad.net.xml")

# Ambulance start edges
ambulance_starts = [
    "603115729#1",   # ambulance_501
    "705674505#1",   # ambulance_502
    "727741259",     # ambulance_503
    "48166762#1",    # ambulance_504
    "38772806#0"     # ambulance_505
]

# Hospital destination edges
hospital_edges = {
    "hosmat": "638531681#3",
    "stmarthas": "1168178847#2",
    "bowring": "1168178845#1",
    "mallya": "169711263#3",
    "manipal": "1167882452"
}

print("Checking connectivity between ambulances and hospitals...\n")

for amb_edge in ambulance_starts:
    print(f"Ambulance start edge {amb_edge} can reach hospitals:")
    reachable = False
    for hosp, hosp_edge in hospital_edges.items():
        start = net.getEdge(amb_edge)
        dest = net.getEdge(hosp_edge)

        path = net.getShortestPath(start, dest)
        if path[0] is not None:
            print(f"  ✅ {hosp} (via {len(path[0])} edges)")
            reachable = True
        else:
            print(f"  ❌ {hosp} (not connected)")
    if not reachable:
        print("  ⚠ No hospital reachable from this start edge")
    print()
