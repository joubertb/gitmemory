# Build frontend
FROM node:20-slim AS frontend-builder

WORKDIR /app/frontend

# Copy frontend files
COPY src/view_fn_hist/web/frontend/package*.json ./
RUN npm ci

COPY src/view_fn_hist/web/frontend/ ./
RUN npm run build


# Build Python app
FROM python:3.12-slim

WORKDIR /app

# Install git (required by GitPython) and uv
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && pip install uv

# Copy Python project files
COPY pyproject.toml ./
COPY src/ ./src/

# Install dependencies
RUN uv pip install --system -e .

# Copy built frontend
COPY --from=frontend-builder /app/frontend/dist ./src/view_fn_hist/web/frontend/dist

# Expose port
EXPOSE 8000

# Environment variables (can be overridden at runtime)
ENV GITHUB_TOKEN=""
ENV OPENROUTER_API_KEY=""
ENV VIEW_FN_HIST_MODEL="openrouter/google/gemini-flash-1.5"

# Run the web server (bind to 0.0.0.0 for Docker)
CMD ["uvicorn", "view_fn_hist.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
