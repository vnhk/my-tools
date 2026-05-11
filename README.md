# My Tools — Spring Boot Multi Module Backend

Multi-module Maven project (`com.bervan:my-tools`) — a suite of personal productivity applications.
Backend is pure Spring Boot (REST API). Frontend is React (`my-tools-react`).

## Running the project

```bash
mvn clean install -DskipTests
mvn spring-boot:run -pl my-tools-app
```

## Docker

```bash
docker-compose --env-file .env_my_tools up --build -d
```
