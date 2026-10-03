# RideFlow – Frontend

    npm install
    npm run dev        # http://localhost:5173

Set `VITE_API_BASE_URL` in `.env` (see `.env.example`, default `http://127.0.0.1:8000`).

Uses Leaflet + OpenStreetMap tiles (no map API key). Endpoints used:
`GET /api/v1/locations/search`, `GET /api/v1/locations/reverse`, `POST /api/v2/fare/predict`.

`src/services/normalize.ts` is the single place that maps the fare response (fare, distance, duration,
surge, weather, route geometry) to the UI. If a field name differs from what it expects, adjust it there.
