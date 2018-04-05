FROM python:3

WORKDIR /app

RUN git clone https://github.com/sfan5/pytgbridge . \
    && pip install --no-cache-dir -r requirements.txt \
    && mkdir /data

VOLUME ["/data"]

CMD [ "python", "./pytgbridge", "-c", "/data/config.json"]
