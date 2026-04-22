import math
import os
import ipaddress
import json
import time
from collections import Counter, deque
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

POSTCODES_API = "https://api.postcodes.io/postcodes/{postcode}"
POLICE_API = "https://data.police.uk/api/crimes-street/all-crime"
REQUEST_DELAY_SECONDS = float(os.environ.get("POLICE_API_REQUEST_DELAY_SECONDS", "0.07"))
MAX_RETRIES_429 = int(os.environ.get("POLICE_API_MAX_RETRIES_429", "5"))
BACKOFF_BASE_SECONDS = float(os.environ.get("POLICE_API_BACKOFF_BASE_SECONDS", "0.5"))
BACKOFF_MAX_SECONDS = float(os.environ.get("POLICE_API_BACKOFF_MAX_SECONDS", "8"))
ADMIN_PANEL_KEY = os.environ.get("ADMIN_PANEL_KEY", "change-me")
VISITOR_LOG_LIMIT = 1000
visitor_log = deque(maxlen=VISITOR_LOG_LIMIT)
ip_location_cache: dict[str, dict] = {}
REQUEST_CONTENT_LIMIT = 1200


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


def parse_retry_after(header_value: str | None) -> float | None:
    if not header_value:
        return None

    stripped = header_value.strip()
    try:
        return max(0.0, float(stripped))
    except ValueError:
        pass

    try:
        retry_dt = parsedate_to_datetime(stripped)
        if retry_dt.tzinfo is None:
            retry_dt = retry_dt.replace(tzinfo=timezone.utc)
        now_utc = datetime.now(timezone.utc)
        return max(0.0, (retry_dt - now_utc).total_seconds())
    except Exception:
        return None


def fetch_crimes_with_retry(lat: float, lon: float, date: str | None = None):
    attempt = 0
    while True:
        try:
            return fetch_crimes(lat, lon, date)
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code != 429 or attempt >= MAX_RETRIES_429:
                raise

            retry_after = parse_retry_after(exc.response.headers.get("Retry-After") if exc.response else None)
            if retry_after is None:
                retry_after = min(BACKOFF_MAX_SECONDS, BACKOFF_BASE_SECONDS * (2 ** attempt))
            time.sleep(retry_after)
            attempt += 1
        except requests.RequestException:
            if attempt >= MAX_RETRIES_429:
                raise
            backoff = min(BACKOFF_MAX_SECONDS, BACKOFF_BASE_SECONDS * (2 ** attempt))
            time.sleep(backoff)
            attempt += 1


def get_client_ip() -> str:
    cf_connecting_ip = request.headers.get("CF-Connecting-IP", "").strip()
    if cf_connecting_ip:
        return cf_connecting_ip

    x_real_ip = request.headers.get("X-Real-IP", "").strip()
    if x_real_ip:
        return x_real_ip

    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def resolve_ip_location(ip: str) -> dict:
    if not ip or ip == "unknown":
        return {"country": "Unknown", "lat": None, "lng": None}

    if ip in ip_location_cache:
        return ip_location_cache[ip]

    try:
        parsed = ipaddress.ip_address(ip)
        if parsed.is_private or parsed.is_loopback or parsed.is_link_local:
            location = {"country": "Local/Private Network", "lat": None, "lng": None}
            ip_location_cache[ip] = location
            return location
    except ValueError:
        location = {"country": "Unknown", "lat": None, "lng": None}
        ip_location_cache[ip] = location
        return location

    location = {"country": "Unknown", "lat": None, "lng": None}

    providers = [
        f"https://ipwho.is/{ip}",
        f"https://ipapi.co/{ip}/json/",
    ]

    for provider_url in providers:
        try:
            response = requests.get(provider_url, timeout=5)
            response.raise_for_status()
            payload = response.json()

            if "ipwho.is" in provider_url:
                if not payload.get("success", False):
                    continue
                location = {
                    "country": payload.get("country") or "Unknown",
                    "lat": payload.get("latitude"),
                    "lng": payload.get("longitude"),
                }
                break

            location = {
                "country": payload.get("country_name") or "Unknown",
                "lat": payload.get("latitude"),
                "lng": payload.get("longitude"),
            }
            break
        except Exception:
            continue

    ip_location_cache[ip] = location
    return location


def extract_request_content() -> str:
    if request.method not in {"POST", "PUT", "PATCH"}:
        return "-"

    payload = request.get_json(silent=True)
    if payload is not None:
        content = json.dumps(payload, ensure_ascii=False)
    else:
        raw_data = request.get_data(cache=True, as_text=True) or ""
        content = raw_data if raw_data else "-"

    if len(content) > REQUEST_CONTENT_LIMIT:
        return f"{content[:REQUEST_CONTENT_LIMIT]}... [truncated]"
    return content


@app.before_request
def log_visitor():
    if request.path.startswith("/static/"):
        return

    ip = get_client_ip()
    location = resolve_ip_location(ip)
    visitor_log.append(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ip": ip,
            "country": location["country"],
            "lat": location["lat"],
            "lng": location["lng"],
            "method": request.method,
            "path": request.path,
            "request_content": extract_request_content(),
            "user_agent": request.user_agent.string or "unknown",
            "accept_language": request.headers.get("Accept-Language", "unknown"),
            "referer": request.headers.get("Referer", "direct"),
        }
    )


def parse_month(month: str) -> datetime:
    return datetime.strptime(month, "%Y-%m")


def month_range(start_month: str, end_month: str) -> list[str]:
    start = parse_month(start_month)
    end = parse_month(end_month)
    if start > end:
        raise ValueError("Start month must be earlier than or equal to end month.")

    result = []
    current = start
    while current <= end:
        result.append(current.strftime("%Y-%m"))
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)
    return result


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/internal/admin")
def admin_panel():
    key = request.args.get("key", "")
    if key != ADMIN_PANEL_KEY:
        return jsonify({"error": "Not found"}), 404

    visits = list(visitor_log)
    unique_ips = len({visit["ip"] for visit in visits})
    path_counts = Counter(visit["path"] for visit in visits)
    country_counts = Counter(visit["country"] for visit in visits)
    map_points = [
        {"lat": visit["lat"], "lng": visit["lng"], "ip": visit["ip"], "country": visit["country"]}
        for visit in visits
        if visit["lat"] is not None and visit["lng"] is not None
    ]

    return render_template(
        "admin.html",
        visits=reversed(visits),
        total_visits=len(visits),
        unique_ips=unique_ips,
        path_counts=path_counts,
        country_counts=country_counts,
        map_points=map_points,
    )


@app.post("/api/analyze")
def analyze():
    body = request.get_json(silent=True) or {}
    postcode = str(body.get("postcode", "")).strip()
    radius = float(body.get("radius", 0))
    start_month = str(body.get("start_month", "")).strip() or None
    end_month = str(body.get("end_month", "")).strip() or None

    if not postcode:
        return jsonify({"error": "Please provide a UK postcode."}), 400
    if radius <= 0:
        return jsonify({"error": "Radius must be greater than 0."}), 400
    if radius > 1000:
        return jsonify({"error": "Radius must be <= 1000 meters (Police API limit)."}), 400
    if (start_month and not end_month) or (end_month and not start_month):
        return jsonify({"error": "Please provide both start and end month."}), 400

    requested_months = []
    if start_month and end_month:
        try:
            requested_months = month_range(start_month, end_month)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    try:
        center = geocode_postcode(postcode)
    except requests.HTTPError:
        return jsonify({"error": "Postcode was not found."}), 404
    except Exception:
        return jsonify({"error": "Postcode geocoding failed."}), 500

    lat = center["latitude"]
    lon = center["longitude"]

    try:
        if requested_months:
            crimes = []
            for idx, month in enumerate(requested_months):
                crimes.extend(fetch_crimes_with_retry(lat, lon, month))
                if REQUEST_DELAY_SECONDS > 0 and idx < len(requested_months) - 1:
                    time.sleep(REQUEST_DELAY_SECONDS)
        else:
            crimes = fetch_crimes_with_retry(lat, lon)
    except Exception as exc:
        return jsonify({"error": f"Failed to fetch data from data.police.uk. Reason: {exc}"}), 502

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
            "period": {"start_month": start_month, "end_month": end_month},
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
