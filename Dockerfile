FROM python:alpine
# Install dependencies
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
# Run the application
COPY . .
VOLUME ["/ddns/ip"]
CMD ["python", "main.py"]