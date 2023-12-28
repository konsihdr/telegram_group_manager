# Verwende das offizielle Python 3.10 Docker-Image als Basis
FROM python:3.10

# Setze das Arbeitsverzeichnis auf /app
WORKDIR /app

# Kopiere die Anwendungsdateien in das Arbeitsverzeichnis im Container
COPY bot.py /app
COPY sql.py /app
COPY requirements.txt /app
COPY force_update_links.py /app
RUN mkdir /db

# Installiere die Python-Pakete aus requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Starte bot.py, wenn der Container gestartet wird
CMD ["python", "-u", "bot.py"]
