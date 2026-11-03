# Use the existing webgen-agent image as the base
FROM webgen-agent:latest

# Install PostgreSQL
RUN apt-get update && \
    apt-get install -y postgresql postgresql-contrib && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Set up PostgreSQL environment variables
ENV POSTGRES_DB=myapp \
    POSTGRES_USER=myappuser \
    POSTGRES_PASSWORD=myapppassword

# Copy a script to initialize and start PostgreSQL
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

RUN pip install pillow -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple

# Use the custom entrypoint script
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]