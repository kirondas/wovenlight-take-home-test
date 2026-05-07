# Container image for the TfL scheduler Flask API.
#
# This Dockerfile packages the Python 3.12 runtime, installs dependencies from
# requirements.txt, installs the `tfl_scheduler` package from ./src in editable
# or standard layout (via pyproject + pip), and sets the default process to run
# the Flask app module. Interview angles: explain multi-stage builds (not used
# here—single stage for simplicity), slim vs full images, and why PYTHONUNBUFFERED
# helps you see logs immediately in `docker logs`.

FROM python:3.12-slim  # Official small Debian-based Python image balancing size vs compatibility

ENV PYTHONUNBUFFERED=1  # Force stdout/stderr to be unbuffered so container logs show prints immediately

WORKDIR /app  # Subsequent COPY/RUN/CMD execute relative to /app inside the image

COPY requirements.txt pyproject.toml ./  # Dependency metadata first for better Docker layer cache on code edits
COPY src ./src  # Application source tree containing `tfl_scheduler` package

RUN pip install --no-cache-dir -r requirements.txt  # Install third-party libs without writing wheels to image cache layer
RUN pip install --no-cache-dir .  # Install this project as a package so `python -m tfl_scheduler.app` resolves

CMD ["python", "-m", "tfl_scheduler.app"]  # Default container command: run module as __main__ (starts dev server via `if __name__` block)
