FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY classifier.py generate_data.py analyze.py evaluate.py app.py ./

# Données de démonstration synthétiques + rapport initial
RUN python generate_data.py && python analyze.py

EXPOSE 5000
CMD ["gunicorn", "-b", "0.0.0.0:5000", "-w", "2", "app:app"]
