# Use the existing webgen-agent-postgres image as the base
FROM webgen-agent-postgres:latest

COPY requirements.txt /app/requirements.txt
WORKDIR /app
RUN unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy && \
    pip install -r requirements.txt