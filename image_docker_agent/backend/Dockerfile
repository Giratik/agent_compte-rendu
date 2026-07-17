FROM python:3.11-slim

# ffmpeg reste nécessaire pour convert_audio_to_wav (subprocess)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements_backend.txt .
RUN pip install --no-cache-dir -r requirements_backend.txt

COPY whisperx.proto .
RUN pip install --no-cache-dir grpcio grpcio-tools protobuf && \
    python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. whisperx.proto

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]