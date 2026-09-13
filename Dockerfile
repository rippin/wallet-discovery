FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src OBS_HOST=0.0.0.0 OBS_DB=/data/observatory.sqlite3
RUN useradd --uid 10001 --create-home observatory && mkdir /data && chown observatory:observatory /data
COPY src/wallet_observatory /app/src/wallet_observatory
USER observatory
EXPOSE 8080
CMD ["python", "-m", "wallet_observatory"]
