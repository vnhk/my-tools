FROM maven:3.9.9-eclipse-temurin-17 AS java_tools
FROM mcr.microsoft.com/playwright:v1.59.1-noble
USER root
RUN apt-get update && apt-get install -y --no-install-recommends python3 curl \
    && rm -rf /var/lib/apt/lists/*
COPY --from=java_tools /opt/java/openjdk /opt/java/openjdk
COPY --from=java_tools /usr/share/maven /opt/maven
ENV JAVA_HOME=/opt/java/openjdk
ENV PATH="/opt/java/openjdk/bin:/opt/maven/bin:${PATH}"
# Playwright supplies Node.js and browser OS dependencies; Maven uses Java 17.
RUN java -version && mvn -version && node --version && python3 --version
