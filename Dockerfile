FROM maven:3.9.2-eclipse-temurin-17 as builder

WORKDIR /app

COPY --from=bervan-utils /app/core.jar /app/core.jar
COPY --from=bervan-utils /app/history-tables-core.jar /app/history-tables-core.jar
COPY --from=bervan-utils /app/ie-entities.jar /app/ie-entities.jar

RUN mvn install:install-file -Dfile=./core.jar -DgroupId=com.bervan -DartifactId=core -Dversion=latest -Dpackaging=jar -DgeneratePom=true
RUN mvn install:install-file -Dfile=./history-tables-core.jar -DgroupId=com.bervan -DartifactId=history-tables-core -Dversion=latest -Dpackaging=jar -DgeneratePom=true
RUN mvn install:install-file -Dfile=./ie-entities.jar -DgroupId=com.bervan -DartifactId=ie-entities -Dversion=latest -Dpackaging=jar -DgeneratePom=true

COPY ./common-vaadin ./common-vaadin
RUN mvn -f='./common-vaadin' install -DskipTests -U

COPY ./shopping-stats-server-app ./shopping-stats-server-app
RUN mvn -f='./shopping-stats-server-app' install -DskipTests -U

COPY ./file-storage-app ./file-storage-app
RUN mvn -f='./file-storage-app' install -DskipTests -U

COPY ./canvas-app ./canvas-app
RUN mvn -f='./canvas-app' install -DskipTests -U

COPY ./spreadsheet-app ./spreadsheet-app
RUN mvn -f='./spreadsheet-app' install -DskipTests -U

COPY ./interview-app ./interview-app
RUN mvn -f='./interview-app' install -DskipTests -U

COPY ./english-text-stats-app ./english-text-stats-app
RUN mvn -f='./english-text-stats-app' install -DskipTests -U

COPY ./pocket-app ./pocket-app
RUN mvn -f='./pocket-app' install -DskipTests -U

COPY ./project-mgmt-app ./project-mgmt-app
RUN mvn -f='./project-mgmt-app' install -DskipTests -U

COPY ./streaming-platform-app ./streaming-platform-app
RUN mvn -f='./streaming-platform-app' install -DskipTests -U

COPY ./learning-language-app ./learning-language-app
RUN mvn -f='./learning-language-app' install -DskipTests -U

COPY ./my-tools-vaadin-app/pom.xml ./my-tools-vaadin-app/pom.xml
COPY ./my-tools-vaadin-app/tsconfig.json ./my-tools-vaadin-app/tsconfig.json
COPY ./my-tools-vaadin-app/types.d.ts ./my-tools-vaadin-app/types.d.ts
COPY ./my-tools-vaadin-app/vite.config.ts ./my-tools-vaadin-app/vite.config.ts
COPY ./my-tools-vaadin-app/src/main/java ./my-tools-vaadin-app/src/main/java
COPY ./my-tools-vaadin-app/src/main/resources ./my-tools-vaadin-app/src/main/resources
COPY ./my-tools-vaadin-app/src/main/frontend/themes ./my-tools-vaadin-app/src/main/frontend/themes
COPY ./my-tools-vaadin-app/src/main/frontend/index.html ./my-tools-vaadin-app/src/main/frontend/index.html
COPY ./my-tools-vaadin-app/src/main/frontend/theme-changer.js ./my-tools-vaadin-app/src/main/frontend/theme-changer.js
COPY ./my-tools-vaadin-app/configuration ./my-tools-vaadin-app/configuration

RUN mvn -f='./my-tools-vaadin-app' -Pproduction install -DskipTests -U

FROM openjdk:17 AS runtime

WORKDIR /app

COPY --from=builder /app/my-tools-vaadin-app/target/my-tools-vaadin-app.jar ./my-tools-vaadin-app.jar
COPY --from=builder /app/my-tools-vaadin-app/configuration ./configuration

CMD ["java", "-jar", "-Dspring.profiles.active=production", "my-tools-vaadin-app.jar"]

