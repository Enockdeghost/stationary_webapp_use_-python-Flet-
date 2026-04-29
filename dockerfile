
FROM python:3.11

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data && chmod 777 /app/data

ENV PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["python", "main.py"]