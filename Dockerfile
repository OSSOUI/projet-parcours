# Image de la simulation : simuler.py, experience.py, direct.py, tableau.py.
# Le moteur n'utilise que la bibliotheque standard ; requirements.txt n'ajoute
# que Kafka et WebSocket, pour le pont vers Godot.
#   docker compose --profile colibri build ephemere
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONUNBUFFERED=1
CMD ["python3", "simuler.py", "--help"]
