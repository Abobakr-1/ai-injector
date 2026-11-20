FROM python:3.12-slim

LABEL org.opencontainers.image.title="ai-injector"
LABEL org.opencontainers.image.description="AI Injector — prompt-injection testing harness (direct + indirect) by AboBakr Mohamed"

WORKDIR /app

# Only runtime deps first, to keep the layer cache useful.
COPY pyproject.toml README.md LICENSE ./
COPY ai_injector ./ai_injector

RUN pip install --no-cache-dir .

# Evidence and profiles land under /root/.config/ai-injector by default.
# Mount a volume to keep them across runs:
#   docker run --network host -v $PWD/runs:/root/.config/ai-injector/runs ai-injector ...
VOLUME ["/root/.config/ai-injector"]

# --network host is required to reach targets on the host (e.g. 127.0.0.1).
ENTRYPOINT ["ai-injector"]
CMD ["--help"]
