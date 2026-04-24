FROM python:3.11

RUN useradd --create-home --shell /bin/bash appuser
WORKDIR /app

# Upgrade pip with retries and timeout to avoid network issues
RUN pip install --no-cache-dir --upgrade pip --retries 5 --timeout 120

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --retries 5 --timeout 120

COPY . .

RUN mkdir -p /app/data && chown -R appuser:appuser /app
USER appuser

ENV PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["python", "main.py"]