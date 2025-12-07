FROM python:alpine
# Install dependencies
WORKDIR /app
COPY --chown=APP:APP requirements.txt .
RUN pip install -r requirements.txt
# Run the application
COPY --chown=APP:APP . .
USER APP
VOLUME ["/ddns/ip"]
CMD ["python", "main.py"]