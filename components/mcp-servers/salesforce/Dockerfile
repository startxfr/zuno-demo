# Pulls through the zuno-ai-build ImageStream mirror
# (ansible/roles/image_mirrors), not docker.io directly.
FROM image-registry.openshift-image-registry.svc:5000/zuno-ai-build/python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py .

EXPOSE 8000
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
