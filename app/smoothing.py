import math

def haversine(lon1, lat1, lon2, lat2):
    R = 6371000 
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1-a))

def densify_route(coords, max_segment_meters=5.0):
    dense_coords = [coords[0]]
    for i in range(1, len(coords)):
        lon1, lat1, z1 = coords[i-1]
        lon2, lat2, z2 = coords[i]
        dist = haversine(lon1, lat1, lon2, lat2)
        
        if dist > max_segment_meters:
            steps = int(math.ceil(dist / max_segment_meters))
            for j in range(1, steps):
                frac = j / steps
                interp_lon = lon1 + (lon2 - lon1) * frac
                interp_lat = lat1 + (lat2 - lat1) * frac
                interp_z = z1 + (z2 - z1) * frac
                dense_coords.append((interp_lon, interp_lat, interp_z))
        dense_coords.append((lon2, lat2, z2))
    return dense_coords

def chaikin_smooth_3d(coords, iterations=2):
    smoothed = coords
    for _ in range(iterations):
        new_smoothed = [smoothed[0]]
        for i in range(len(smoothed) - 1):
            p0 = smoothed[i]
            p1 = smoothed[i+1]
            q = tuple(0.75 * p0[axis] + 0.25 * p1[axis] for axis in range(3))
            r = tuple(0.25 * p0[axis] + 0.75 * p1[axis] for axis in range(3))
            new_smoothed.append(q)
            new_smoothed.append(r)
        new_smoothed.append(smoothed[-1])
        smoothed = new_smoothed
    return smoothed

def process_graphhopper_geometry(gh_coords):
    coords = [(c[0], c[1], c[2]) for c in gh_coords]
    dense_coords = densify_route(coords, max_segment_meters=5.0)
    smooth_coords = chaikin_smooth_3d(dense_coords, iterations=2)
    return smooth_coords

def calculate_slope_profile(coords):
    distances = [0.0]
    slopes = [0.0]
    
    for i in range(1, len(coords)):
        lon1, lat1, z1 = coords[i-1]
        lon2, lat2, z2 = coords[i]
        d_2d = haversine(lon1, lat1, lon2, lat2)
        dz = z2 - z1
        
        distances.append(distances[-1] + d_2d)
        slope = math.degrees(math.atan2(dz, d_2d)) if d_2d > 0 else 0.0
        slopes.append(slope)
        
    return distances, slopes
