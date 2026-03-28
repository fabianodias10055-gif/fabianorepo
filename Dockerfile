FROM python:3.11-slim

WORKDIR /app

COPY discord-feedback-bot/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY discord-feedback-bot/ .

CMD ["python", "bot.py"]
