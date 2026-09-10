FROM azari-stage10-final:latest
USER root
RUN pip install --no-cache-dir httpx==0.28.1
USER azari
ENV PYTHONPATH=/app:/load
ENTRYPOINT ["python", "/load/stage11_load.py"]
