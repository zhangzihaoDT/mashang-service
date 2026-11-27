"""Single-request client for the pinned OpenCode Console image model."""

import base64
import hashlib
import json
import os
from http.client import HTTPException, HTTPSConnection
from pathlib import Path
from time import monotonic

from dotenv import dotenv_values
from PIL import Image

MODEL_ID = "gemini-nano-banana-2.1"
MODEL = f"opencode/{MODEL_ID}"
HOST = "opencode.ai"
ROUTE = f"/inference/google/v1beta/models/{MODEL_ID}:generateContent"
ASPECT = "3:4"
RESOLUTION = "1K"
EXPECTED_SIZE = (896, 1200)  # Nano Banana 2.1's native 3:4, 1K pixel size.
OUTPUT_TYPES = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


def api_key():
    key = os.environ.get("OPENCODE_API_KEY")
    if not key:
        config_home = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
        env_file = config_home / "opencode/.env"
        if env_file.is_file():
            key = dotenv_values(env_file, interpolate=False).get("OPENCODE_API_KEY")
    if not key or not key.strip():
        raise ValueError("未配置 OpenCode Console 的 OPENCODE_API_KEY")
    return key.strip()


def request_body(prompt, reference):
    return {
        "contents": [{"role": "user", "parts": [
            {"inlineData": {"mimeType": "image/png", "data": base64.b64encode(reference).decode("ascii")}},
            {"text": prompt},
        ]}],
        "generationConfig": {
            "candidateCount": 1,
            "responseModalities": ["IMAGE"],
            "imageConfig": {"aspectRatio": ASPECT, "imageSize": RESOLUTION},
        },
    }


def request_bytes(prompt, reference):
    return json.dumps(request_body(prompt, reference), ensure_ascii=False).encode("utf-8")


def generate(prompt, reference, output):
    key = api_key()
    body = request_bytes(prompt, reference)
    attempt = output / "generation.json"
    result = {"status": "submission_started", "requested_model": MODEL,
              "endpoint": f"https://{HOST}{ROUTE}", "aspect_ratio": ASPECT,
              "resolution": RESOLUTION, "cost_usd": None, "request_sha256": hashlib.sha256(body).hexdigest()}
    # Reserve the attempt before opening the connection. Never replay a POST
    # if the connection closes or the charge/result cannot be determined.
    with attempt.open("x", encoding="utf-8") as record:
        json.dump(result, record, ensure_ascii=False, indent=2)
    started = monotonic()
    connection = HTTPSConnection(HOST, timeout=180)
    try:
        connection.request("POST", ROUTE, body=body, headers={
            "Authorization": f"Bearer {key}", "Content-Type": "application/json",
            "Accept": "application/json", "Connection": "close",
        })
        response = connection.getresponse()
        result["http_status"] = response.status
        raw = response.read()
        result["seconds"] = round(monotonic() - started, 2)
        if response.status != 200:
            raise ValueError(f"OpenCode Console HTTP {response.status}")
        data = json.loads(raw)
        version = data.get("modelVersion")
        result["actual_model_version"] = version
        result["response_id"] = data.get("responseId")
        usage = data.get("usageMetadata")
        result["usage"] = usage
        if isinstance(usage, dict) and type(usage.get("cost")) in (int, float):
            result["cost_usd"] = usage["cost"]
        images = [
            part["inlineData"]
            for candidate in data.get("candidates", [])
            for part in candidate.get("content", {}).get("parts", [])
            if "inlineData" in part and not part.get("thought", False)
        ]
        if len(images) != 1:
            raise ValueError(f"OpenCode 返回了 {len(images)} 张最终图片，期望 1 张")
        image = images[0]
        extension = OUTPUT_TYPES.get(image.get("mimeType"))
        if extension is None:
            raise ValueError("图片回包缺少受支持的 MIME 类型")
        payload = base64.b64decode(image["data"], validate=True)
        path = output / f"raw-poster.{extension}"
        with path.open("xb") as file:
            file.write(payload)
        result["image_path"] = str(path)
        with Image.open(path) as poster:
            result["image_size"] = list(poster.size)
            result["exact_3_4"] = poster.width * 4 == poster.height * 3
            poster.verify()
        if not isinstance(version, str) or version.removeprefix("models/") != MODEL_ID:
            raise ValueError("返回的 modelVersion 缺失或与指定模型不一致")
        if tuple(result["image_size"]) != EXPECTED_SIZE:
            raise ValueError(f"图片尺寸应为 {EXPECTED_SIZE[0]}×{EXPECTED_SIZE[1]}")
        result["status"] = "pending_visual_review"
    except (ValueError, OSError, HTTPException, KeyError, TypeError) as error:
        result["status"] = "failed"
        # Avoid echoing arbitrary API content or credentials from exceptions.
        result["error"] = str(error) if type(error) is ValueError else type(error).__name__
    finally:
        connection.close()
        result.setdefault("seconds", round(monotonic() - started, 2))
        attempt.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result
