FROM openjdk:21-jdk-bullseye

WORKDIR "/server"

# Download Core package from side
RUN wget https://api.papermc.io/v2/projects/paper/versions/1.19.3/builds/358/downloads/paper-1.19.3-358.jar

# Copy Configurations
COPY ./properties/* .

# Inform Docker that container will listen 25565 port
EXPOSE 25565

CMD [ "java", "-jar", "paper-1.19.3-358.jar"]
