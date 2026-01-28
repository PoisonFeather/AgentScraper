import math
import requests
from config import settings

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p = math.pi / 180.0
    dlat = (lat2-lat1)*p
    dlon = (lon2-lon1)*p
    a = (math.sin(dlat/2)**2 +
         math.cos(lat1*p)*math.cos(lat2*p)*math.sin(dlon/2)**2)
    c = 2*math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R*c

def geocode_nominatim(place: str):
    # Fallback ONLY if OLX page doesn't expose coordinates.
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": place, "format": "json", "limit": 1},
            headers={"User-Agent": settings.USER_AGENT},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        if not data:
            return None
        return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        return None

def distance_from_cluj(lat, lon):
    if lat is None or lon is None:
        return None
    return haversine_km(settings.CLUJ_LAT, settings.CLUJ_LON, lat, lon)