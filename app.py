# from fastapi import FastAPI
# from pydantic import BaseModel
# import requests
# from itertools import permutations

# app = FastAPI()
# API_KEY = "ZRGuIOOKLritb2NoH9teNXEJ6PKTAdvVPBBwNRS4h0KY9Gk4rXhv3KBzmlG1UxOq"

# class Location(BaseModel):
#     lat: float
#     lon: float
#     priority: int = 0
#     order_id: int = 0

# class RequestData(BaseModel):
#     current_lat: float
#     current_lon: float
#     locations: list[Location]

# def get_distance_duration(origin, destinations):
#     dest_str = "|".join([f"{d[0]},{d[1]}" for d in destinations])
#     url = (
#         f"https://api.distancematrix.ai/maps/api/distancematrix/json"
#         f"?origins={origin}&destinations={dest_str}&key={API_KEY}"
#     )
#     resp = requests.get(url)
#     data = resp.json()
#     results = []
#     for elem in data["rows"][0]["elements"]:
#         results.append({
#             "distance_text": elem["distance"]["text"],
#             "duration_text": elem["duration"]["text"],
#             "duration_value": elem["duration"]["value"]
#         })
#     return results

# @app.post("/optimize_route")
# def optimize_route(req: RequestData):
#     origin = (req.current_lat, req.current_lon)
#     points = [(loc.lat, loc.lon) for loc in req.locations]

#     # distances from origin to each location
#     map_points_data = get_distance_duration(f"{origin[0]},{origin[1]}", points)
#     map_points_dict = {}
#     for loc, info in zip(req.locations, map_points_data):
#         map_points_dict[loc.order_id] = {
#             "lat": loc.lat,
#             "lon": loc.lon,
#             "distance_text": info["distance_text"],
#             "duration_text": info["duration_text"],
#             "duration_value": info["duration_value"]
#         }

#     # build full duration matrix (all points with origin included)
#     all_points = [origin] + points
#     n = len(all_points)
#     duration_matrix = [[0]*n for _ in range(n)]
#     distance_matrix = [[0]*n for _ in range(n)]
#     for i in range(n):
#         origins_str = f"{all_points[i][0]},{all_points[i][1]}"
#         destinations_str = "|".join([f"{p[0]},{p[1]}" for p in all_points])
#         url = (
#             f"https://api.distancematrix.ai/maps/api/distancematrix/json"
#             f"?origins={origins_str}&destinations={destinations_str}&key={API_KEY}"
#         )
#         resp = requests.get(url)
#         data = resp.json()
#         for j, elem in enumerate(data["rows"][0]["elements"]):
#             duration_matrix[i][j] = elem["duration"]["value"]
#             distance_matrix[i][j] = elem["distance"]["value"]

#     # try all permutations
#     loc_indices = list(range(1, n))
#     best_order = None
#     best_total = float("inf")
#     for perm in permutations(loc_indices):
#         total = 0
#         prev = 0
#         for idx in perm:
#             loc_priority = req.locations[idx-1].priority
#             total += duration_matrix[prev][idx] - loc_priority*300
#             prev = idx
#         if total < best_total:
#             best_total = total
#             best_order = perm

#     optimized_route = []
#     map_points = []
#     prev_idx = 0  # start from origin
#     for idx in best_order:
#         loc = req.locations[idx-1]
#         optimized_route.append({
#             "order_id": loc.order_id,
#             "lat": loc.lat,
#             "lon": loc.lon,
#             "priority": loc.priority,
#             # from origin
#             "distance_from_origin_meters": distance_matrix[0][idx],
#             "duration_from_origin_seconds": duration_matrix[0][idx],
#             # from previous point in route
#             "distance_from_prev_meters": distance_matrix[prev_idx][idx],
#             "duration_from_prev_seconds": duration_matrix[prev_idx][idx]
#         })
#         prev_idx = idx

#         info = map_points_dict[loc.order_id]
#         map_points.append({
#             "order_id": loc.order_id,
#             "lat": info["lat"],
#             "lon": info["lon"],
#             "distance_text": info["distance_text"],
#             "duration_text": info["duration_text"],
#             "duration_value": info["duration_value"]
#         })


#     return {
#         "origin": {"lat": origin[0], "lon": origin[1]},
#         "optimized_route": optimized_route,
#         "map_points": map_points,
#         "total_duration_seconds": best_total
#     }
# -------------------------------------------------------------------------------------------

from fastapi import FastAPI
from pydantic import BaseModel
import requests

app = FastAPI()
API_KEY = "ZRGuIOOKLritb2NoH9teNXEJ6PKTAdvVPBBwNRS4h0KY9Gk4rXhv3KBzmlG1UxOq"

class Location(BaseModel):
    lat: float
    lon: float
    priority: int = 0
    order_id: int = 0

class RequestData(BaseModel):
    current_lat: float
    current_lon: float
    locations: list[Location]

def build_distance_matrix(all_points):
    origins_str = "|".join([f"{p[0]},{p[1]}" for p in all_points])
    destinations_str = origins_str
    url = (
        f"https://api.distancematrix.ai/maps/api/distancematrix/json"
        f"?origins={origins_str}&destinations={destinations_str}&key={API_KEY}"
    )

    resp = requests.get(url)
    if resp.status_code != 200:
        raise Exception(f"API Error: {resp.status_code}")

    data = resp.json()
    if "rows" not in data:
        raise Exception(f"Invalid response: {data}")

    n = len(all_points)
    duration_matrix = [[0]*n for _ in range(n)]
    distance_matrix = [[0]*n for _ in range(n)]

    for i, row in enumerate(data["rows"]):
        for j, elem in enumerate(row["elements"]):
            if elem["status"] != "OK":
                duration_matrix[i][j] = 9999999
                distance_matrix[i][j] = 9999999
            else:
                duration_matrix[i][j] = elem["duration"]["value"]
                distance_matrix[i][j] = elem["distance"]["value"]

    return duration_matrix, distance_matrix


def nearest_neighbor_heuristic(duration_matrix):
    n = len(duration_matrix)
    visited = [False] * n
    visited[0] = True  # origin
    route = []
    current = 0
    for _ in range(n-1):
        next_idx = None
        best_time = float("inf")
        for j in range(1, n):
            if not visited[j] and duration_matrix[current][j] < best_time:
                next_idx = j
                best_time = duration_matrix[current][j]
        route.append(next_idx)
        visited[next_idx] = True
        current = next_idx
    return route


@app.post("/optimize_route")
def optimize_route(req: RequestData):
    origin = (req.current_lat, req.current_lon)
    points = [(loc.lat, loc.lon) for loc in req.locations]
    all_points = [origin] + points

    # build full matrix (one API call only)
    duration_matrix, distance_matrix = build_distance_matrix(all_points)

    # get optimized order (nearest neighbor heuristic)
    best_order = nearest_neighbor_heuristic(duration_matrix)

    optimized_route = []
    map_points = []
    prev_idx = 0
    total_duration = 0

    for idx in best_order:
        loc = req.locations[idx-1]
        optimized_route.append({
            "order_id": loc.order_id,
            "lat": loc.lat,
            "lon": loc.lon,
            "priority": loc.priority,
            "distance_from_origin_meters": distance_matrix[0][idx],
            "duration_from_origin_seconds": duration_matrix[0][idx],
            "distance_from_prev_meters": distance_matrix[prev_idx][idx],
            "duration_from_prev_seconds": duration_matrix[prev_idx][idx]
        })

        total_duration += duration_matrix[prev_idx][idx]

        map_points.append({
            "order_id": loc.order_id,
            "lat": loc.lat,
            "lon": loc.lon,
            "distance_text": f"{distance_matrix[prev_idx][idx]/1000:.1f} km",
            "duration_text": f"{duration_matrix[prev_idx][idx]//60} mins",
            "duration_value": duration_matrix[prev_idx][idx]
        })

        prev_idx = idx

    return {
        "origin": {"lat": origin[0], "lon": origin[1]},
        "optimized_route": optimized_route,
        "map_points": map_points,
        "total_duration_seconds": total_duration
    }

# -------------------------------------------------------------------------------------------
# http://127.0.0.1:8000/docs
# https://.postman.co/workspace/My-Workspace~e8ae2448-faa4-412d-849b-1df7333cb7a9/request/39145632-1eb335e5-4b2b-4d7c-b5b7-7a7fee86b06b?action=share&creator=39145632
# https://omaritf.pythonanywhere.com/optimize_route

# body req 
# ------------------------
# {
#   "current_lat": 24.800266666991973,
#   "current_lon": 46.80583614521882,
#   "locations": [
#     { "lat": 24.786157903353768, "lon": 46.77888360194174, "priority": 1, "order_id": 101 },
#     { "lat": 24.799052305173873, "lon": 46.71311036745888, "priority": 0, "order_id": 102 },
#     { "lat": 24.76401638240479, "lon": 46.78853360940482, "priority": 0, "order_id": 103 },
#     { "lat": 24.741313967915147, "lon": 46.65880775252222, "priority": 1, "order_id": 104 }
#   ]
# }
