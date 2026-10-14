# 🚕 AI-Powered Dynamic Ride Fare Prediction System

![Python](https://img.shields.io/badge/Python-3.x-blue?logo=python&logoColor=white)
![XGBoost](https://img.shields.io/badge/XGBoost-Machine%20Learning-orange)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-Frontend-61DAFB?logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-Frontend-3178C6?logo=typescript&logoColor=white)
![Leaflet](https://img.shields.io/badge/Leaflet-Maps-199900?logo=leaflet&logoColor=white)
![Render](https://img.shields.io/badge/Deployed%20on-Render-46E3B7?logo=render&logoColor=black)

[![Live
Demo](https://img.shields.io/badge/Live%20Demo-Try%20Now-success)](https://dynamic-ride-fare-prediction-1.onrender.com)
[![GitHub
Repository](https://img.shields.io/badge/GitHub-Repository-black?logo=github)](https://github.com/JAYESH-PARDESHI/dynamic-ride-fare-prediction)

An end-to-end machine learning application that estimates ride fares
from trip distance, pickup and destination areas, cab type, time-related
features, weather conditions, and surge-related inputs.

The application combines an XGBoost regression pipeline with a FastAPI
backend and a React + TypeScript frontend. It integrates route
calculation, map-based location selection, geocoding, and weather data
to generate fare estimates for supported Boston-area locations.

**Author:** Jayesh Pardeshi

-   **Live application:**
    https://dynamic-ride-fare-prediction-1.onrender.com
-   **Backend API:** https://dynamic-ride-fare-prediction.onrender.com
-   **Interactive API documentation:**
    https://dynamic-ride-fare-prediction.onrender.com/docs
-   **Repository:**
    https://github.com/JAYESH-PARDESHI/dynamic-ride-fare-prediction

------------------------------------------------------------------------

## Table of Contents

-   [Project Overview](#project-overview)
-   [Key Features](#key-features)
-   [How It Works](#how-it-works)
-   [Machine Learning Workflow](#machine-learning-workflow)
-   [Model Configuration](#model-configuration)
-   [Model Evaluation](#model-evaluation)
-   [Technology Stack](#technology-stack)
-   [API Endpoints](#api-endpoints)
-   [Dataset Documentation](#dataset-documentation)
-   [Limitations](#limitations)
-   [Repository Structure](#repository-structure)
-   [Future Improvements](#future-improvements)
-   [Author](#author)

## Project Overview

Ride-hailing fares can vary with distance, pickup and destination, cab
category, time, weather, and demand-related conditions. This project
explores how machine learning can estimate a ride fare from historical
ride data and contextual features.

A user can select a pickup point and destination, calculate the route
distance, retrieve weather information, choose a cab type, and request a
fare estimate from the deployed application.

This is an educational and portfolio project. Its predictions are
estimates based on historical data, not guaranteed quotes from a
ride-hailing provider.

## Key Features

### Machine Learning

-   XGBoost regression pipeline for fare estimation.
-   Data preprocessing and feature engineering.
-   Time-based and cyclical time features.
-   Categorical feature encoding.
-   Feature selection.
-   Model comparison with Linear Regression, Ridge, Random Forest
    Regressor, and LightGBM Regressor.
-   Evaluation using regression metrics.

### Location and Routing

-   Search for pickup and destination locations.
-   Interactive map-based location selection.
-   Reverse geocoding for map coordinates.
-   Route-distance calculation using OSRM.
-   Mapping of real-world locations to areas supported by the trained
    model.
-   Unsupported-location handling when a location cannot be reliably
    mapped.

### Weather

-   Weather information retrieved through OpenWeatherMap.
-   Weather-related inputs supplied to the prediction workflow.

### Backend and Frontend

-   FastAPI REST API.
-   Serialized model pipeline loaded by the backend.
-   Request validation and error handling.
-   React, TypeScript, and Vite frontend.
-   Leaflet interactive map.

### Deployment

-   Frontend deployed on Render.
-   Backend deployed on Render.
-   API documentation available through Swagger UI at `/docs`.

## How It Works

1.  The user selects a pickup location and destination.
2.  The application resolves the selected locations.
3.  OSRM calculates the route and distance.
4.  The application retrieves weather information through
    OpenWeatherMap.
5.  The backend prepares the model inputs, including the applicable time
    and trip features.
6.  The trained preprocessing and XGBoost pipeline generates a fare
    estimate.
7.  The frontend displays the result.

The exact feature values and API behavior should be checked against the
current source code before making changes to the deployed system.

## Machine Learning Workflow

1.  **Load data:** Use the historical ride-fare dataset and weather
    dataset.
2.  **Merge data:** The project notes report a left join; the join keys
    and final row counts should be verified in the notebook.
3.  **Clean data:** Missing records were reported as dropped. Duplicate
    checks were performed; the user reported that no duplicates were
    found.
4.  **Feature engineering:** Reported time features include hour, day of
    week, day of month, month, weekend indicator, rush-hour indicator,
    and cyclical hour features (`hour_sin` / `hour_cos`).
5.  **Encode categorical variables:** One-hot and ordinal encoding were
    reported. Confirm the exact columns and transformer configuration in
    the notebook.
6.  **Scale numerical features:** StandardScaler was reported in the
    project notes. RobustScaler was also reported as having been used to
    reduce the influence of outliers. Verify which features use each
    scaler in the saved pipeline before treating this description as
    final.
7.  **Feature selection:** Feature selection was reported; the specific
    method and selected feature list need verification.
8.  **Train and compare models:** The final model is reported as XGBoost
    Regressor. Other models compared were Linear Regression, Ridge,
    Random Forest Regressor, and LightGBM Regressor.
9.  **Evaluate:** An 80/20 train-test split and cross-validation were
    reported. The exact cross-validation strategy and tuning process
    should be documented from the notebook.

## Model Configuration

The following XGBoost parameters were provided in the project notes:

``` text
n_estimators      = 500
learning_rate     = 0.05
max_depth         = 8
min_child_weight  = 2
subsample         = 0.8
colsample_bytree  = 0.8
objective         = reg:squarederror
random_state      = 42
n_jobs            = -1
```

Confirm these values against the estimator saved in the final pipeline
before publishing them as the definitive configuration.

## Model Evaluation

The following scores were supplied for the current README draft. **They
are provisional and must be checked against the notebook's final
held-out test-set output before being treated as verified results.**

  ------------------------------------------------------------------------
  Metric                              Reported value Interpretation
  --------------------- ---------------------------- ---------------------
  R²                                           0.962 Reported coefficient
                                                     of determination

  Adjusted R²                                  0.961 Calculation and
                                                     applicability need
                                                     verification

  MAE                                         \$1.13 Reported mean
                                                     absolute error

  RMSE                                        \$1.83 Reported root mean
                                                     squared error
  ------------------------------------------------------------------------

The reported train-test split is 80% training and 20% testing.
Cross-validation was reported as used, but its number of folds and
configuration are not yet confirmed. Hyperparameter tuning details are
also unverified.

For a regression problem, R², MAE, and RMSE are useful complementary
metrics. Adjusted R² is not a standard default metric for tree-based
models such as XGBoost; retain it only if its calculation is appropriate
and documented.

## Technology Stack

  -----------------------------------------------------------------------
  Area                                Technology
  ----------------------------------- -----------------------------------
  Programming language                Python

  Machine learning                    XGBoost, scikit-learn, LightGBM
                                      (reported for model comparison)

  Backend                             FastAPI

  Frontend                            React, TypeScript, Vite

  Maps                                Leaflet

  Routing                             OSRM

  Geocoding                           Nominatim / OpenStreetMap

  Weather                             OpenWeatherMap

  Hosting                             Render
  -----------------------------------------------------------------------

The exact package versions should be taken from the project's dependency
file.

## API Endpoints

The following endpoints were listed in the project notes. Verify their
current route definitions in the deployed API before changing this
table.

  -----------------------------------------------------------------------------
  Method                  Endpoint                      Description
  ----------------------- ----------------------------- -----------------------
  `GET`                   `/api/v1/locations/search`    Search for pickup or
                                                        destination locations

  `GET`                   `/api/v1/locations/reverse`   Reverse-geocode map
                                                        coordinates

  `POST`                  `/api/v2/fare/predict`        Generate a fare
                                                        prediction
  -----------------------------------------------------------------------------

**API documentation:** [Open Swagger
UI](https://dynamic-ride-fare-prediction.onrender.com/docs)

## Dataset Documentation

The model is described as trained on a publicly available Kaggle
ride-fare dataset covering Boston-area rides, combined with weather
data.

A separate dataset note is available at
[`docs/dataset_information.md`](docs/dataset_information.md). Dataset
dimensions have been reported by the project author but still need to be
reconciled with the notebook and saved preprocessing pipeline. See that
document for the values and verification notes.

## Limitations

-   The model uses historical Boston-area ride data and should only be
    used for locations supported by the model's training data and
    location-mapping logic.
-   Predicted fares can differ from actual ride-hailing prices.
-   Real fares can vary with demand, traffic, tolls, taxes, fees,
    provider-specific pricing, and other factors.
-   Weather, routing, and geocoding features depend on external services
    and their availability.
-   The application does not use an official Uber pricing API. Any Uber
    fare comparison is manual, if performed.
-   Model scores and dataset dimensions in this README are provisional
    until verified against the final notebook outputs.
-   Hyperparameter-tuning details, the exact cross-validation setup, and
    the precise scaler/feature-selection configuration still need
    verification.

## Repository Structure

The repository's latest folder structure has not yet been verified. The
following is a **suggested structure**, not a claim about the current
contents:

``` text
dynamic-ride-fare-prediction/
├── fare-backend/
├── fare-frontend-updated/
├── notebooks/
│   └── ride_fare_prediction.ipynb
│   
├── screenshots/
├── README.md
└── requirements.txt
```

Keep the notebook and dataset documentation paths in sync with the
actual repository. The notebook is reported to exist as
`ride_fare_prediction.ipynb` and needs cleaning/documentation.

## Future Improvements

-   Clean and organize the notebook into clear, reproducible sections.
-   Verify and document the dataset join keys, row counts,
    feature-selection method, and final pipeline transformations.
-   Record the exact cross-validation and hyperparameter-tuning setup.
-   Add automated tests for API validation and prediction behavior.
-   Add model monitoring and evaluate performance on newer data when
    suitable data becomes available.

## Author

**Jayesh Pardeshi**

-   GitHub: [JAYESH-PARDESHI](https://github.com/JAYESH-PARDESHI)

------------------------------------------------------------------------

*Documentation note: Items explicitly marked provisional or requiring
verification should be confirmed from the notebook, saved pipeline,
dependency files, and current repository before being presented as final
experimental results.*
