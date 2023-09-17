# Use Python 3.11.5 as a parent image
FROM python:3.11.5

ENV PYTHONUNBUFFERED True

ENV APP_HOME /app
WORKDIR $APP_HOME
COPY . ./

# Install any needed packages specified in requirements.txt
RUN apt update
RUN apt -y install build-essential python3-dev libcairo2-dev libpango1.0-dev ffmpeg texlive texlive-latex-extra
RUN pip install --no-cache-dir -r requirements.txt

# Make port 8080 available to the world outside this container
EXPOSE 8080

# Define environment variable
ENV PORT 8080
ENV OPENAI_API_KEY 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

# Run app.py when the container launches
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 main:app