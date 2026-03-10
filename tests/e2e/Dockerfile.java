FROM maven:3.9-eclipse-temurin-17 AS build

WORKDIR /sdk
COPY sdks/java/ .
RUN mvn -q package -DskipTests

WORKDIR /app
COPY tests/e2e/TestE2E.java .
RUN javac -cp /sdk/target/thea-recorder-1.0.0.jar TestE2E.java

FROM eclipse-temurin:17-jre
COPY --from=build /sdk/target/thea-recorder-1.0.0.jar /app/
COPY --from=build /app/TestE2E.class /app/
WORKDIR /app
CMD ["java", "-cp", ".:thea-recorder-1.0.0.jar", "TestE2E"]
