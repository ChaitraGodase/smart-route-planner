import os
import re
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pathlib import Path
from pydantic import BaseModel
import httpx
try:
    from .smoothing import calculate_slope_profile
    from .intelligence import EnvironmentalAI
except ImportError:
    from smoothing import calculate_slope_profile
    from intelligence import EnvironmentalAI

# --- LOAD ENVIRONMENT VARIABLES ---
load_dotenv()

app = FastAPI(title="GraphHopper AI Routing System")

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# --- GET API KEY SECURELY FROM .ENV ---
GRAPHHOPPER_API_KEY = os.getenv("GRAPHHOPPER_API_KEY")
GRAPHHOPPER_PROFILES = {"car", "bike", "foot"}

class RouteRequest(BaseModel):
    start_loc: str
    end_loc: str
    vehicle_type: str = "car"


def format_duration(total_seconds: float) -> str:
    total_minutes = max(1, round(total_seconds / 60))
    hours, minutes = divmod(total_minutes, 60)
    if hours and minutes:
        return f"{hours} hr {minutes} min"
    if hours:
        return f"{hours} hr"
    return f"{minutes} min"


def parse_coordinates(value: str):
    match = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*", value)
    if not match:
        return None

    first = float(match.group(1))
    second = float(match.group(2))

    if -90 <= first <= 90 and -180 <= second <= 180:
        return {"lat": first, "lng": second, "name": f"{first}, {second}"}
    if -180 <= first <= 180 and -90 <= second <= 90:
        return {"lat": second, "lng": first, "name": f"{second}, {first}"}
    return None


async def geocode_location(client: httpx.AsyncClient, query: str) -> dict:
    coords = parse_coordinates(query)
    if coords:
        return coords

    response = await client.get(
        "https://graphhopper.com/api/1/geocode",
        params={
            "q": query,
            "limit": 1,
            "locale": "en",
            "key": GRAPHHOPPER_API_KEY,
        },
    )

    if response.status_code != 200:
        try:
            message = response.json().get("message", "GraphHopper geocoding failed.")
        except ValueError:
            message = "GraphHopper geocoding failed."
        raise HTTPException(status_code=400, detail=message)

    hits = response.json().get("hits", [])
    if not hits:
        raise HTTPException(status_code=404, detail=f"Could not find location: {query}")

    hit = hits[0]
    point = hit.get("point") or {}
    if "lat" not in point or "lng" not in point:
        raise HTTPException(status_code=502, detail="GraphHopper returned an unexpected geocoding format.")

    parts = [hit.get("name"), hit.get("city"), hit.get("state"), hit.get("country")]
    name = ", ".join(dict.fromkeys(part for part in parts if part))
    return {"lat": point["lat"], "lng": point["lng"], "name": name or query}


@app.get("/", response_class=HTMLResponse)
def read_root():
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))

@app.post("/api/route")
async def generate_smart_route(req: RouteRequest):
    if not GRAPHHOPPER_API_KEY:
        raise HTTPException(status_code=500, detail="GraphHopper API key is missing. Check your .env file.")

    if req.vehicle_type not in GRAPHHOPPER_PROFILES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"GraphHopper profile '{req.vehicle_type}' is not enabled for this API key. "
                f"Use one of: {', '.join(sorted(GRAPHHOPPER_PROFILES))}."
            ),
        )

    routing_profile = req.vehicle_type

    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. Geocoding: use GraphHopper so text matches GraphHopper's route website behavior.
        start_point = await geocode_location(client, req.start_loc)
        end_point = await geocode_location(client, req.end_loc)

        # 2. Call GraphHopper API with Real Elevation
        gh_url = "https://graphhopper.com/api/1/route"
        params = {
            "point": [f"{start_point['lat']},{start_point['lng']}", f"{end_point['lat']},{end_point['lng']}"],
            "profile": routing_profile,
            "elevation": "true",
            "key": GRAPHHOPPER_API_KEY,
            "geometry_format": "geojson",
            "points_encoded": "false"
        }

        response = await client.get(gh_url, params=params)
        if response.status_code != 200:
            try:
                gh_error = response.json().get("message", "GraphHopper routing failed.")
            except ValueError:
                gh_error = "GraphHopper routing failed."
            raise HTTPException(status_code=400, detail=gh_error)
        gh_data = response.json()

    # 3. Extract Raw 3D Coordinates
    try:
        route_path = gh_data["paths"][0]
        raw_coords = route_path["points"]["coordinates"]
    except (KeyError, IndexError, TypeError):
        raise HTTPException(status_code=502, detail="GraphHopper returned an unexpected route format.")

    travel_time_ms = route_path.get("time", 0)
    travel_time_seconds = travel_time_ms / 1000
    
    # 4. Use raw GraphHopper geometry so the map follows the road route exactly.
    route_coords = [(c[0], c[1], c[2] if len(c) > 2 else 0) for c in raw_coords]
    distances, slopes = calculate_slope_profile(route_coords)
    
    # 5. AI Intelligence
    weather = EnvironmentalAI.generate_weather_mock()
    weather_risk = EnvironmentalAI.get_weather_risk(weather)
    terrain_risk = EnvironmentalAI.get_terrain_risk(slopes, req.vehicle_type)
    
    total_risk = min((weather_risk * 0.4) + (terrain_risk["risk_score"] * 0.6), 1.0)

    # 6. Format GeoJSON
    geojson_line = {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": [[c[0], c[1], c[2]] for c in route_coords]
        },
        "properties": {
            "smoothed": False,
            "requested_profile": req.vehicle_type,
            "routing_profile": routing_profile,
            "start": start_point,
            "end": end_point
        }
    }

    return {
        "geojson": geojson_line,
        "elevation_profile": {
            "distances": distances,
            "elevations": [c[2] for c in route_coords],
            "slopes": slopes
        },
        "analytics": {
            "total_distance_m": distances[-1],
            "travel_time_ms": travel_time_ms,
            "travel_time_seconds": travel_time_seconds,
            "travel_time_text": format_duration(travel_time_seconds),
            "weather": weather,
            "weather_risk": weather_risk,
            "terrain_analysis": terrain_risk,
            "overall_risk_score": total_risk,
            "requested_profile": req.vehicle_type,
            "routing_profile": routing_profile,
            "start": start_point,
            "end": end_point,
            "vehicle_suitability": "Suitable" if total_risk < 0.4 else "Caution Advised"
        }
    }

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
