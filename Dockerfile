# NAL Reel Engine — Python + ffmpeg (para Render.com / cualquier host Docker)
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY reel_engine.py service.py ./
COPY fonts ./fonts
ENV PORT=8080
# 1 worker, timeout alto (render + ffmpeg ~5-8s)
CMD ["gunicorn","-w","1","-k","gthread","--threads","4","-t","180","-b","0.0.0.0:8080","service:app"]
