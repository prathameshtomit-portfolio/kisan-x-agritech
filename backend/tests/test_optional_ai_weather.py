import base64

from fastapi import HTTPException

from app.api.v1.endpoints.ai_assistant import _public_https_url
from app.api.v1.endpoints.weather_forecast import OPEN_METEO_URL


def test_ai_key_is_required_and_not_persisted(client):
    response = client.post("/api/v1/ai/chat", json={"provider":"gemini","model":"some-model","message":"hello"})
    assert response.status_code == 400
    assert "API key" in response.json()["error"]["message"]


def test_ai_provider_is_allowlisted(client):
    response = client.post("/api/v1/ai/chat", headers={"X-Provider-API-Key":"user-owned-key"},
                           json={"provider":"unknown","model":"model","message":"hello"})
    assert response.status_code == 422


def test_gemini_user_key_is_sent_only_to_the_provider_and_response_is_normalized(client, monkeypatch):
    import app.api.v1.endpoints.ai_assistant as assistant

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"steps":[{"type":"model_output","content":[{"type":"text","text":" नमस्ते "}]}]}

    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs["follow_redirects"] is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def post(self, url, headers, json):
            assert url == "https://generativelanguage.googleapis.com/v1beta/interactions"
            assert headers["x-goog-api-key"] == "farmer-owned-test-key"
            assert json["store"] is False
            assert json["input"][1]["type"] == "image"
            assert json["input"][1]["mime_type"] == "image/png"
            return FakeResponse()

    monkeypatch.setattr(assistant.httpx, "AsyncClient", FakeClient)
    response = client.post("/api/v1/ai/chat", headers={"X-Provider-API-Key":"farmer-owned-test-key"},
                           json={"provider":"gemini","model":"farmer-selected-model","message":"hello",
                                 "images":[{"mime_type":"image/png","data":base64.b64encode(b"\x89PNG\r\n\x1a\nsmall-image").decode()}]})
    assert response.status_code == 200
    assert response.json()["answer"] == " नमस्ते "
    assert response.json()["key_storage"] == "request_only"


def test_ai_rejects_image_mime_mismatch(client):
    response = client.post("/api/v1/ai/chat", headers={"X-Provider-API-Key":"user-owned-key"},
                           json={"provider":"gemini","model":"some-model","message":"describe it",
                                 "images":[{"mime_type":"image/jpeg","data":base64.b64encode(b"not an image").decode()}]})
    assert response.status_code == 422


def test_transcription_requires_user_provider_key(client):
    response = client.post("/api/v1/ai/transcribe", data={"provider":"openai","model":"whisper-1"},
                           files={"audio":("recording.webm",b"audio-bytes","audio/webm")})
    assert response.status_code == 400


def test_transcription_uses_request_key_and_returns_text_without_storing_audio(client, monkeypatch):
    import app.api.v1.endpoints.ai_assistant as assistant

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"text":"नमस्ते खेत"}

    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs["follow_redirects"] is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def post(self, url, headers, data, files):
            assert url == "https://api.openai.com/v1/audio/transcriptions"
            assert headers["Authorization"] == "Bearer user-key"
            assert files["file"][2] == "audio/webm"
            return FakeResponse()

    monkeypatch.setattr(assistant.httpx, "AsyncClient", FakeClient)
    response = client.post("/api/v1/ai/transcribe", headers={"X-Provider-API-Key":"user-key"},
                           data={"provider":"openai","model":"whisper-1","language":"hi-IN"},
                           files={"audio":("recording.webm",b"audio-bytes","audio/webm")})
    assert response.status_code == 200
    assert response.json()["transcript"] == "नमस्ते खेत"
    assert response.json()["audio_storage"] == "request_only"


def test_custom_ai_url_must_be_public_https():
    try:
        _public_https_url("http://127.0.0.1:8000/v1")
    except HTTPException as exc:
        assert exc.status_code == 422
    else:
        raise AssertionError("private HTTP URL should be rejected")


def test_forecast_requires_valid_coordinates(client):
    response = client.get("/api/v1/weather/forecast?lat=91&lon=79")
    assert response.status_code == 422


def test_forecast_provider_failure_does_not_return_substitute_data(client, monkeypatch):
    import app.api.v1.endpoints.weather_forecast as forecast

    class FakeResponse:
        def raise_for_status(self):
            raise forecast.httpx.ConnectError("offline")

    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs["timeout"] == 12

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def get(self, url, params):
            assert url == OPEN_METEO_URL
            assert params["latitude"] == 20.5
            return FakeResponse()

    monkeypatch.setattr(forecast.httpx, "AsyncClient", FakeClient)
    response = client.get("/api/v1/weather/forecast?lat=20.5&lon=79&days=7")
    assert response.status_code == 502
    assert "no substitute forecast" in response.json()["error"]["message"]


def test_forecast_returns_current_conditions_for_visible_weather_card(client, monkeypatch):
    import app.api.v1.endpoints.weather_forecast as forecast

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"timezone":"Asia/Kolkata","current":{"temperature_2m":31.2,"apparent_temperature":34.1,
                    "relative_humidity_2m":62,"precipitation":0,"wind_speed_10m":8.5,"weather_code":2,"is_day":1},
                    "current_units":{"temperature_2m":"°C"},"daily":{"time":["2026-11-15"],"temperature_2m_max":[32]}}

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def get(self, url, params):
            assert "weather_code" in params["current"]
            assert "apparent_temperature" in params["current"]
            return FakeResponse()

    monkeypatch.setattr(forecast.httpx, "AsyncClient", FakeClient)
    response=client.get("/api/v1/weather/forecast?lat=20.5&lon=79&days=7")
    assert response.status_code==200
    assert response.json()["current"]["temperature_2m"]==31.2
    assert response.json()["current"]["weather_code"]==2
