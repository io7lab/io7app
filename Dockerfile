FROM python:3.14.4-slim
# Unbuffered I/O is transitive to any subprocess the user's app spawns,
# unlike `python -u` which only affects the directly-launched interpreter.
ENV PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir io7app
COPY --chmod=755 scripts/services.sh /usr/local/bin/services.sh
RUN mkdir /app
WORKDIR /app
CMD ["/usr/local/bin/services.sh"]
