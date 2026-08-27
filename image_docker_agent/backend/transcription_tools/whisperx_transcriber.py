"""Client gRPC asynchrone du service externe WhisperX."""

import asyncio
import os
import uuid
import subprocess
import grpc

import whisperx_pb2
import whisperx_pb2_grpc

WHISPERX_SERVICE_ADDRESS = os.environ.get("WHISPERX_SERVICE_ADDRESS", "whisperx_service:50051")
COMPUTE_TYPE = os.environ.get("COMPUTE_TYPE", "float16")

# Dossier partagé (bind mount) tel que vu par CE conteneur (backend)
SHARED_AUDIO_DIR = os.environ.get("SHARED_AUDIO_DIR", "/audio")

_channel = None
_stub = None


def get_client():
    """Réutilise le channel gRPC entre appels plutôt que d'en recréer un à chaque fois."""
    # Le stub est conservé pour réutiliser la connexion gRPC entre transcriptions.
    global _channel, _stub
    if _stub is None:
        _channel = grpc.insecure_channel(WHISPERX_SERVICE_ADDRESS)
        _stub = whisperx_pb2_grpc.WhisperXServiceStub(_channel)
    return _stub


def _transcribe_sync(
    audio_path: str,
    model_choice: str,
    device: str,
    batch_size: int,
    compute_type: str,
) -> str:
    """
    Version synchrone, exécutée dans un thread séparé (grpc est bloquant).
    audio_path doit déjà être un chemin dans SHARED_AUDIO_DIR.
    """
    stub = get_client()
    request = whisperx_pb2.TranscriptionRequest(
        audio_path=audio_path,
        model_choice=model_choice,
        device=device,
        batch_size=batch_size,
        compute_type=compute_type,
    )

    response = stub.TranscribeAudio(request, timeout=600)

    if response.error:
        raise Exception(f"WhisperX service error: {response.error}")

    return response.transcript


async def transcribe_audio_with_whisperx(
    audio_path: str,
    model_choice: str = "large-v3",
    device: str = "cuda",
    batch_size: int = 4,
    compute_type: str = "float16",
) -> str:
    """
    Transcribe audio via le service whisperx-service externe (gRPC).
    Signature identique à l'ancienne version locale : transcription_queue.py
    n'a rien à changer.

    IMPORTANT : audio_path doit pointer vers un fichier DÉJÀ présent dans le
    dossier partagé (SHARED_AUDIO_DIR), pas un chemin arbitraire du backend.
    Si le fichier vient de convert_audio_to_wav_async, celle-ci écrit
    désormais directement dans ce dossier partagé.
    """
    return await asyncio.to_thread(
        _transcribe_sync,
        audio_path,
        model_choice,
        device,
        batch_size,
        compute_type,
    )


def convert_audio_to_wav(input_path: str) -> str:
    """
    Convert audio file to WAV format (16kHz, mono, PCM 16-bit).
    Écrit désormais dans SHARED_AUDIO_DIR (et non /tmp) pour que le fichier
    soit visible par whisperx-service via le volume partagé.
    """
    filename = f"{uuid.uuid4().hex}.wav"
    output_path = os.path.join(SHARED_AUDIO_DIR, filename)

    command = [
        "ffmpeg", "-i", input_path, "-vn",
        "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", "-y",
        output_path
    ]
    subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    return output_path


async def convert_audio_to_wav_async(input_path: str) -> str:
    """Déporte ffmpeg dans un thread pour ne pas bloquer la boucle asyncio."""
    return await asyncio.to_thread(convert_audio_to_wav, input_path)