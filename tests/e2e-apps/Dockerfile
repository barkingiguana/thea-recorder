# E2E test environment for recording different application types.
#
# Everything runs in ONE container because Thea, Xvfb, and the application
# being recorded must be co-located (they communicate via a local Unix
# socket at /tmp/.X11-unix/, not over a network).

FROM python:3.12-slim

# System dependencies for Xvfb + ffmpeg (Thea's core)
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb ffmpeg x11-xserver-utils fonts-dejavu-core \
    # For terminal recording test:
    xterm \
    # For browser recording test:
    chromium chromium-driver python3-selenium \
    # For GUI app recording test:
    gnumeric \
    # Gnumeric needs dbus for save dialogs:
    dbus-x11 \
    # Lightweight window manager (needed for window focus/activation):
    openbox \
    # Diagnostic tools:
    xdotool imagemagick procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir ".[dev]" selenium

# All tests run inside this single container.
CMD ["python3", "-m", "pytest", "tests/e2e-apps/", "-v", "--tb=short"]
