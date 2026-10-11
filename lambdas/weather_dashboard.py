"""Weather Dashboard Lambda.

Routes (Lambda Function URL, payload v2):
    GET /              -> HTML dashboard
    GET /api/weather   -> ?city=London&units=metric|imperial
    GET /api/history   -> recent searches

Weather data comes from Open-Meteo (no API key required).
"""
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HTTP_TIMEOUT = 8
HISTORY_TTL_SECONDS = 30 * 24 * 3600
HISTORY_PK = "SEARCH"

_table = None


class CityNotFound(Exception):
    pass


class BadRequest(Exception):
    pass


class UpstreamError(Exception):
    pass


WEATHER_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    56: "Freezing drizzle", 57: "Heavy freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain",
    66: "Freezing rain", 67: "Heavy freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Light showers", 81: "Showers", 82: "Violent showers",
    85: "Snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Severe thunderstorm with hail",
}


def _get_table():
    global _table
    if _table is None:
        _table = boto3.resource("dynamodb").Table(os.environ["HISTORY_TABLE_NAME"])
    return _table


def _fetch_json(url, params):
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(full_url, timeout=HTTP_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.error("Upstream call failed: %s (%s)", url, exc)
        raise UpstreamError("Weather provider is unavailable") from exc


def geocode(city):
    data = _fetch_json(GEOCODE_URL, {"name": city, "count": 1, "language": "en", "format": "json"})
    results = data.get("results") or []
    if not results:
        raise CityNotFound(f"City '{city}' not found")
    top = results[0]
    return {
        "name": top["name"],
        "country": top.get("country", ""),
        "latitude": top["latitude"],
        "longitude": top["longitude"],
    }


def get_weather(city, units):
    place = geocode(city)
    imperial = units == "imperial"
    data = _fetch_json(FORECAST_URL, {
        "latitude": place["latitude"],
        "longitude": place["longitude"],
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,"
                   "weather_code,wind_speed_10m,pressure_msl",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum",
        "forecast_days": 5,
        "timezone": "auto",
        "temperature_unit": "fahrenheit" if imperial else "celsius",
        "wind_speed_unit": "mph" if imperial else "kmh",
    })

    cur = data["current"]
    daily = data["daily"]
    forecast = [
        {
            "date": daily["time"][i],
            "summary": WEATHER_CODES.get(daily["weather_code"][i], "Unknown"),
            "tempMax": daily["temperature_2m_max"][i],
            "tempMin": daily["temperature_2m_min"][i],
            "precipitationMm": daily["precipitation_sum"][i],
        }
        for i in range(len(daily["time"]))
    ]

    return {
        "city": place["name"],
        "country": place["country"],
        "units": "imperial" if imperial else "metric",
        "current": {
            "temperature": cur["temperature_2m"],
            "feelsLike": cur["apparent_temperature"],
            "humidity": cur["relative_humidity_2m"],
            "windSpeed": cur["wind_speed_10m"],
            "pressureHpa": cur["pressure_msl"],
            "summary": WEATHER_CODES.get(cur["weather_code"], "Unknown"),
            "observedAt": cur["time"],
        },
        "forecast": forecast,
    }


def save_search(result):
    now = int(time.time())
    _get_table().put_item(Item={
        "pk": HISTORY_PK,
        "ts": now,
        "city": result["city"],
        "country": result["country"],
        "temperature": Decimal(str(result["current"]["temperature"])),
        "units": result["units"],
        "summary": result["current"]["summary"],
        "expiresAt": now + HISTORY_TTL_SECONDS,
    })


def get_history(limit=10):
    resp = _get_table().query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key("pk").eq(HISTORY_PK),
        ScanIndexForward=False,
        Limit=limit,
    )
    return [
        {
            "city": i["city"],
            "country": i["country"],
            "temperature": float(i["temperature"]),
            "units": i["units"],
            "summary": i["summary"],
            "searchedAt": int(i["ts"]),
        }
        for i in resp["Items"]
    ]


def _json_response(status, body):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "Cache-Control": "no-store"},
        "body": json.dumps(body),
    }


def _html_response():
    path = os.path.join(os.path.dirname(__file__), "dashboard.html")
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "text/html; charset=utf-8"},
        "body": html,
    }


def lambda_handler(event, context):
    http = event.get("requestContext", {}).get("http", {})
    method = http.get("method", "GET")
    path = event.get("rawPath", "/")
    params = event.get("queryStringParameters") or {}

    logger.info("Request: %s %s", method, path)

    if method != "GET":
        return _json_response(405, {"error": "Method not allowed"})

    try:
        if path == "/":
            return _html_response()

        if path == "/api/weather":
            city = (params.get("city") or "").strip()
            units = (params.get("units") or "metric").lower()
            if not city or len(city) > 100:
                raise BadRequest("Query parameter 'city' is required (max 100 chars)")
            if units not in ("metric", "imperial"):
                raise BadRequest("'units' must be 'metric' or 'imperial'")
            result = get_weather(city, units)
            save_search(result)
            return _json_response(200, result)

        if path == "/api/history":
            return _json_response(200, {"history": get_history()})

        return _json_response(404, {"error": "Not found"})

    except BadRequest as exc:
        return _json_response(400, {"error": str(exc)})
    except CityNotFound as exc:
        return _json_response(404, {"error": str(exc)})
    except UpstreamError as exc:
        return _json_response(502, {"error": str(exc)})
    # Anything unexpected is deliberately NOT caught: the invocation fails
    # visibly (and is logged/alarmable) instead of being masked as success.
