FROM python:3.11.5-slim

LABEL org.opencontainers.image.source=https://github.com/octoconsulting/keip

WORKDIR /code/webhook

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENTRYPOINT ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7080", "--app-dir", "/code"]
