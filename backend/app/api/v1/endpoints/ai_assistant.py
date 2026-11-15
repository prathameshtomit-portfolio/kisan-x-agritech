"""Bring-your-own-key chat proxy. User keys are request-scoped and never persisted."""
from __future__ import annotations

import base64
import binascii
import ipaddress
import socket
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field, field_validator

router = APIRouter(tags=["optional AI assistant"])


class ImageInput(BaseModel):
    data: str = Field(min_length=4, max_length=11_184_812)
    mime_type: str = Field(pattern="^(image/jpeg|image/png|image/webp)$")

    @field_validator("data")
    @classmethod
    def valid_image_data(cls, value: str) -> str:
        try:
            decoded = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("Image data must be valid base64.") from exc
        if not decoded or len(decoded) > 8 * 1024 * 1024:
            raise ValueError("Each image must be at most 8 MB.")
        return value

    @field_validator("mime_type")
    @classmethod
    def matches_image_type(cls, value: str, info):
        data = info.data.get("data")
        if data:
            raw = base64.b64decode(data, validate=True)
            signatures = {
                "image/jpeg": raw.startswith(b"\xff\xd8\xff"),
                "image/png": raw.startswith(b"\x89PNG\r\n\x1a\n"),
                "image/webp": len(raw) >= 12 and raw.startswith(b"RIFF") and raw[8:12] == b"WEBP",
            }
            if not signatures.get(value, False):
                raise ValueError("Image contents do not match their MIME type.")
        return value


class ChatRequest(BaseModel):
    provider: str = Field(pattern="^(gemini|openai|anthropic|openai-compatible)$")
    model: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=8000)
    base_url: str | None = Field(default=None, max_length=500)
    images: list[ImageInput] = Field(default_factory=list, max_length=4)


def _public_https_url(raw: str) -> str:
    parsed = urlparse(raw)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise HTTPException(status_code=422, detail="Custom provider URL must be an HTTPS URL without embedded credentials.")
    if parsed.port not in (None, 443) or parsed.query or parsed.fragment:
        raise HTTPException(status_code=422, detail="Custom provider URL must use standard HTTPS without query or fragment values.")
    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith((".localhost", ".local", ".internal")):
        raise HTTPException(status_code=422, detail="Local or private-network provider URLs are not allowed.")
    try:
        addresses = {entry[4][0] for entry in socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)}
    except OSError as exc:
        raise HTTPException(status_code=422, detail="Could not resolve the custom provider host.") from exc
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise HTTPException(status_code=422, detail="Custom provider host must resolve only to public IP addresses.")
    return raw.rstrip("/")


@router.post("/ai/chat")
async def optional_ai_chat(payload: ChatRequest, x_provider_api_key: str | None = Header(default=None, alias="X-Provider-API-Key")) -> dict:
    if not x_provider_api_key or len(x_provider_api_key) > 4096:
        raise HTTPException(status_code=400, detail="Enter your provider API key in Settings. It is used only for this request.")
    decoded_images = [base64.b64decode(image.data, validate=True) for image in payload.images]
    if sum(len(data) for data in decoded_images) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Combined image size must be 15 MB or less.")
    if payload.provider == "gemini":
        url = "https://generativelanguage.googleapis.com/v1beta/interactions"
        headers = {"x-goog-api-key": x_provider_api_key}
        content = [{"type":"text", "text":payload.message}]
        content.extend({"type":"image", "data":image.data, "mime_type":image.mime_type} for image in payload.images)
        body = {"model": payload.model, "input": content, "store": False}
    elif payload.provider == "openai":
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {x_provider_api_key}"}
        content = [{"type":"text", "text":payload.message}]
        content.extend({"type":"image_url", "image_url":{"url":f"data:{image.mime_type};base64,{image.data}"}} for image in payload.images)
        body = {"model": payload.model, "messages": [{"role": "user", "content": content if payload.images else payload.message}]}
    elif payload.provider == "anthropic":
        url = "https://api.anthropic.com/v1/messages"
        headers = {"x-api-key": x_provider_api_key, "anthropic-version": "2023-06-01"}
        content = [{"type":"text", "text":payload.message}]
        content.extend({"type":"image", "source":{"type":"base64", "media_type":image.mime_type, "data":image.data}} for image in payload.images)
        body = {"model": payload.model, "max_tokens": 1200, "messages": [{"role": "user", "content": content if payload.images else payload.message}]}
    else:
        if not payload.base_url:
            raise HTTPException(status_code=422, detail="Enter an OpenAI-compatible HTTPS base URL in Settings.")
        base = _public_https_url(payload.base_url)
        url = base if base.endswith("/chat/completions") else f"{base}/chat/completions"
        headers = {"Authorization": f"Bearer {x_provider_api_key}"}
        content = [{"type":"text", "text":payload.message}]
        content.extend({"type":"image_url", "image_url":{"url":f"data:{image.mime_type};base64,{image.data}"}} for image in payload.images)
        body = {"model": payload.model, "messages": [{"role": "user", "content": content if payload.images else payload.message}]}
    try:
        async with httpx.AsyncClient(timeout=35, follow_redirects=False) as client:
            response = await client.post(url, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()
        if payload.provider == "gemini":
            answer = "".join(part.get("text", "") for step in data["steps"] if step.get("type") == "model_output" for part in step.get("content", []) if part.get("type") == "text")
        elif payload.provider == "anthropic":
            answer = "".join(block.get("text", "") for block in data["content"] if block.get("type") == "text")
        else:
            answer = data["choices"][0]["message"]["content"]
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("Empty model response")
    except httpx.HTTPStatusError as exc:
        # Avoid echoing provider error bodies which may contain sensitive request data.
        raise HTTPException(status_code=502, detail=f"{payload.provider} rejected the request (HTTP {exc.response.status_code}); check the key, model and provider account.") from exc
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
        raise HTTPException(status_code=502, detail=f"{payload.provider} is unavailable or returned an unexpected response.") from exc
    return {"provider": payload.provider, "model": payload.model, "answer": answer, "key_storage": "request_only"}


@router.post("/ai/transcribe")
async def transcribe_speech(
    audio: UploadFile = File(...),
    provider: str = Form(..., pattern="^(gemini|openai|openai-compatible)$"),
    model: str = Form(..., min_length=1, max_length=120),
    base_url: str | None = Form(default=None, max_length=500),
    language: str = Form(default="", max_length=20),
    x_provider_api_key: str | None = Header(default=None, alias="X-Provider-API-Key"),
) -> dict:
    if not x_provider_api_key or len(x_provider_api_key) > 4096:
        raise HTTPException(status_code=400, detail="Configure your own Gemini/OpenAI-compatible provider key before using AI speech transcription.")
    allowed_types = {"audio/webm", "audio/ogg", "audio/wav", "audio/x-wav", "audio/mp4", "audio/mpeg", "audio/mp3", "audio/m4a"}
    mime_type = (audio.content_type or "").split(";", 1)[0].lower()
    if mime_type not in allowed_types:
        raise HTTPException(status_code=415, detail="Unsupported audio type. Record audio/webm, audio/ogg, audio/wav, audio/mp4 or audio/mpeg.")
    raw = await audio.read(14 * 1024 * 1024 + 1)
    if not raw or len(raw) > 14 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Audio recording must be between 1 byte and 14 MB.")
    language_hint = f" The spoken language is likely {language}." if language else " Identify the spoken language automatically."
    prompt = f"Transcribe the speech exactly in its original language. Return only the transcript, without commentary.{language_hint}"
    try:
        async with httpx.AsyncClient(timeout=45, follow_redirects=False) as client:
            if provider == "gemini":
                url = "https://generativelanguage.googleapis.com/v1beta/interactions"
                response = await client.post(url, headers={"x-goog-api-key":x_provider_api_key}, json={
                    "model":model,
                    "input":[{"type":"text","text":prompt},{"type":"audio","data":base64.b64encode(raw).decode("ascii"),"mime_type":mime_type}],
                    "store":False,
                })
            else:
                if provider == "openai":
                    url = "https://api.openai.com/v1/audio/transcriptions"
                else:
                    if not base_url:
                        raise HTTPException(status_code=422, detail="Enter your OpenAI-compatible HTTPS base URL in Settings.")
                    base = _public_https_url(base_url)
                    url = base if base.endswith("/audio/transcriptions") else f"{base}/audio/transcriptions"
                response = await client.post(url, headers={"Authorization":f"Bearer {x_provider_api_key}"},
                                             data={"model":model,"language":language.split("-")[0] if language else ""},
                                             files={"file":(audio.filename or "kisanx-recording.webm",raw,mime_type)})
            response.raise_for_status()
            data=response.json()
        if provider == "gemini":
            transcript="".join(part.get("text","") for step in data["steps"] if step.get("type")=="model_output" for part in step.get("content",[]) if part.get("type")=="text")
        else:
            transcript=data.get("text","")
        if not isinstance(transcript,str) or not transcript.strip():
            raise ValueError("Empty transcription")
    except HTTPException:
        raise
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Speech provider rejected the request (HTTP {exc.response.status_code}); check your key, model and account.") from exc
    except (httpx.HTTPError,ValueError,KeyError,TypeError) as exc:
        raise HTTPException(status_code=502, detail="Speech provider is unavailable or returned an unexpected response.") from exc
    return {"provider":provider,"model":model,"transcript":transcript.strip(),"audio_storage":"request_only"}
