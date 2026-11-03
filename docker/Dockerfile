# Use Ubuntu base image with Python
FROM ubuntu:22.04

# Avoid prompts from apt
ENV DEBIAN_FRONTEND=noninteractive

# Use Chinese mirrors for Ubuntu to improve network connectivity
RUN sed -i 's/archive.ubuntu.com/mirrors.aliyun.com/g' /etc/apt/sources.list && \
    sed -i 's/security.ubuntu.com/mirrors.aliyun.com/g' /etc/apt/sources.list

# Install Python and other dependencies including Docker
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    curl \
    wget \
    gnupg \
    ca-certificates \
    unzip \
    sudo \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    iproute2 \
    && rm -rf /var/lib/apt/lists/*

# Install Docker
RUN curl -fsSL https://get.docker.com -o get-docker.sh && sh get-docker.sh

# Install docker-compose
RUN curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
RUN chmod +x /usr/local/bin/docker-compose

# Create a symbolic link for python
RUN ln -s /usr/bin/python3 /usr/bin/python

# Upgrade pip
RUN pip3 install --upgrade pip

# Copy requirements.txt and install Python dependencies (temporarily disable proxy for build)
COPY requirements.txt /app/requirements.txt
WORKDIR /app
RUN unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy && \
    pip install -r requirements.txt

# Copy install scripts
COPY src/scripts/install /app/install
RUN chmod +x /app/install/*.sh

# Run the install script to set up npm and Chrome
RUN cd /app/install && ./install_node.sh
RUN cd /app/install && ./install_chrome.sh
RUN cd /app/install && python ./check_selenium.py

RUN pip install playwright
RUN playwright install chromium

RUN apt-get update && apt-get install -y tmux 
RUN pip install bashlex libtmux

RUN playwright install chromium

# Set user as root
USER root

# Set working directory
WORKDIR /app

# Default command
CMD ["bash"]
