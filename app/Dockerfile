# Một ảnh container cho cả FastAPI và TiTiler (giai đoạn nguyên mẫu).
# Khi mở rộng thì tách thành hai dịch vụ Cloud Run; mã nguồn không phải đổi.
FROM python:3.12-slim

# rasterio/rio-tiler cần thư viện hệ thống của GDAL.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libexpat1 libgdal32 && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY app/requirements.txt /srv/app/requirements.txt
RUN pip install --no-cache-dir -r /srv/app/requirements.txt

COPY app /srv/app
COPY task_pipeline/provinces.json /srv/task_pipeline/provinces.json

# Cloud Run truyền cổng qua biến PORT.
ENV PORT=8080 VNGIS_DB=/srv/app/data/vngis.db
EXPOSE 8080
CMD exec uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT}
