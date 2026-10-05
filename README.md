# 🚕 AI-Powered Dynamic Ride Fare Prediction System

![Python](https://img.shields.io/badge/Python-3.x-blue?logo=python&logoColor=white)
![XGBoost](https://img.shields.io/badge/XGBoost-Machine%20Learning-orange)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-Frontend-61DAFB?logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-Frontend-3178C6?logo=typescript&logoColor=white)
![Leaflet](https://img.shields.io/badge/Leaflet-Maps-199900?logo=leaflet&logoColor=white)
![Render](https://img.shields.io/badge/Deployed%20on-Render-46E3B7?logo=render&logoColor=black)

[![Live Demo](https://img.shields.io/badge/Live%20Demo-Try%20Now-success)](https://dynamic-ride-fare-prediction-1.onrender.com)
[![GitHub](https://img.shields.io/badge/GitHub-Repository-black?logo=github)](https://github.com/JAYESH-PARDESHI/dynamic-ride-fare-prediction)

An end-to-end machine learning application that predicts ride fares using trip distance, location, cab type, time, weather conditions, and surge-related features.

The project combines a trained XGBoost regression model with a FastAPI backend, React frontend, interactive maps, routing, weather data, and geographic location-mapping logic to provide real-time fare predictions.

🔗 **Live Demo:** https://dynamic-ride-fare-prediction-1.onrender.com

🔗 **Backend API:** https://dynamic-ride-fare-prediction.onrender.com

---

## 📌 Project Overview

Ride-hailing platforms use multiple factors to determine the price of a trip. This project aims to build an ML-based system that estimates ride fares based on trip and environmental conditions.

The system allows a user to:

1. Select a pickup location.
2. Select a destination.
3. Calculate the route and distance.
4. Retrieve current weather information.
5. Select a cab type.
6. Generate a fare prediction using the trained ML pipeline.
7. View the predicted fare through a web interface.
8. Optionally compare the prediction with an Uber app quote.

The application is fully deployed with a React frontend and FastAPI backend.

---

## ✨ Key Features

### 🤖 Machine Learning

- XGBoost regression model for fare prediction.
- End-to-end preprocessing pipeline.
- Feature engineering for date/time information.
- Categorical feature processing.
- Surge-related fare modeling.
- Evaluation using MAE, RMSE, and R².

### 📍 Location Intelligence

- Search locations using real-world addresses.
- Interactive map-based location selection.
- Reverse geocoding for map clicks.
- Geographic validation of selected locations.
- Mapping of real-world coordinates to supported model areas.
- Prevents predictions when a location cannot be reliably mapped to a supported model area.

### 🗺️ Routing

- OSRM-based route calculation.
- Automatic pickup-to-destination distance calculation.
- Interactive map visualization.

### 🌦️ Weather Integration

- Retrieves weather information for the selected location.
- Uses weather-related features as model inputs.

### ⚡ Backend

- FastAPI REST API.
- Model loaded through a serialized ML pipeline.
- Input validation.
- Location search and reverse-geocoding APIs.
- Prediction API.
- Error handling and unsupported-location handling.

### 💻 Frontend

- React + TypeScript + Vite.
- Interactive Leaflet map.
- Pickup and destination search.
- Location suggestions.
- Prediction results.
- Dynamic fare visualization.

### ☁️ Deployment

- Frontend deployed on Render.
- Backend deployed on Render.
- Production API communication between frontend and backend.

---

# 🧠 Machine Learning Model

The project uses an **XGBoost Regressor** trained on a publicly available Kaggle ride-fare dataset containing approximately **600K+ historical ride records**.

### Model Configuration

```text
n_estimators      = 500
learning_rate     = 0.05
max_depth         = 8
min_child_weight  = 2
subsample         = 0.8
colsample_bytree  = 0.8
objective         = reg:squarederror
random_state      = 42
n_jobs            = -1

### 📊 Model Performance

-- The model was evaluated on a held-out test set.

- Metric Score
- R² : 0.962
- Adjusted R² : 0.961
- MAE :	$1.13
- RMSE : $1.83

## 🔌 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/locations/search` | Search for pickup or destination locations |
| `GET` | `/api/v1/locations/reverse` | Convert map coordinates into a location |
| `POST` | `/api/v2/fare/predict` | Predict ride fare using the trained ML model |

### 📚 API Documentation

[Dynamic Ride Fare Prediction API - Swagger UI](https://dynamic-ride-fare-prediction.onrender.com/docs)
