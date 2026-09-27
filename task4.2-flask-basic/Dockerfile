# SWE40006 Task 4.2 - Credit level Dockerfile
# Intentionally straightforward. Its weaknesses are addressed at Task 4.3.

FROM python:3.12-slim

WORKDIR /app

# Dependencies first so this layer is cached when only app.py changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

ENV PORT=5000
EXPOSE 5000

CMD ["python", "app.py"]
