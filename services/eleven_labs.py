import aiohttp
from services.ai_service import AIService

from typing import AsyncGenerator
import requests

class ElevenLabsTTSService(AIService):

    def __init__(
        self,
        model="eleven_turbo_v2",
    ):
        super().__init__()

        self._api_key = "1e7a87586dcb8cfbc12be0f49de1e260"
        self._voice_id = "OGSJQsuxTj6mxZQFIV9V"
        self._model = model

    def run_tts(self, sentence) -> AsyncGenerator[bytes, None]:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self._voice_id}/stream"
        payload = {"text": sentence, "model_id": self._model}
        querystring = {
            "output_format": "pcm_16000",
            "optimize_streaming_latency": 2}
        headers = {
            "xi-api-key": self._api_key,
            "Content-Type": "application/json",
        }
        r = requests.post(
            url, json=payload, headers=headers, params=querystring
        )
        if r.status_code != 200:
            self.logger.error(
                f"audio fetch status code: {r.status}, error: {r.text}"
            )
            return

        for chunk in r.iter_content(chunk_size=None):  # None means it will use the server's chunk size
            if chunk:
                yield chunk
