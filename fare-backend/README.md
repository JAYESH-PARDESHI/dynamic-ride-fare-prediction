# Dynamic Ride Fare Prediction – FastAPI backend

A deployment/integration layer around an **already-trained** XGBoost fare pipeline
(`fare_prediction_pipeline.pkl`). It does not train, change or replace the model.

> **Prototype.** The model was trained on a historical **Boston Uber/Lyft dataset**
> (12 neighbourhoods). It is *not* a universal Uber pricing model, and the surge
> multiplier here is a **simulation**, not Uber's/Lyft's real algorithm.

---

## 1. Overview

The rider picks **any real place in Boston** (search box or map click). The backend:

1. finds the **exact coordinates** (location search / reverse geocoding),
2. maps each point to one of the **12 areas the trained model understands** (real boundary data),
3. routes between the **exact coordinates** (OSRM), fetches **weather** there (Open-Meteo),
4. uses **Boston local time** for demand/surge, and
5. feeds the unchanged 14-column input to the unchanged XGBoost pipeline.

Exact coordinates and model categories serve different purposes and are never mixed up:
coordinates drive routing + weather + the map; the model category is only what the ML model sees
as `source` / `destination`.

## 2. Architecture

```
GET  /api/v1/locations/search?q=...                 GET /api/v1/locations/reverse?latitude=&longitude=
        │                                                    │
        ▼                                                    ▼
   GeocodingService (Nominatim, cached, 1 req/s)  ──►  LocationMappingService (offline, boundary polygons)
        │  real name + exact lat/lon                         │  neighbourhood + model area
        ▼                                                    ▼
                        POST /api/v2/fare/predict   (exact pickup + destination)
                                      │
                                      ▼
   FareService.predict_exact  (app/services/fare_service.py)
        │ 1  validate ride option, same-point check
        │ 2  LocationMappingService: exact coordinate → official neighbourhood → model area
        │       outside Boston → 422 · in Boston but not covered → 422 · same area → 422
        │ 3  RoutingService  (OSRM, EXACT coordinates) → distance, duration, road geometry   ┐ run
        │ 4  WeatherService  (Open-Meteo, EXACT pickup coordinates)                           ┘ together
        │ 5  Boston local time → DemandService → surge_multiplier
        │ 6  build ONE raw row (the same 14 columns as before; source/destination = model areas)
        ▼
   saved sklearn Pipeline (unchanged)  →  estimated_fare
```

```
app/
  main.py                          FastAPI app, routes, error handlers, CORS
  config.py                        settings from .env
  schemas.py                       request / response models (legacy + exact-coordinate)
  errors.py                        clean HTTP error types
  catalog.py                       model categories + ride options, read from the pipeline's encoders
  model_loader.py                  loads the pickle once at startup
  data/
    boston_neighborhoods.geojson   OFFICIAL City of Boston neighbourhood polygons (service area + 5 direct areas)
    model_area_refinements.geojson the 7 model areas that are not official neighbourhoods (see §9)
    model_area_mapping.json        official neighbourhood → model category (1:1 cases)
  services/
    location_mapping_service.py    exact coordinate → neighbourhood → model category   (NEW)
    geocoding_service.py           place search + reverse geocoding (Nominatim)        (NEW)
    routing_service.py             distance + duration + geometry (OSRM / OpenRouteService)
    weather_service.py             current weather in the model's training units
    demand_service.py              simulated demand → surge
    fare_service.py                orchestrates everything (predict_fare = legacy, predict_exact = new)
  utils/
    geometry.py                    dependency-free point-in-polygon                    (NEW)
    cache.py                       TTL cache (optionally size-bounded)
    time_features.py               model clock + Boston clock
project/transformer.py             DateTimeFeatureTransformer (package the pickle refers to - untouched)
models/                            fare_prediction_pipeline.pkl (untouched)
scripts/                           inspect_pipeline.py, check_golden.py
tests/                             pytest suite (no internet needed)
```

## 3. How the fare prediction works

* The pipeline expects **14 raw columns**: `distance, cab_type, destination, source,
  surge_multiplier, name, date_time, hour_date, temp, clouds, pressure, rain, humidity, wind`.
* Encoding, scaling, date features (`hour`, `day_of_week`, …) and feature selection all happen
  **inside** the pickle. The backend never one-hot-encodes anything itself.
* There is **no demand feature** in the model. Demand only decides `surge_multiplier`
  *before* prediction. Price is never used to compute surge (no target leakage).

Units sent to the model (taken from your training notebook):

| column | unit | how the backend gets it |
|---|---|---|
| distance | **miles** | route metres ÷ 1609.344 |
| temp | **°F** | provider asked for Fahrenheit |
| wind | **mph** | provider asked for mph |
| clouds, humidity | **fraction 0–1** | provider percent ÷ 100 |
| pressure | mb (hPa) | as returned |
| rain | **inches**, `NaN` when dry | no rain → `NaN` (the pipeline imputes 0 + adds a "missing" flag, exactly like training) |
| date_time | **UTC**, naive (switchable, see §10) | see §10 |

**Time-zone note:** see §10 - the model clock is UTC by default (what it was trained on); Boston
local time drives demand/surge and the `timestamp` in responses.

## 4. Installation

Python 3.13 is recommended (it is what you trained with). The ML library versions in
`requirements.txt` **must match** the ones that saved the pickle.

```bash
# Windows (PowerShell / cmd)
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env

# macOS / Linux
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## 5. Environment variables (`.env`)

| variable | default | meaning |
|---|---|---|
| `MODEL_PATH` | `models/fare_prediction_pipeline.pkl` | where the pickle is |
| `ROUTING_PROVIDER` | `osrm` | `osrm` (no key) or `openrouteservice` |
| `ROUTING_API_KEY` | – | only for openrouteservice |
| `ROUTING_BASE_URL` | public OSRM demo | override to use your own routing server |
| `WEATHER_PROVIDER` | `openmeteo` | `openmeteo` (no key) or `openweathermap` |
| `WEATHER_API_KEY` | – | only for openweathermap |
| `WEATHER_CACHE_SECONDS` | `600` | weather is cached per location |
| `HTTP_TIMEOUT_SECONDS` | `8` | timeout for routing / weather / geocoding calls |
| `GEOCODER_BASE_URL` | `https://nominatim.openstreetmap.org` | geocoding provider (use your own Nominatim for real traffic) |
| `GEOCODER_CONTACT` | – | **set this**: email/URL added to the User-Agent (Nominatim policy requires an identifying UA) |
| `GEOCODER_MIN_INTERVAL_SECONDS` | `1.0` | minimum gap between provider calls (policy: max 1 request/second) |
| `GEOCODER_MAX_QUEUE_SECONDS` | `4.0` | if a request would wait longer than this, answer HTTP 429 instead |
| `GEOCODER_CACHE_SECONDS` | `86400` | search + reverse results are cached this long |
| `GEOCODER_RESULT_LIMIT` | `8` | max search results returned |
| `MODEL_CLOCK` | `utc` | `utc` (what the model was trained on) or `boston` - see §10 before changing |
| `SURGE_CAB_TYPES` | `Uber,Lyft` | cab types that get simulated surge (others use 1.0) |
| `CORS_ALLOWED_ORIGINS` | localhost:3000, :5173 | comma-separated frontend origins |
| `APP_ENV`, `LOG_LEVEL` | `development`, `INFO` | |

Keys are never hard-coded, logged or returned to clients.
The free public OSRM server is meant for light/dev use only.

## 6. External services

| purpose | service | key? | notes |
|---|---|---|---|
| place search, reverse geocoding | **Nominatim** (OpenStreetMap) | no | Public server: max 1 req/s, identifying User-Agent (`GEOCODER_CONTACT`), cache results, no heavy autocomplete. The backend enforces spacing, caching and returns HTTP 429 rather than queueing without limit. Results carry the attribution `(c) OpenStreetMap contributors` - **the frontend must display it**. |
| routing + road geometry | **OSRM** (`router.project-osrm.org`) or OpenRouteService | no / yes | Public OSRM is a demo server for light use; set `ROUTING_BASE_URL` for your own. |
| weather | **Open-Meteo** or OpenWeatherMap | no / yes | Cached 10 min per ~100 m cell. |
| neighbourhood boundaries | files in `app/data/` (offline) | – | see §9 for provenance. No network at runtime. |

## 7. Model placement

```
fare-backend/
├── models/fare_prediction_pipeline.pkl     ← your saved pipeline
└── project/
    ├── __init__.py
    └── transformer.py                      ← DateTimeFeatureTransformer
```

**Why `project/` and not `transformer/`?** The pickle stores the class path
`project.transformer.DateTimeFeatureTransformer` (that is what your notebook imported).
The package must be called exactly `project`, with a module `transformer.py` inside.

**Use your original `transformer.py`.** The pickle holds only the class *name*; the code that
runs is whatever is in this file. The one provided is a reconstruction. Overwrite it with your
original file, then run the golden check (§14).

Always start the server **from the backend root folder** so `project` and `app` are importable.

## 8. Running

```bash
uvicorn app.main:app --reload
```

Docs UI: http://127.0.0.1:8000/docs · Health: http://127.0.0.1:8000/health

If the model fails to load, the server still starts and `/health` returns **503** with the reason.
The model is loaded once at startup, never per request.

## 9. Exact locations and model-area mapping

**Exact coordinates** are what the rider chose. They are never replaced by neighbourhood centres:
OSRM routes between them, Open-Meteo is queried at the pickup point, and the response echoes them back.

**Model area** is what the ML model sees as `source` / `destination`. It comes from
`LocationMappingService` (`app/services/location_mapping_service.py`), fully offline:

```
exact lat/lon ─► in the City of Boston?  ──no──► 422 outside_service_area
                      │ yes
                      ▼
        refinement polygon (7 areas) inside its parent neighbourhood?  ──yes──► that model area
                      │ no
                      ▼
        official neighbourhood with a 1:1 model area (5 areas)?        ──yes──► that model area
                      │ no
                      ▼
        422 location_not_mapped   (never "the nearest category")
```

| model area | how it is defined |
|---|---|
| Back Bay, Beacon Hill, North End, West End, Fenway | the **official City of Boston neighbourhood polygon** of the same name |
| Boston University, Northeastern University, South Station, North Station, Haymarket Square, Financial District, Theatre District | a **refinement polygon** (`model_area_refinements.geojson`) that only counts *inside* its parent official neighbourhood(s), e.g. the BU campus is carved out of the official "Fenway" polygon |

Examples: Copley Square → Back Bay · Fenway Park → Fenway · BU Marsh Chapel → Boston University ·
South Station → South Station.

**Be aware (please review):**

* The official polygons are the BPDA research division's *tract-based* neighbourhoods, so edges follow census tracts, not street centrelines.
* The model's categories are the dataset's own zone names and **have no published boundaries**. The 7 refinement areas are therefore **simple hand-drawn rectangles** that approximate well-known street limits, deliberately conservative, clipped to their parent neighbourhoods. They are not official data. Edit `app/data/model_area_refinements.geojson` if you have better definitions (the file is plain GeoJSON; `tests/test_location_mapping.py` pins the intended landmarks).
* Anything in Boston outside the 12 areas (Faneuil Hall, Downtown Crossing, Chinatown, South End, Jamaica Plain, Allston, Seaport, East Boston, ...) returns `location_not_mapped`. Logan Airport's terminal area is not in the boundary data and returns `outside_service_area`.
* Pickup and destination in the **same** model area return `same_model_area`: the model was trained only on trips between *different* areas, so pricing such a trip would be an extrapolation.
* Boundary source: `boston_neighborhoods.geojson` was taken from the `geoms/boston_neighborhoods_2020tract_2.geojson` file of github.com/bpda-research-division/neighborhood-change (City of Boston open data). Check the data licence for your use; that repository's *code* is GPL-2.0.

## 10. Boston local time

* The ride is in Boston, so **all time logic uses Boston time (`America/New_York`) computed on the server** - never the browser's time zone. The frontend sends no time at all.
* Pipeline: `server clock (UTC)` → `to_boston()` → demand score (hour, weekday/weekend, Friday evening) → surge → model. The response `timestamp` is Boston local time with its UTC offset (`-04:00` summer, `-05:00` winter; DST handled by `tzdata`).
* **Important finding:** the model's own time features (`hour`, `is_rush_hour`, `hour_sin/cos`, ...) are derived inside the pickle from the `date_time` column. The existing backend sends **UTC** there, because the training notebook built `date_time` from epoch milliseconds (UTC), so the model learned *UTC* hours. Sending Boston wall-clock time instead would shift every time feature by 4-5 hours relative to training.
* So by default (`MODEL_CLOCK=utc`) that behaviour is **preserved**; Boston time drives demand/surge and the response timestamp. If you have confirmed that your training data's `date_time` was Boston local time, set `MODEL_CLOCK=boston` and the model will receive Boston wall-clock time instead. (With the real pickle, one sample trip differed by about $0.02 between the two settings.)

## 11. Frontend API Contract

Base URL: `http://127.0.0.1:8000` (add the frontend's origin to `CORS_ALLOWED_ORIGINS`). All bodies are JSON, UTF-8.
Interactive docs: `/docs`. **Recommended flow:** search or map-click → exact coordinates → `POST /api/v2/fare/predict`.

### 11.1 Conventions

* **Coordinates**: decimal degrees (WGS84) as JSON numbers, always named `latitude` (−90…90) and `longitude` (−180…180). Boston ≈ `42.3, -71.1`.
* **Route geometry**: GeoJSON `LineString`, positions are **`[longitude, latitude]`** (GeoJSON order). Leaflet's `L.polyline` wants `[lat, lng]`, so swap: `coordinates.map(([lng, lat]) => [lat, lng])`, or use `L.geoJSON(geometry)` which handles it. Draw this line - do **not** draw a straight line between the markers.
* **Units**: distance in `miles`, duration in `minutes`, temperature °F, wind mph, pressure mb, rain inches, money in USD.
* **Boston timestamp**: ISO 8601 with offset, e.g. `2026-10-05T17:30:00-04:00`; `timezone` is always `America/New_York`. Parse with `new Date(ts)`; to *display Boston time* use `Intl.DateTimeFormat("en-US", {timeZone: "America/New_York", ...})`.
* **Ride types** (`cab_type` → allowed `name`, case-insensitive; the canonical spelling is echoed back). Always available live from `GET /api/v1/locations` → `cab_types`:
  * `Uber`: `UberPool`, `UberX`, `WAV`, `UberXL`, `Black`, `Black SUV`
  * `Lyft`: `Shared`, `Lyft`, `Lyft XL`, `Lux`, `Lux Black`, `Lux Black XL`
* **Errors** (all endpoints, never a stack trace): `{"error": {"code": "<machine_code>", "message": "<human text>"}}` - branch on `code`, show `message`.
* **Attribution**: show `(c) OpenStreetMap contributors` (returned as `attribution`) wherever search/reverse results or the map are shown.

### 11.2 Location search - `GET /api/v1/locations/search?q=<text>`

```bash
curl "http://127.0.0.1:8000/api/v1/locations/search?q=Copley%20Square"
```

```json
{
  "query": "Copley Square",
  "results": [
    {
      "display_name": "Copley Square, Back Bay, Boston, Suffolk County, Massachusetts, 02116, United States",
      "name": "Copley Square",
      "latitude": 42.3500,
      "longitude": -71.0773,
      "neighborhood": "Back Bay",
      "model_area": "Back Bay",
      "supported": true
    },
    {
      "display_name": "Jamaica Pond, Jamaica Plain, Boston, Massachusetts, United States",
      "name": "Jamaica Pond",
      "latitude": 42.3099,
      "longitude": -71.1130,
      "neighborhood": "Jamaica Plain",
      "model_area": null,
      "supported": false
    }
  ],
  "attribution": "(c) OpenStreetMap contributors"
}
```

* Only places inside the City of Boston are returned (the search is bounded to Boston, results are re-checked locally). `results` may be **empty** (HTTP 200) - show "no places found".
* `supported: false` means the place is in Boston but a fare cannot be predicted there: grey it out / explain, don't let it be selected as an endpoint.
* `q`: 2-200 characters, at least 2 letters/digits. **Debounce typing (≥ 400 ms, ≥ 3 characters), cancel in-flight requests, and search on Enter/click rather than on every keystroke** - the provider allows 1 request/second.
* Errors: `422 invalid_request` (empty/short/too long), `429 geocoding_rate_limited` (wait and retry), `502 geocoding_unavailable`, `504 geocoding_timeout`.

### 11.3 Reverse geocoding (map click) - `GET /api/v1/locations/reverse?latitude=<lat>&longitude=<lon>`

```bash
curl "http://127.0.0.1:8000/api/v1/locations/reverse?latitude=42.3500&longitude=-71.0773"
```

```json
{
  "display_name": "Copley Square, Back Bay, Boston, Suffolk County, Massachusetts, 02116, United States",
  "name": "Copley Square",
  "latitude": 42.35,
  "longitude": -71.0773,
  "neighborhood": "Back Bay",
  "model_area": "Back Bay",
  "supported": true,
  "message": null,
  "attribution": "(c) OpenStreetMap contributors"
}
```

* `latitude`/`longitude` in the response are **exactly the clicked point** (not snapped). Use them as the trip endpoint.
* If the point is in Boston but not covered by the model: `200` with `"supported": false, "model_area": null` and a human `message`.
* Errors: `422 outside_service_area` (click outside Boston - no provider call is made), `422 invalid_request`, `404 reverse_geocode_not_found` (nothing named there, e.g. open water), `429`, `502`, `504` as above.
* Click handling: take only the last click after a short pause (≥ 400 ms) and ignore stale responses.

### 11.4 Fare prediction - `POST /api/v2/fare/predict` (recommended)

Request:

```bash
curl -X POST http://127.0.0.1:8000/api/v2/fare/predict -H "Content-Type: application/json" -d '{
  "pickup":      {"latitude": 42.35012, "longitude": -71.07731, "display_name": "Copley Square, Boston, MA"},
  "destination": {"latitude": 42.34672, "longitude": -71.09722, "display_name": "Fenway Park, Boston, MA"},
  "cab_type": "Uber",
  "name": "UberX"
}'
```

| field | type | required | notes |
|---|---|---|---|
| `pickup.latitude` / `.longitude` | number | yes | exact point |
| `pickup.display_name` | string ≤ 300 | no | echoed back only (never used for pricing) |
| `destination.*` | same | yes | must differ from pickup (≥ 25 m) and be in a different model area |
| `cab_type` | string | yes | `Uber` or `Lyft` |
| `name` | string | yes | ride option for that company (see 11.1) |

Unknown fields are rejected (`422 invalid_request`). No time/weather/distance is accepted - the server computes them.

Response `200`:

```json
{
  "estimated_fare": 14.7,
  "currency": "USD",
  "cab_type": "Uber",
  "name": "UberX",
  "pickup": {
    "latitude": 42.35012, "longitude": -71.07731,
    "display_name": "Copley Square, Boston, MA",
    "neighborhood": "Back Bay",
    "model_area": "Back Bay"
  },
  "destination": {
    "latitude": 42.34672, "longitude": -71.09722,
    "display_name": null,
    "neighborhood": "Fenway",
    "model_area": "Fenway"
  },
  "route": {
    "distance": 2.4, "distance_unit": "miles",
    "duration": 11.5, "duration_unit": "minutes",
    "geometry": {
      "type": "LineString",
      "coordinates": [[-71.07731, 42.35012], [-71.087265, 42.34842], [-71.09722, 42.34672]]
    }
  },
  "surge_multiplier": 1.75,
  "demand_score": 0.736,
  "weather": {
    "temperature_f": 41.0, "cloud_cover_pct": 75.0, "humidity_pct": 80.0,
    "wind_mph": 7.5, "pressure_mb": 1012.0, "raining": false, "rain_inches": 0.0
  },
  "timestamp": "2026-10-05T17:30:00-04:00",
  "timezone": "America/New_York",
  "disclaimer": "Prototype estimate from a model trained on a historical Boston ride dataset. ..."
}
```

(Route geometry has many more points in a real response.) `pickup.model_area` / `destination.model_area` are the categories the model was given; `neighborhood` is the official Boston neighbourhood. `weather` is measured at the pickup point. `surge_multiplier` is **simulated** (one of 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0) - show the disclaimer.

### 11.5 Error responses

| HTTP | `error.code` | meaning / suggested UI |
|---|---|---|
| 422 | `invalid_request` | malformed/missing/extra fields, coordinates out of range, same point, empty search |
| 422 | `outside_service_area` | point is not inside the City of Boston |
| 422 | `location_not_mapped` | in Boston, but not one of the 12 model areas (message names the neighbourhood and the supported areas) |
| 422 | `same_model_area` | pickup and destination are in the same model area |
| 422 | `invalid_ride_option` | bad `cab_type` or `name` for that company |
| 422 | `route_not_found` | no driving route between the points |
| 404 | `reverse_geocode_not_found` | nothing found at the clicked point |
| 429 | `geocoding_rate_limited` | too many searches; retry shortly |
| 502 | `geocoding_unavailable` / `external_service_error` | search/routing/weather provider failed |
| 504 | `geocoding_timeout` / `external_service_timeout` | provider timed out |
| 503 | `model_unavailable` / `service_not_configured` | model not loaded / provider key missing (see `GET /health`) |
| 500 | `prediction_failed` / `internal_error` | server-side failure (details only in server logs) |

### 11.6 Other endpoints

* `GET /health` → `{"status": "ok", "model_loaded": true, "detail": null}` (`503` + reason if the model failed to load; search/reverse still work).
* `GET /api/v1/locations` → `{"sources": [...], "destinations": [...], "cab_types": {"Uber": [...], "Lyft": [...]}}` - the 12 **model** categories and ride options. Use `cab_types` for the ride picker; **do not** use the 12 categories as the location picker any more.

## 12. Legacy endpoint and migration

`POST /api/v1/fare/predict` (body `{source, destination, cab_type, name}` with the 12 category names) is
**unchanged and still works**, but is deprecated: it returns `Deprecation: true` and
`Link: </api/v2/fare/predict>; rel="successor-version"`, and OpenAPI marks it deprecated. It prices
trips between fixed neighbourhood centre points; its response (including its UTC `timestamp`) is
exactly as before. Migrate the frontend to `/api/v2/fare/predict`; the old endpoint can be removed
once nothing calls it.

Two small behaviour changes affect both endpoints: OSRM's "no route" answer is now `422 route_not_found`
(was a generic `502`), and the route cache is keyed by exact coordinates (identical results for the legacy fixed points).

## 13. Surge simulation (project-specific, NOT Uber's algorithm)

`app/services/demand_service.py`, fully deterministic:

1. **Time profile** – a 0–1 "busyness" value per hour of the day (Boston time), one profile for
   weekdays and one for weekends. Friday from 18:00 uses the weekend profile.
2. **Location bonus** – each neighbourhood has a *commute* weight (e.g. South Station) and a
   *leisure* weight (e.g. Theatre District). Commute counts in weekday rush windows, leisure in
   the evening/night. Pickup counts fully, drop-off half.
3. `score = time_profile + bonus` (0–1) → mapped by thresholds to **one of
   `1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0`** – never anything else.

With the current tuning about two thirds of (time, route) combinations give 1.0, commute peaks give
1.5–1.75, busy weekend nights up to 2.0. 2.5 and 3.0 exist in the mapping but are practically
unreachable. All numbers are constants at the top of the file – adjust freely.

## 14. Tests & verification

```bash
pip install -r requirements-dev.txt
pytest
```

The suite (no internet needed; Nominatim, OSRM and Open-Meteo are mocked) covers: coordinate validation,
location search, reverse geocoding (incl. caching, rate limiting, timeouts, provider errors), coordinate →
model-area mapping (Copley Square → Back Bay, Fenway Park → Fenway, campuses, outside/unmapped areas, all 12
categories reachable), exact-coordinate OSRM/ORS routing + geometry, weather lookup, Boston time and DST,
the UTC/Boston model-clock switch, the full prediction flow and the HTTP contract.
It uses a **stand-in pipeline** with the same structure as yours (`tests/dummy_pipeline.py`) - it only checks
the plumbing, never real fares. Mocked responses follow the providers' documented formats; they were **not**
checked against the live services, so do one manual run with the curl examples below.

Useful scripts (run from the backend root):

```bash
python -m scripts.inspect_pipeline     # shows what YOUR pickle expects + one sample prediction
python -m scripts.check_golden         # proves the backend reproduces your notebook's predictions
```

Smoke test against live services (needs internet):

```bash
curl "http://127.0.0.1:8000/api/v1/locations/search?q=Copley%20Square"
curl "http://127.0.0.1:8000/api/v1/locations/reverse?latitude=42.3500&longitude=-71.0773"
curl -X POST http://127.0.0.1:8000/api/v2/fare/predict -H "Content-Type: application/json" \
  -d '{"pickup":{"latitude":42.35012,"longitude":-71.07731},"destination":{"latitude":42.34672,"longitude":-71.09722},"cab_type":"Uber","name":"UberX"}'
```

## 15. Supported locations & limitations

Supported (read from your pipeline's encoders): Back Bay, Beacon Hill, Boston University, Fenway,
Financial District, Haymarket Square, North End, North Station, Northeastern University,
South Station, Theatre District, West End. Aliases: `BU`, `NEU`, `Northeastern`, `FiDi`, `Haymarket`.

* **Unknown locations are rejected, never guessed.** Your encoder uses `drop="first"` +
  `handle_unknown="ignore"`, so an unknown place would silently be priced as "Back Bay".
* Any real Boston place can now be chosen, but the model still only knows 12 areas: the exact point is
  mapped to one of them (§9) and anything else is refused. Truly new areas would need a retrained model.
* The model has seen **only Nov 26 – Dec 18, 2018**: winter temperatures (≈20–55 °F), and a
  day-of-month feature (`day`) from just those 3 weeks. Predictions in other seasons/dates are extrapolations.
* The 2018 prices are not today's prices.
* In the public version of this dataset, Uber rows may have `surge_multiplier == 1.0` only.
  If that is true for your data, set `SURGE_CAB_TYPES=Lyft` so Uber rides are not extrapolated.
* Distance is now the *road route between the exact points*, whereas the dataset used the apps'
  own neighbourhood-to-neighbourhood distance – differences are expected, especially for short trips
  within a large area.

