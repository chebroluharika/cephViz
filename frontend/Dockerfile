# Use a smaller base image
FROM python:3.10-slim AS base

# Set the working directory in the container
WORKDIR /frontend

# Install build dependencies (including cmake for pyarrow)
RUN apt-get update && apt-get install -y \
    cmake \
    g++ \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Copy only the requirements.txt file first
COPY requirements.txt requirements.txt

# Install Python dependencies with optimizations
RUN pip install --no-cache-dir -r requirements.txt

# Now copy the rest of the application files
COPY . .

# Expose Streamlit’s default port
# EXPOSE 8501

EXPOSE 8501
ENTRYPOINT ["streamlit", "run"]
CMD ["frontend.py"]

# Run the Streamlit app
# CMD ["streamlit", "run", "frontend.py", "--server.port=8501", "--server.address=0.0.0.0"]
