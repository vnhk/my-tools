FROM eclipse-temurin:17-jdk
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0t64 libnss3 libnspr4 libdbus-1-3 libatk1.0-0t64 \
    libatk-bridge2.0-0t64 libatspi2.0-0t64 libx11-6 libxcomposite1 \
    libxdamage1 libxext6 libxfixes3 libxrandr2 libgbm1 libdrm2 libxcb1 \
    libxkbcommon0 ffmpeg libasound2t64 && rm -rf /var/lib/apt/lists/*
COPY my-tools-app.jar ./my-tools-app.jar
COPY configuration ./configuration
# Match the current application runtime; no production configuration is embedded.
CMD ["sh", "-c", "exec java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:5005 -Xms2g -Xmx9g -Dspring.profiles.active=production -jar my-tools-app.jar"]
