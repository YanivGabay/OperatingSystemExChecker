# Dockerfile
FROM gcc-test


# Set the working directory
WORKDIR /grading

# Copy the grading script into the container
COPY grade.py /grading/grade.py

# Ensure the script is executable
RUN chmod +x /grading/grade.py

# Set the entrypoint to run the Python script using 'python3'
ENTRYPOINT ["python3", "/grading/grade.py"]
