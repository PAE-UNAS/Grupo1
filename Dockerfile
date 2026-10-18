# Ambiente reprodutível do painel.
#   docker build -t calor-heliopolis .
#   docker run -p 8501:8501 -v "$(pwd)/data:/app/data" calor-heliopolis
# O volume em /app/data guarda o cache dos downloads e os CSVs dos sensores.
FROM python:3.12-slim

# compilador: só é usado se o pip não achar um pacote pronto do pyreaddbc
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.headless=true"]
