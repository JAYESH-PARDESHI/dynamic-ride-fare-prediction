"""Application errors. Each one maps to a clean HTTP response (see main.py).

Messages here are shown to API clients, so they must never contain API keys,
stack traces or raw upstream responses.
"""


class AppError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class UnsupportedLocationError(AppError):
    status_code = 422
    code = "unsupported_location"


class InvalidRideOptionError(AppError):
    status_code = 422
    code = "invalid_ride_option"


class InvalidRequestError(AppError):
    status_code = 422
    code = "invalid_request"


class ConfigurationError(AppError):
    """Missing/invalid server configuration (e.g. API key not set)."""

    status_code = 503
    code = "service_not_configured"


class ModelUnavailableError(AppError):
    status_code = 503
    code = "model_unavailable"


class ExternalServiceError(AppError):
    status_code = 502
    code = "external_service_error"


class ExternalTimeoutError(AppError):
    status_code = 504
    code = "external_service_timeout"


class PredictionError(AppError):
    status_code = 500
    code = "prediction_failed"


class ModelLoadError(Exception):
    """Raised while loading the pickle at startup (not an HTTP error itself)."""


# ---- exact-location / geocoding errors ----------------------------------------
class OutsideServiceAreaError(AppError):
    """The coordinate is not inside the City of Boston service area."""

    status_code = 422
    code = "outside_service_area"


class LocationNotMappedError(AppError):
    """Inside Boston, but not safely mappable to one of the model's areas."""

    status_code = 422
    code = "location_not_mapped"


class SameModelAreaError(AppError):
    """Pickup and destination fall in the same model area."""

    status_code = 422
    code = "same_model_area"


class ReverseGeocodeNotFoundError(AppError):
    status_code = 404
    code = "reverse_geocode_not_found"


class GeocodingUnavailableError(AppError):
    status_code = 502
    code = "geocoding_unavailable"


class GeocodingTimeoutError(AppError):
    status_code = 504
    code = "geocoding_timeout"


class GeocodingRateLimitedError(AppError):
    status_code = 429
    code = "geocoding_rate_limited"


class RouteNotFoundError(AppError):
    """The routing provider answered, but there is no driving route between the points."""

    status_code = 422
    code = "route_not_found"
