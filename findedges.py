import sumolib

net = sumolib.net.readNet("bangalore_mgroad.net.xml")

edges_to_check = [
    "638531681#5",
    "1168178847#2",
    "-1168178847#2",
    "-1168178845#1",
    "-169711263#3",
    "-112657837#0"
]

for e in edges_to_check:
    try:
        edge = net.getEdge(e)
        print(f"\nOutgoing edges from {e}:")
        outs = edge.getOutgoing()
        if not outs:
            print("  ❌ No outgoing edges (dead end)")
        else:
            for o in outs:
                print("  →", o.getID())
    except:
        print(f"\n❌ Edge {e} not found!")
