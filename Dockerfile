FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 RADAR_LOCAL_ONLY=0 RADAR_DATA_DIR=/var/lib/radar
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY radar/ ./radar/
COPY static/ ./static/
COPY run.py ./
RUN mkdir -p /var/lib/radar
EXPOSE 8000
CMD ["uvicorn", "radar.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
