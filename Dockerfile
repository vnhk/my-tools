FROM maven:3.9.2-eclipse-temurin-17 as builder

WORKDIR /app

COPY --from=bervan-utils /app/core.jar /app/core.jar
COPY --from=bervan-utils /app/history-tables-core.jar /app/history-tables-core.jar
COPY --from=bervan-utils /app/ie-entities.jar /app/ie-entities.jar

RUN mvn install:install-file -Dfile=./core.jar -DgroupId=com.bervan -DartifactId=core -Dversion=latest -Dpackaging=jar -DgeneratePom=true
RUN mvn install:install-file -Dfile=./history-tables-core.jar -DgroupId=com.bervan -DartifactId=history-tables-core -Dversion=latest -Dpackaging=jar -DgeneratePom=true
RUN mvn install:install-file -Dfile=./ie-entities.jar -DgroupId=com.bervan -DartifactId=ie-entities -Dversion=latest -Dpackaging=jar -DgeneratePom=true

COPY pom.xml .
COPY common-vaadin/pom.xml common-vaadin/
COPY shopping-stats-server-app/pom.xml shopping-stats-server-app/
COPY file-storage-app/pom.xml file-storage-app/
COPY canvas-app/pom.xml canvas-app/
COPY spreadsheet-app/pom.xml spreadsheet-app/
COPY interview-app/pom.xml interview-app/
COPY english-text-stats-app/pom.xml english-text-stats-app/
COPY pocket-app/pom.xml pocket-app/
COPY project-mgmt-app/pom.xml project-mgmt-app/
COPY streaming-platform-app/pom.xml streaming-platform-app/
COPY learning-language-app/pom.xml learning-language-app/
COPY my-tools-vaadin-app/pom.xml my-tools-vaadin-app/

RUN mvn dependency:go-offline -B

COPY ./common-vaadin ./common-vaadin
COPY ./shopping-stats-server-app ./shopping-stats-server-app
COPY ./file-storage-app ./file-storage-app
COPY ./canvas-app ./canvas-app
COPY ./spreadsheet-app ./spreadsheet-app
COPY ./interview-app ./interview-app
COPY ./english-text-stats-app ./english-text-stats-app
COPY ./pocket-app ./pocket-app
COPY ./project-mgmt-app ./project-mgmt-app
COPY ./streaming-platform-app ./streaming-platform-app
COPY ./learning-language-app ./learning-language-app
COPY ./my-tools-vaadin-app ./my-tools-vaadin-app

#themes manual copy to all required directions
COPY ./my-tools-vaadin-app/src/main/resources/META-INF/resources/static/cyberpunk-theme.css ./my-tools-vaadin-app/src/main/resources/static/
COPY ./my-tools-vaadin-app/src/main/resources/META-INF/resources/static/darkula-theme.css ./my-tools-vaadin-app/src/main/resources/static/
COPY ./my-tools-vaadin-app/src/main/resources/META-INF/resources/static/earth-theme.css ./my-tools-vaadin-app/src/main/resources/static/

COPY ./my-tools-vaadin-app/src/main/resources/META-INF/resources/static/cyberpunk-theme.css ./my-tools-vaadin-app/src/main/frontend/themes/
COPY ./my-tools-vaadin-app/src/main/resources/META-INF/resources/static/darkula-theme.css ./my-tools-vaadin-app/src/main/frontend/themes/
COPY ./my-tools-vaadin-app/src/main/resources/META-INF/resources/static/earth-theme.css ./my-tools-vaadin-app/src/main/frontend/themes/


RUN mvn install -Pproduction -DskipTests

FROM openjdk:17 AS runtime

WORKDIR /app

COPY --from=builder /app/my-tools-vaadin-app/target/my-tools-vaadin-app.jar ./my-tools-vaadin-app.jar
COPY --from=builder /app/my-tools-vaadin-app/configuration ./configuration

CMD ["java", "-jar", "-Dspring.profiles.active=production", "my-tools-vaadin-app.jar"]