
# merged6_final.py — PART 1: imports, config, globals, helpers

import traci
import sumolib
import random
import math
import csv
import os
import time
import numpy as np
import matplotlib.pyplot as plt
from collections import defaultdict
import heapq

# ---------------- CONFIG ----------------
SUMO_CONFIG = "mgroad.sumocfg"
NET_FILE = "bangalore_mgroad.net.xml"

SIM_STEPS = 2000           # increase if needed
TIME_STEP = 1.0            # seconds per SUMO step

LOG_FILE = "routing_log_final.txt"
TASK_CSV = "task_offloading.csv"
TASK_XLSX = "task_offloading.xlsx"
ETA_GRAPH_FILE = "eta_comparison.png"
WAITING_GRAPH_FILE = "waiting_time_pie.png"

RSU_RANGE = 50             # meters radius for RSU detection

# ACCIDENT SETTINGS
ACC_START = random.randint(200, 600)
ACC_DURATION = 200
ACC_REDUCED_SPEED = 1.0

# GA SETTINGS
GA_GENERATIONS = 8
POP_SIZE = 6
MUTATION_RATE = 0.2
K_PATHS = 4

# REROUTE SETTINGS
RE_ROUTE_CHECK_INTERVAL = 5
REROUTE_CONGESTION_THRESHOLD = 0.20
REROUTE_DELTA_THRESHOLD = 0.05
MIN_REROUTE_INTERVAL = 30
MAX_REROUTES = 20

# TRAFFIC LEVELS
BACKGROUND_COUNTS = {
    "low": 60,
    "medium": 200,
    "high": 1000
}

# ---------------- GLOBAL STRUCTURES ----------------
assigned = {}                  # amb → hospital
assigned_step = {}             # amb → step assigned (time of offload at RSU)
arrival_step = {}              # amb → step reached hospital
completed = set()

# ETA & waiting tracking (seconds)
eta_before = {}     # amb -> ETA (sec) estimated at offload
eta_after = {}      # amb -> ETA (sec) recorded at arrival (B2: traveltime or fallback)
waiting_time = defaultdict(float)   # amb -> waiting seconds accumulated
last_speed = {}     # amb -> last speed read

route_assign_meta = {}         # (amb,hosp) → metadata
last_route_congestion = {}     # amb → previous congestion
reroute_counter = {}           # amb → # reroutes
last_reroute_step = {}         # amb → step of last reroute
beds_reserved = {}             # amb → hospital reserved (locks)

_graph_cache = None            # adjacency graph
_edge_map_cache = None         # edge id → nodeFrom, nodeTo
_net = None                    # loaded SUMOLIB network

task_offloads = []             # list of dicts to write to CSV/XLSX at end
log_lines = []                 # file logs

DEBUG = True                   # show TRACI errors

# ---------------- COLOR SETTINGS ----------------
severity_colors = {
    "critical": (255, 0, 0),       # red
    "high":     (255, 165, 0),     # orange
    "medium":   (0, 128, 255)      # blue
}

OFFLOADED_COLOR = (0, 255, 0)     # green at RSU offload
ARRIVED_COLOR = (255, 255, 255)   # white at hospital arrival

# ---------------- HOSPITALS ----------------
hospital_edges = {
    'hosmat':      '638531681#3',
    'stmarthas':   '1168178847#2',
    'bowring':     '1168178845#1',
    'mallya':      '169711263#3',
    'manipal':     '-112657837#1'
}

hospitals = {
    'hosmat':     {'beds_available': 5, 'doctors': ['trauma', 'cardiology']},
    'stmarthas':  {'beds_available': 3, 'doctors': ['neurology']},
    'bowring':    {'beds_available': 2, 'doctors': ['orthopedic', 'trauma']},
    'mallya':     {'beds_available': 4, 'doctors': ['cardiology']},
    'manipal':    {'beds_available': 6, 'doctors': ['trauma', 'neurology']}
}

# ---------------- PATIENTS ----------------
patients = {
    "ambulance_501": {"severity": "critical", "required_specialist": "trauma"},
    "ambulance_502": {"severity": "high",     "required_specialist": "cardiology"},
    "ambulance_503": {"severity": "medium",   "required_specialist": "neurology"},
    "ambulance_504": {"severity": "high",     "required_specialist": "orthopedic"},
    "ambulance_505": {"severity": "critical", "required_specialist": "neurology"}
}

# ================= UTILITIES =================
def log(msg, console=True):
    if console:
        print(msg)
    log_lines.append(str(msg))

def safe_traci(func, *args, default=None, **kwargs):
    try:
        return func(*args, **kwargs)
    except Exception as e:
        if DEBUG:
            print(f"[TRACI ERROR] {e}")
        return default

def get_distance(a, b):
    try:
        return math.hypot(a[0] - b[0], a[1] - b[1])
    except Exception:
        return float("inf")

def _is_internal(edge_id):
    return edge_id is not None and str(edge_id).startswith(":")

def get_valid_start_edge(amb):
    r = safe_traci(traci.vehicle.getRoadID, amb)
    if r and not _is_internal(r):
        return r
    route = safe_traci(traci.vehicle.getRoute, amb, default=[])
    for e in (route or []):
        if not _is_internal(e):
            return e
    return None

# Robust route applier (safe_apply_route) - defined here for global use
def safe_apply_route(veh, new_edges, dest_edge=None):
    """
    Robustly apply a new route to vehicle `veh`.
    - Ensures vehicle's current edge is included in the new route (prepend if needed).
    - If current edge is internal, tries to find a valid non-internal start edge from vehicle route.
    - If setRoute fails, falls back to traci.vehicle.changeTarget(dest_edge) (if dest_edge provided).
    Returns True if route was applied or changeTarget succeeded, False otherwise.
    """
    try:
        new_edges = list(new_edges or [])
        if not new_edges:
            return False
        current = safe_traci(traci.vehicle.getRoadID, veh, default=None)
        veh_route = safe_traci(traci.vehicle.getRoute, veh, default=[]) or []
        # Case A: current in new_edges -> direct set
        if current and current in new_edges:
            try:
                traci.vehicle.setRoute(veh, new_edges)
                return True
            except Exception as e:
                log(f"[safe_apply_route] direct setRoute failed: {e}")
        # Case B: prepend current if non-internal
        candidate_edges = list(new_edges)
        if current and not str(current).startswith(":"):
            if current not in candidate_edges:
                candidate_edges = [current] + candidate_edges
            try:
                traci.vehicle.setRoute(veh, candidate_edges)
                return True
            except Exception as e:
                log(f"[safe_apply_route] prepended current edge failed: {e}")
        # Case C: use first non-internal edge from veh_route
        start_edge = None
        for e in veh_route:
            if not str(e).startswith(":"):
                start_edge = e
                break
        if start_edge:
            candidate_edges = [start_edge] + list(new_edges)
            try:
                traci.vehicle.setRoute(veh, candidate_edges)
                return True
            except Exception as e:
                log(f"[safe_apply_route] prepended route-start edge failed: {e}")
        # Fallback: changeTarget
        if dest_edge:
            try:
                traci.vehicle.changeTarget(veh, dest_edge)
                return True
            except Exception as e:
                log(f"[safe_apply_route] changeTarget fallback failed: {e}")
        # Last-ditch: create a named route and set by id
        try:
            rid = f"route_for_{veh}_{int(time.time()*1000)}"
            traci.route.add(rid, list(new_edges))
            traci.vehicle.setRoute(veh, new_edges)
            return True
        except Exception as e:
            log(f"[safe_apply_route] creating route fallback failed: {e}")
            return False
    except Exception as e:
        log(f"[safe_apply_route] unexpected error: {e}")
        return False


# ================= PART 2/5 =================
# Path, congestion, graph building, Yen K-shortest (node-based) + ETA realistic

def get_congestion(edge_id):
    try:
        vehs = safe_traci(traci.edge.getLastStepVehicleNumber, edge_id, default=0) or 0
        mean_spd = safe_traci(traci.edge.getLastStepMeanSpeed, edge_id, default=0.0) or 0.0
        max_spd = safe_traci(traci.lane.getMaxSpeed, f"{edge_id}_0", default=13.9) or 13.9
        length = safe_traci(traci.lane.getLength, f"{edge_id}_0", default=50.0) or 50.0
        if max_spd <= 0:
            return 0.0
        speed_ratio = mean_spd / max_spd
        density = vehs / max(1.0, length / 100.0)
        c = (1.0 - speed_ratio) + 0.10 * density
        return float(max(0.0, min(1.0, c)))
    except Exception:
        return 0.0

def get_path(amb, hosp_edge):
    start = get_valid_start_edge(amb)
    target = hosp_edge
    if not start or not target:
        return (0.0, 0.0, [])
    rt = safe_traci(traci.simulation.findRoute, start, target, default=None)
    if not rt or not getattr(rt, "edges", None):
        return (0.0, 0.0, [])
    edges = list(rt.edges)
    total_len = 0.0
    cong_vals = []
    for e in edges:
        L = safe_traci(traci.lane.getLength, f"{e}_0", default=50.0) or 50.0
        total_len += L
        cong_vals.append(get_congestion(e))
    avg_cong = float(np.mean(cong_vals)) if cong_vals else 0.0
    return (total_len, avg_cong, edges)

def fitness_fn(dist, beds, spec_ok, cong, severity):
    dist_term = 1.0 / (1.0 + (dist / 4000.0))
    s = (severity or "medium").lower()
    if s == "critical":
        wD, wB, wS, wC = 0.5, 0.1, 0.3, 0.1
    elif s == "high":
        wD, wB, wS, wC = 0.4, 0.2, 0.3, 0.1
    else:
        wD, wB, wS, wC = 0.3, 0.3, 0.3, 0.1
    return (wD * dist_term + wB * (min(beds, 10) / 10.0) + wS * (1 if spec_ok else 0) + wC * (1 - cong))

def build_graph():
    global _net
    if _net is None:
        try:
            _net = sumolib.net.readNet(NET_FILE)
        except Exception as e:
            print("[build_graph] could not read net:", e)
            return {}, {}
    adj = {}
    edge_map = {}
    for e in _net.getEdges():
        try:
            eid = e.getID()
            u = e.getFromNode().getID()
            v = e.getToNode().getID()
            L = e.getLength() or 1.0
            adj.setdefault(u, []).append((v, eid, L))
            edge_map[(u, v)] = eid
        except Exception:
            continue
    return adj, edge_map

def dijkstra_nodes(adj, src, tgt):
    dist = {src: 0.0}
    prev = {}
    pq = [(0.0, src)]
    visited = set()
    while pq:
        d, u = heapq.heappop(pq)
        if u in visited:
            continue
        visited.add(u)
        if u == tgt:
            break
        for (v, eid, w) in adj.get(u, []):
            nd = d + (w or 1.0)
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))
    if tgt not in dist:
        return None
    path = []
    cur = tgt
    while cur != src:
        path.append(cur)
        cur = prev[cur]
    path.append(src)
    path.reverse()
    return path

def nodes_to_edgepath(node_path, edge_map):
    edges = []
    for i in range(len(node_path) - 1):
        u = node_path[i]
        v = node_path[i + 1]
        eid = edge_map.get((u, v))
        if not eid:
            return None
        edges.append(eid)
    return edges

def yen_k_shortest(adj, edge_map, src_node, tgt_node, K=4):
    A = []
    A_edges = []
    B = []
    node_path = dijkstra_nodes(adj, src_node, tgt_node)
    if not node_path:
        return []
    first_edges = nodes_to_edgepath(node_path, edge_map)
    if not first_edges:
        return []
    A.append(node_path)
    A_edges.append(first_edges)
    for k in range(1, K):
        for i in range(len(A[k - 1]) - 1):
            root_nodes = A[k - 1][:i + 1]
            removed = []
            for p_nodes in A:
                if len(p_nodes) > i and p_nodes[:i + 1] == root_nodes:
                    u = p_nodes[i]
                    v = p_nodes[i + 1]
                    new_neighbors = [(n, eid, w) for (n, eid, w) in adj.get(u, []) if n != v]
                    removed.append((u, adj.get(u, []).copy()))
                    adj[u] = new_neighbors
            spur_start = root_nodes[-1]
            spur_path_nodes = dijkstra_nodes(adj, spur_start, tgt_node)
            for (u, saved_list) in removed:
                adj[u] = saved_list
            if not spur_path_nodes:
                continue
            total_nodes = root_nodes[:-1] + spur_path_nodes
            edge_path = nodes_to_edgepath(total_nodes, edge_map)
            if edge_path and edge_path not in A_edges and edge_path not in B:
                B.append(edge_path)
        if not B:
            break
        B.sort(key=lambda path: sum(_net.getEdge(e).getLength() for e in path))
        best = B.pop(0)
        A_edges.append(best)
        nodes_for_best = []
        for e in best:
            edge_obj = _net.getEdge(e)
            if not nodes_for_best:
                nodes_for_best.append(edge_obj.getFromNode().getID())
            nodes_for_best.append(edge_obj.getToNode().getID())
        A.append(nodes_for_best)
    return A_edges

# ------------------ ETA realistic calculator ------------------
def compute_eta_realistic(edges):
    """Compute ETA in seconds for an edge list using SUMO's last step mean speed per edge.
       Skip internal edges. Use safe defaults if mean speed unavailable."""
    total_eta = 0.0
    if not edges:
        return None
    for e in edges:
        if _is_internal(e):
            continue
        length = safe_traci(traci.lane.getLength, f"{e}_0", default=20) or 20
        speed = safe_traci(traci.edge.getLastStepMeanSpeed, e, default=None)
        if speed is None or speed <= 0.1:
            # fallback: use lane max speed
            speed = safe_traci(traci.lane.getMaxSpeed, f"{e}_0", default=13.9) or 13.9
        # avoid division by zero
        speed = max(0.1, float(speed))
        total_eta += (float(length) / speed)
    return float(total_eta)

# ================= end PART 2/5 =================
# ================= PART 3/5 =================
# GA, assignment (offload), ETA-before estimator using compute_eta_realistic

def run_ga_verbose(amb, patient, candidates):
    log(f"\n🚑 {amb} — Running Genetic Algorithm for Hospital Selection")
    pop = [random.choice(candidates) for _ in range(POP_SIZE)]
    best_record = None
    for gen in range(1, GA_GENERATIONS + 1):
        log(f"\n🧬 Generation {gen}")
        scored = []
        for h in pop:
            dist, cong, edges = get_path(amb, hospital_edges[h])
            beds = hospitals[h]["beds_available"]
            spec_ok = patient["required_specialist"] in hospitals[h]["doctors"]
            fit = fitness_fn(dist, beds, spec_ok, cong, patient["severity"])
            scored.append((h, fit, dist, beds, cong, edges))
            log(f"   🏥 {h}: dist={dist:.1f}m | cong={cong:.2f} | beds={beds} | fit={fit:.3f}")
        scored.sort(key=lambda x: x[1], reverse=True)
        best_record = scored[0]
        ids = [s[0] for s in scored]
        newpop = [best_record[0]]
        while len(newpop) < POP_SIZE:
            a = random.choice(ids); b = random.choice(ids)
            child = a if random.random() < 0.5 else b
            if random.random() < MUTATION_RATE:
                child = random.choice(ids)
            newpop.append(child)
        pop = newpop
    if best_record:
        h, fit, dist, beds, cong, edges = best_record
        if edges:
            ok = safe_apply_route(amb, edges, dest_edge=hospital_edges[h])
            if not ok:
                log(f"[run_ga_verbose] Could not set route for {amb} to {h}")
        log(f"\n🎯 FINAL SELECTION → {h} | fit={fit:.3f} | cong={cong:.2f} | dist={dist:.1f}m")
        return h
    return None

def run_ga_silent(amb, patient, candidates):
    pop = [random.choice(candidates) for _ in range(POP_SIZE)]
    best_record = None
    for _ in range(GA_GENERATIONS):
        scored = []
        for h in pop:
            dist, cong, edges = get_path(amb, hospital_edges[h])
            beds = hospitals[h]["beds_available"]
            spec_ok = patient["required_specialist"] in hospitals[h]["doctors"]
            fit = fitness_fn(dist, beds, spec_ok, cong, patient["severity"])
            scored.append((h, fit, dist, cong, edges))
        scored.sort(key=lambda x: x[1], reverse=True)
        best_record = scored[0]
        ids = [s[0] for s in scored]
        newpop = [best_record[0]]
        while len(newpop) < POP_SIZE:
            a = random.choice(ids); b = random.choice(ids)
            child = a if random.random() < 0.5 else b
            if random.random() < MUTATION_RATE:
                child = random.choice(ids)
            newpop.append(child)
        pop = newpop
    if best_record:
        h, fit, dist, cong, edges = best_record
        if edges:
            ok = safe_apply_route(amb, edges, dest_edge=hospital_edges[h])
            if not ok:
                log(f"[run_ga_silent] Could not set route for {amb} to {h}")
        return (h, fit, dist, cong, edges)
    return (None, 0, 0, 0, [])

def assign_hospital(amb, step):
    """Assign hospital when ambulance is in RSU range — OFFLOAD at that time (color GREEN).
       Reserve a bed (lock) and decrement available beds. Unlock only at arrival.
    """
    patient = patients[amb]
    suitable = [h for h, info in hospitals.items() if info["beds_available"] > 0 and patient["required_specialist"] in info["doctors"]]
    if not suitable:
        log(f"❌ No suitable hospital found for {amb}")
        return None
    chosen = run_ga_verbose(amb, patient, suitable)
    if not chosen:
        log(f"❌ GA failed for {amb}")
        return None
    # Reserve bed immediately (lock)
    hospitals[chosen]["beds_available"] -= 1
    beds_reserved[amb] = chosen
    # Record assignment
    assigned[amb] = chosen
    assigned_step[amb] = step
    # ETA BEFORE: compute using the edges to destination (realistic)
    start = get_valid_start_edge(amb)
    dist, cong, edges = get_path(amb, hospital_edges[chosen])
    eta_b = None
    try:
        eta_b = compute_eta_realistic(edges)
    except Exception:
        eta_b = None
    eta_before[amb] = eta_b
    # OFFLOAD: set ambulance color to GREEN at offload time (RSU)
    safe_traci(traci.vehicle.setColor, amb, OFFLOADED_COLOR)
    # not rerouted yet
    route_assign_meta[(amb, chosen)] = {"rerouted": False}
    # create task offload record entry (arrival fields later)
    task_offloads.append({
        "ambulance": amb,
        "severity": patient.get("severity"),
        "hospital": chosen,
        "offload_step": step,
        "offload_time_s": eta_b if eta_b is not None else None,
        "arrival_step": None,
        "arrival_time_s": None,
        "waiting_time_s": None,
        "reroutes": 0,
        "accident_impact": None
    })
    log(f"\n🎯 ASSIGNED & OFFLOADED → {amb} → {chosen}")
    log(f"🔒 Hospital {chosen}: 1 bed reserved for {amb}. Beds remaining: {hospitals[chosen]['beds_available']}")
    return chosen

# ================= end PART 3/5 =================
# ================= PART 4/5 =================
# Reroute engine (Yen starting at vehicle current node), arrival detection and on_arrival

def adjust_lane_speeds(level):
    edges = safe_traci(traci.edge.getIDList, default=[]) or []
    for e in edges:
        ln = safe_traci(traci.edge.getLaneNumber, e, default=1) or 1
        for i in range(ln):
            lane = f"{e}_{i}"
            cur = safe_traci(traci.lane.getMaxSpeed, lane, default=13.9) or 13.9
            if level == "low":
                new = cur
            elif level == "medium":
                new = cur * 0.90
            else:
                new = cur * 0.60
            safe_traci(traci.lane.setMaxSpeed, lane, new)

def spawn_background_traffic(level):
    count = BACKGROUND_COUNTS.get(level, 200)
    log(f"\n🚘 Spawning {count} background vehicles for level={level.upper()}")
    edges = safe_traci(traci.edge.getIDList, default=[]) or []
    if not edges:
        return
    AMB_ROUTES = list(hospital_edges.values())
    for i in range(count):
        try:
            if level == "high":
                start = random.choice(AMB_ROUTES)
                end   = random.choice(AMB_ROUTES)
                v_speed = 5.0
            elif level == "medium":
                start = random.choice(edges)
                end   = random.choice(edges)
                v_speed = 8.0
            else:
                start = random.choice(edges)
                end   = random.choice(edges)
                v_speed = 13.9
            if start == end:
                continue
            rt = safe_traci(traci.simulation.findRoute, start, end, default=None)
            if not rt or not getattr(rt, "edges", None):
                continue
            rid = f"bg_rt_{i}"
            vid = f"bg_{i}"
            safe_traci(traci.route.add, rid, list(rt.edges))
            ok = safe_traci(traci.vehicle.add, vid, rid, default=None)
            if ok is None:
                continue
            safe_traci(traci.vehicle.setMaxSpeed, vid, v_speed)
            safe_traci(traci.vehicle.setColor, vid, (180, 180, 180))
        except Exception as e:
            if DEBUG:
                print("[spawn_background] error:", e)
            continue

acc_active = False
acc_edge = None

def handle_accident(step):
    global acc_active, acc_edge
    if step == ACC_START:
        edges = safe_traci(traci.edge.getIDList, default=[]) or []
        non_internal = [e for e in edges if not _is_internal(e)]
        if not non_internal:
            return
        acc_edge = random.choice(non_internal)
        ln = safe_traci(traci.edge.getLaneNumber, acc_edge, default=1) or 1
        for i in range(ln):
            safe_traci(traci.lane.setMaxSpeed, f"{acc_edge}_{i}", ACC_REDUCED_SPEED)
        acc_active = True
        log(f"💥 Accident at {acc_edge} (speed reduced)")
    if acc_active and step == ACC_START + ACC_DURATION:
        ln = safe_traci(traci.edge.getLaneNumber, acc_edge, default=1) or 1
        for i in range(ln):
            safe_traci(traci.lane.setMaxSpeed, f"{acc_edge}_{i}", 13.9)
        acc_active = False
        log(f"✅ Accident cleared at {acc_edge}")

def reroute_if_better(amb, hosp, patient, step):
    if amb in completed:
        return
    if reroute_counter.get(amb, 0) >= MAX_REROUTES:
        return
    last_step = last_reroute_step.get(amb, -9999)
    if step - last_step < MIN_REROUTE_INTERVAL:
        return
    hosp_edge = hospital_edges.get(hosp)
    if not hosp_edge:
        return
    old_dist, old_cong, old_edges = get_path(amb, hosp_edge)
    lastC = last_route_congestion.get(amb, None)
    last_route_congestion[amb] = old_cong
    trigger = False
    if lastC is not None and (old_cong - lastC >= REROUTE_DELTA_THRESHOLD):
        trigger = True
    if old_cong >= REROUTE_CONGESTION_THRESHOLD:
        trigger = True
    if not trigger:
        return
    global _graph_cache, _edge_map_cache
    if _graph_cache is None:
        _graph_cache, _edge_map_cache = build_graph()
    adj = _graph_cache
    edge_map = _edge_map_cache
    start_edge = get_valid_start_edge(amb)
    dest_edge = hosp_edge
    if not start_edge or not dest_edge:
        return
    # --- NEW: compute Yen from vehicle's current node ---
    try:
        curr_edge = safe_traci(traci.vehicle.getRoadID, amb, default=None)
        if curr_edge is None or _is_internal(curr_edge):
            rt = safe_traci(traci.vehicle.getRoute, amb, default=[])
            curr_edge = next((e for e in rt if not _is_internal(e)), None)
        if curr_edge is None:
            return
        src_node = _net.getEdge(curr_edge).getToNode().getID()
        tgt_node = _net.getEdge(dest_edge).getToNode().getID()
    except Exception:
        log("⚠️ Cannot compute current or destination node for Yen reroute")
        return
    k_paths = yen_k_shortest(adj, edge_map, src_node, tgt_node, K=K_PATHS)
    candidates = []
    for edges in k_paths:
        candidate_edges = list(edges)
        total_d = 0.0
        cong_vals = []
        valid = True
        for e in candidate_edges:
            if _is_internal(e):
                valid = False
                break
            L = safe_traci(traci.lane.getLength, f"{e}_0", default=50) or 50
            total_d += L
            cong_vals.append(get_congestion(e))
        if valid and candidate_edges:
            avg_cong = float(np.mean(cong_vals)) if cong_vals else 0.0
            candidates.append(("yen", total_d, avg_cong, candidate_edges))
    # safety: include SUMO main route
    rt_main = safe_traci(traci.simulation.findRoute, curr_edge, dest_edge, default=None)
    if rt_main and getattr(rt_main, "edges", None):
        edges_main = list(rt_main.edges)
        dist_main = sum(safe_traci(traci.lane.getLength, f"{e}_0", default=50) for e in edges_main)
        cong_main = np.mean([get_congestion(e) for e in edges_main]) if edges_main else 0.0
        candidates.append(("sumo_main", dist_main, cong_main, edges_main))
    # GA diversification
    new_h, ffit, d_ga, c_ga, edges_ga = run_ga_silent(amb, patient, [hosp])
    if edges_ga:
        edges = list(edges_ga)
        if random.random() < 0.2:
            random.shuffle(edges)
        cd = sum(safe_traci(traci.lane.getLength, f"{e}_0", default=50) for e in edges)
        cc = np.mean([get_congestion(e) for e in edges]) if edges else 0.0
        candidates.append(("ga_route", cd, cc, edges))
    if not candidates:
        log(f"⚠️ No reroute candidates found for {amb}")
        return
    def score(dist, cong):
        return 0.7 * cong + 0.3 * (dist / 3000.0)
    best = min(candidates, key=lambda x: score(x[1], x[2]))
    method, new_dist, new_cong, new_edges = best
    old_score = score(old_dist, old_cong)
    new_score = score(new_dist, new_cong)
    if new_score >= old_score - 0.005:
        log(f"⚠️ Reroute skipped for {amb}: combined score not improved enough ({new_score:.3f} ≥ {old_score:.3f} - 0.005)")
        return
    # apply reroute safely
    ok = safe_apply_route(amb, new_edges, dest_edge=dest_edge)
    if not ok:
        log(f"⚠️ Could not apply reroute for {amb}; skipping.")
        return
    reroute_counter[amb] = reroute_counter.get(amb, 0) + 1
    route_assign_meta.setdefault((amb, hosp), {})["rerouted"] = True
    last_reroute_step[amb] = step
    # update task_offloads reroute count live
    for rec in task_offloads:
        if rec["ambulance"] == amb:
            rec["reroutes"] = reroute_counter.get(amb, 0)
            break
    log("\n🔁 REROUTE APPLIED")
    log(f"   Method: {method}")
    log(f"   Ambulance: {amb}")
    log(f"   Old → dist={old_dist:.1f} | cong={old_cong:.3f}")
    log(f"   New → dist={new_dist:.1f} | cong={new_cong:.3f}")
    log(f"   (Combined score improved: {old_score:.3f} -> {new_score:.3f})")
    log(f"   GA + Multi-path search applied.")

def on_arrival(amb, hosp):
    """Called when ambulance reaches hospital edge. ETA-after recorded via realistic compute."""
    if amb in completed:
        return
    completed.add(amb)
    arrival_step[amb] = current_step
    # set to WHITE at hospital arrival
    safe_traci(traci.vehicle.setColor, amb, ARRIVED_COLOR)
    # ETA-after: compute from current vehicle route if possible else use traveltime/fallback
    try:
        cur_route = safe_traci(traci.vehicle.getRoute, amb, default=[]) or []
        a_eta = compute_eta_realistic(cur_route)
    except Exception:
        a_eta = None
    if a_eta is None:
        # try traveltime
        try:
            a_eta = safe_traci(traci.vehicle.getTraveltime, amb, default=None)
        except Exception:
            a_eta = None
    if a_eta is None and amb in assigned_step:
        a_eta = float(arrival_step[amb] - assigned_step[amb])
    eta_after[amb] = a_eta
    # update task_offloads record and unlock hospital (remove lock)
    for rec in task_offloads:
        if rec["ambulance"] == amb:
            rec["arrival_step"] = arrival_step[amb]
            rec["arrival_time_s"] = a_eta if a_eta is not None else None
            rec["waiting_time_s"] = waiting_time.get(amb, 0.0)
            rec["reroutes"] = reroute_counter.get(amb, 0)
            break
    locked = beds_reserved.get(amb)
    if locked:
        beds_reserved.pop(amb, None)
        log(f"🔓 Hospital {locked} is now unlocked for new reservations (if beds remain).")
    log(f"\n🎉 ambulance {amb} reached {hosp} — Task Completed")
    log(f"🛏️ Hospital {hosp} reservation confirmed for {amb}. Beds remaining: {hospitals[hosp]['beds_available']}")

def check_arrival(amb, hosp):
    """Detect when ambulance reaches hospital edge robustly."""
    if amb in completed:
        return True
    hosp_edge = hospital_edges.get(hosp)
    if not hosp_edge:
        return False
    current = safe_traci(traci.vehicle.getRoadID, amb, default=None)
    if current == hosp_edge:
        on_arrival(amb, hosp)
        return True
    try:
        if current and hosp_edge and hosp_edge in str(current):
            on_arrival(amb, hosp)
            return True
    except Exception:
        pass
    route = safe_traci(traci.vehicle.getRoute, amb, default=[]) or []
    if route and hosp_edge in route:
        try:
            hosp_idx = route.index(hosp_edge)
            cur_idx = route.index(current) if current in route else -1
            if cur_idx != -1 and cur_idx >= hosp_idx - 1:
                on_arrival(amb, hosp)
                return True
        except Exception:
            pass
    try:
        if _net is not None:
            he = _net.getEdge(hosp_edge)
            if he is not None:
                hx, hy = he.getToNode().getCoord()
                pos = safe_traci(traci.vehicle.getPosition, amb, default=None)
                if pos:
                    ax, ay = pos
                    d = math.hypot(ax - hx, ay - hy)
                    if d <= 20.0:
                        on_arrival(amb, hosp)
                        return True
    except Exception:
        pass
    return False

def finalize_waiting_times():
    for rec in task_offloads:
        amb = rec["ambulance"]
        rec["waiting_time_s"] = waiting_time.get(amb, 0.0)

# ================= end PART 4/5 =================
# ================= PART 5/5 =================
# Task-offload CSV/XLSX, plotting, main loop

def write_task_offload_file():
    finalize_waiting_times()
    headers = ["ambulance","severity","hospital","offload_step","offload_time_s","arrival_step","arrival_time_s","waiting_time_s","reroutes","accident_impact"]
    try:
        with open(TASK_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(headers)
            for rec in task_offloads:
                row = [rec.get(h) for h in headers]
                w.writerow(row)
        print("Task offloading CSV saved:", TASK_CSV)
    except Exception as e:
        print("[write_task_offload_file] CSV save error:", e)
    try:
        import pandas as pd
        df = pd.DataFrame(task_offloads)
        df.to_excel(TASK_XLSX, index=False)
        print("Task offloading XLSX saved:", TASK_XLSX)
    except Exception:
        pass

def generate_eta_graph():
    labels = []
    normal_vals = []
    ga_vals = []
    for rec in task_offloads:
        a = rec["ambulance"]
        b = rec.get("offload_time_s")
        g = rec.get("arrival_time_s")
        if b is None or g is None:
            continue
        labels.append(a)
        normal_vals.append(b / 60.0)   # minutes
        ga_vals.append(g / 60.0)       # minutes
    if not labels:
        print("No ETA data to plot.")
        print("DEBUG: eta_before keys:", eta_before)
        print("DEBUG: eta_after keys:", eta_after)
        return
    x = np.arange(len(labels))
    width = 0.35
    plt.figure(figsize=(12,6))
    plt.bar(x - width/2, normal_vals, width, label='Normal ETA (min)', color='gray')
    plt.bar(x + width/2, ga_vals, width, label='Actual ETA (min)', color='#d81b60')
    plt.ylabel("ETA (minutes)")
    plt.xlabel("Ambulance ID")
    plt.title("Comparison of ETA: Before offload (estimated) vs Actual at arrival")
    plt.xticks(x, labels, rotation=45)
    plt.grid(axis='y', linestyle='--', alpha=0.6)
    plt.legend(loc='upper right')
    for i, v in enumerate(normal_vals):
        plt.text(i - width/2, v + 0.02, f"{v:.1f}", ha='center', fontsize=9)
    for i, v in enumerate(ga_vals):
        plt.text(i + width/2, v + 0.02, f"{v:.1f}", ha='center', fontsize=9)
    plt.tight_layout()
    try:
        plt.savefig(ETA_GRAPH_FILE)
        ETA_GRAPH_FILE
    except Exception as e:
        print("[generate_eta_graph] save error:", e)
    plt.close()

def generate_waiting_pie():
    labels = []
    sizes = []
    for rec in task_offloads:
        amb = rec["ambulance"]
        w = rec.get("waiting_time_s", 0.0)
        if w and w > 0:
            labels.append(f"{amb} ({int(w)}s)")
            sizes.append(w)
    if not sizes:
        print("No waiting data to plot.")
        return
    plt.figure(figsize=(8,8))
    plt.pie(sizes, labels=labels, autopct="%1.1f%%", startangle=140)
    plt.title("Waiting Time Distribution (seconds)")
    plt.tight_layout()
    try:
        plt.savefig(WAITING_GRAPH_FILE)
        WAITING_GRAPH_FILE
    except Exception as e:
        print("[generate_waiting_pie] save error:", e)
    plt.close()

def print_simple_reroute_summary():
    print("\n━━━━━━━━ REROUTE SUMMARY ━━━━━━━━")
    ambs = sorted(set(list(reroute_counter.keys()) + list(assigned.keys())))
    for a in ambs:
        c = reroute_counter.get(a, 0)
        print(f"{a} → rerouted {c} times")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
    print("GRAPHS ARE GENERATED");

def main():
    global current_step, _net
    level = input("Enter traffic level (low / medium / high): ").strip().lower()
    if level not in ("low", "medium", "high"):
        print("Invalid level. Defaulting to medium.")
        level = "medium"
    log("\n🚦 Simulation Started\n")
    try:
        if os.path.exists(LOG_FILE): os.remove(LOG_FILE)
    except:
        pass
    # start SUMO
    try:
        traci.start(["sumo-gui", "-c", SUMO_CONFIG])
    except Exception as e:
        print("[main] traci.start failed:", e)
        return
    # print junctions to help choose RSU ids
    print("\n🔍 Junctions in network:", safe_traci(traci.junction.getIDList, default=[]))
    # prepare network cache
    try:
        if _net is None:
            _net = sumolib.net.readNet(NET_FILE)
    except Exception as e:
        print("[main] Could not load netfile:", e)
    adjust_lane_speeds(level)
    spawn_background_traffic(level)
    # RSU ids — change if needed
    RSU_LIST = ["306834748", "1837783520", "248459796", "11707451095"]
    for step in range(SIM_STEPS):
        current_step = step
        try:
            traci.simulationStep()
        except Exception as e:
            print("[main] simulationStep error or SUMO closed:", e)
            break
        handle_accident(step)
        vehs = safe_traci(traci.vehicle.getIDList, default=[]) or []
        for amb in vehs:
            if not str(amb).startswith("ambulance_"):
                continue
            # initialize keys for all seen ambulances
            eta_before.setdefault(amb, None)
            eta_after.setdefault(amb, None)
            x, y = safe_traci(traci.vehicle.getPosition, amb, default=(0, 0))
            # Waiting time accumulation (speed-based)
            speed = safe_traci(traci.vehicle.getSpeed, amb, default=0) or 0
            if amb not in last_speed:
                last_speed[amb] = speed
            if speed < 2.0:
                waiting_time[amb] += TIME_STEP
            last_speed[amb] = speed
            # If already assigned, check arrival and reroute
            if amb in assigned:
                hosp = assigned.get(amb)
                if not hosp:
                    continue
                if check_arrival(amb, hosp):
                    continue
                if step % RE_ROUTE_CHECK_INTERVAL == 0:
                    reroute_if_better(amb, hosp, patients[amb], step)
                continue
            # Not assigned → check RSU proximity (offload here)
            nearest = None
            bestD = float("inf")
            for r in RSU_LIST:
                pos = safe_traci(traci.junction.getPosition, r, default=None)
                if not pos:
                    continue
                d = get_distance((x, y), pos)
                if d < bestD:
                    bestD = d
                    nearest = r
            if nearest and bestD <= RSU_RANGE:
                assign_hospital(amb, step)
                continue
    # END SIM
    try:
        traci.close()
    except:
        pass
    # finalize data and write task-offload file
    write_task_offload_file()
    # write log
    try:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(log_lines))
    except Exception as e:
        print("[main] writing log failed:", e)
    print("\n📝 Log saved to", LOG_FILE)
    print_simple_reroute_summary()
    # plots
    generate_eta_graph()
    generate_waiting_pie()
    print("\n🎉 Simulation completed.\n")

if __name__ == "__main__":
    main()
# ================= end PART 5/5 =================
