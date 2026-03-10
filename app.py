import math
import os
from collections import Counter
from datetime import datetime

import requests
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

POSTCODES_API = "https://api.postcodes.io/postcodes/{postcode}"
POLICE_API = "https://data.police.uk/api/crimes-street/all-crime"


def calculate_bbox(lat: float, lon: float, distance_m: float):
    earth_radius = 6378137.0
    dist_lat = distance_m / earth_radius
    dist_lon = distance_m / (earth_radius * math.cos(math.pi * lat / 180.0))

    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)

    lat_min = math.degrees(lat_rad - dist_lat)
    lat_max = math.degrees(lat_rad + dist_lat)
    lon_min = math.degrees(lon_rad - dist_lon)
    lon_max = math.degrees(lon_rad + dist_lon)

    return lat_min, lat_max, lon_min, lon_max


def geocode_postcode(postcode: str):
    url = POSTCODES_API.format(postcode=postcode.strip().replace(" ", ""))
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    payload = response.json()

    if payload.get("status") != 200 or not payload.get("result"):
        raise ValueError("Postcode not found")

    result = payload["result"]
    return {
        "latitude": result["latitude"],
        "longitude": result["longitude"],
        "normalized_postcode": result["postcode"],
    }


def fetch_crimes(lat: float, lon: float, date: str | None = None):
    params = {"lat": lat, "lng": lon}
    if date:
        params["date"] = date
    response = requests.get(POLICE_API, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


@app.route("/")
def index():
    return render_template("index.html")


@app.post("/api/analyze")
def analyze():
    body = request.get_json(silent=True) or {}
    postcode = str(body.get("postcode", "")).strip()
    radius = float(body.get("radius", 0))
    month = str(body.get("month", "")).strip() or None

    if not postcode:
        return jsonify({"error": "Вкажіть UK postcode."}), 400
    if radius <= 0:
        return jsonify({"error": "Радіус має бути > 0."}), 400
    if radius > 1000:
        return jsonify({"error": "Радіус має бути <= 1000 м (обмеження Police API)."}), 400

    try:
        center = geocode_postcode(postcode)
    except requests.HTTPError:
        return jsonify({"error": "Не вдалося знайти такий postcode."}), 404
    except Exception:
        return jsonify({"error": "Помилка геокодування postcode."}), 500

    lat = center["latitude"]
    lon = center["longitude"]

    try:
        crimes = fetch_crimes(lat, lon, month)
    except Exception:
        return jsonify({"error": "Помилка отримання даних з data.police.uk."}), 502

    lat_min, lat_max, lon_min, lon_max = calculate_bbox(lat, lon, radius)

    filtered = []
    for item in crimes:
        location = item.get("location") or {}
        item_lat = location.get("latitude")
        item_lon = location.get("longitude")
        if item_lat is None or item_lon is None:
            continue
        c_lat = float(item_lat)
        c_lon = float(item_lon)
        if lat_min <= c_lat <= lat_max and lon_min <= c_lon <= lon_max:
            filtered.append(item)

    categories = [crime.get("category", "unknown") for crime in filtered]
    category_counts = Counter(categories)

    monthly_counts = Counter()
    for crime in filtered:
        month_value = crime.get("month")
        if month_value:
            monthly_counts[month_value] += 1

    heat_points = []
    for crime in filtered:
        location = crime.get("location")
        if not location:
            continue
        heat_points.append(
            {
                "lat": float(location["latitude"]),
                "lng": float(location["longitude"]),
                "category": crime.get("category", "unknown"),
                "street": (location.get("street") or {}).get("name", "Unknown street"),
                "month": crime.get("month"),
                "outcome": (crime.get("outcome_status") or {}).get("category", "No outcome"),
            }
        )

    top_categories = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    return jsonify(
        {
            "postcode": center["normalized_postcode"],
            "center": {"lat": lat, "lng": lon},
            "radius": radius,
            "total_crimes": len(filtered),
            "top_categories": [{"name": name, "count": count} for name, count in top_categories],
            "all_categories": dict(category_counts),
            "monthly_counts": dict(sorted(monthly_counts.items(), key=lambda x: datetime.strptime(x[0], "%Y-%m"))),
            "points": heat_points,
        }
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
