FROM python:3.14.4-slim
# Unbuffered I/O is transitive to any subprocess the user's app spawns,
# unlike `python -u` which only affects the directly-launched interpreter.
ENV PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir io7app
COPY --chmod=755 scripts/services.sh /usr/local/bin/services.sh
RUN mkdir /app
WORKDIR /app
# Extra packages the user installs at runtime (`docker exec io7app pip install
# flask`) land in the mounted working folder, /app/.local, so they survive the
# container being recreated. Must come AFTER `pip install io7app` above: set
# earlier, io7app itself would install under /app and be hidden by the mount.
ENV PYTHONUSERBASE=/app/.local \
    PIP_USER=1 \
    PIP_ROOT_USER_ACTION=ignore \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH=/app/.local/bin:$PATH
CMD ["/usr/local/bin/services.sh"]
