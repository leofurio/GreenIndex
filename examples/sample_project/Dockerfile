# GC080: tag :latest non fissato   +   GC081: nessuna multi-stage build
FROM python:latest

WORKDIR /app
COPY . .
RUN pip install -r requirements.txt

CMD ["python", "etl.py"]
