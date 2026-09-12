from __future__ import annotations

from dataclasses import dataclass

AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
MODEL_NOT_FOUND = "MODEL_NOT_FOUND"
CONNECTION_FAILED = "CONNECTION_FAILED"
TIMEOUT = "TIMEOUT"
RATE_LIMITED = "RATE_LIMITED"
INVALID_BASE_URL = "INVALID_BASE_URL"
PROVIDER_API_ERROR = "PROVIDER_API_ERROR"
UNKNOWN_ERROR = "UNKNOWN_ERROR"


@dataclass(frozen=True)
class NormalizedError:
    code: str
    message: str


def normalize_error(message: str) -> NormalizedError:
    text = (message or "").lower()
    if any(x in text for x in ("401", "403", "authentication", "unauthorized", "api key")):
        return NormalizedError(AUTHENTICATION_FAILED, "API key is invalid or unauthorized.")
    if "rate limit" in text or "429" in text or "too many requests" in text:
        return NormalizedError(RATE_LIMITED, "Request rate limit reached. Try again later.")
    if "timeout" in text or "timed out" in text:
        return NormalizedError(TIMEOUT, "The provider did not respond within the configured timeout.")
    if "model" in text and any(x in text for x in ("not found", "unsupported", "unavailable")):
        return NormalizedError(MODEL_NOT_FOUND, "The selected model is unavailable or unsupported.")
    if "url" in text or "connection" in text or "network" in text or "name or service" in text:
        return NormalizedError(INVALID_BASE_URL if "url" in text else CONNECTION_FAILED,
                               "Invalid provider URL." if "url" in text else "Connection to the provider failed.")
    if "provider" in text or "api error" in text:
        return NormalizedError(PROVIDER_API_ERROR, "The provider returned an API error.")
    return NormalizedError(UNKNOWN_ERROR, "The provider request failed.")
