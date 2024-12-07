# Dockerfile
FROM gcc-test

# Install additional necessary packages for grading
RUN dnf install -y valgrind tar && \
    dnf clean all

# Set the working directory
WORKDIR /grading

# Copy the grading script into the container
COPY grade.py /grading/grade.py

# Ensure the script is executable
RUN chmod +x /grading/grade.py

# Set the entrypoint to run the Python script using 'python3'
ENTRYPOINT ["python3", "/grading/grade.py"]
