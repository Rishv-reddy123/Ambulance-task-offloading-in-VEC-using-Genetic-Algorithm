import sumolib
import xml.etree.ElementTree as ET

# Paths to your files
NET_FILE = "bangalore_mgroad.net.xml"
POI_FILE = "hospital.poi"

# Load the network
net = sumolib.net.readNet(NET_FILE)

# Parse POI XML
tree = ET.parse(POI_FILE)
root = tree.getroot()

# Loop over all POIs
for poi in root.findall("poi"):
    lane_id = poi.attrib['lane']
    pos = float(poi.attrib['pos'])
    
    try:
        lane = net.getLane(lane_id)
        lane_length = lane.getLength()
        if pos > lane_length:
            print(f"[WARNING] POI '{poi.attrib['id']}' has pos={pos} > lane length={lane_length:.2f}.")
            # Optionally, fix it automatically
            poi.attrib['pos'] = str(lane_length * 0.5)  # put it at the middle of the lane
            print(f"         -> Adjusted pos to {poi.attrib['pos']}")
    except KeyError:
        print(f"[ERROR] Lane '{lane_id}' not found in network.")

# Save corrected POI file
tree.write("hospital_validated.poi")
print("Validation complete. Corrected POI file saved as 'hospital_validated.poi'")
