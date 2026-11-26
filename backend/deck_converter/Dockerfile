# The deck converter: a Lambda container image (arm64) with LibreOffice Impress and poppler. It is the ONLY place an untrusted deck is opened.
# Debian + the Lambda runtime interface client (the Amazon Linux base images carry no LibreOffice). Fonts: Carlito and Caladea are metric-compatible with
# Calibri and Cambria, Liberation with Arial/Times/Courier, so line breaks match what the author saw.
FROM public.ecr.aws/docker/library/python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends \
      libreoffice-impress libreoffice-draw fonts-crosextra-carlito fonts-crosextra-caladea fonts-liberation fonts-dejavu-core fonts-noto-core fonts-noto-cjk fonts-noto-color-emoji poppler-utils \
    && rm -rf /var/lib/apt/lists/* /usr/share/doc /usr/share/man
RUN pip install --no-cache-dir awslambdaric==2.2.1 boto3 python-pptx defusedxml Pillow
ENV HOME=/tmp LANG=C.UTF-8 PYTHONDONTWRITEBYTECODE=1
WORKDIR /var/task
COPY deck_safe.py deck_extract.py deck_render.py app.py ./
ENTRYPOINT ["/usr/local/bin/python", "-m", "awslambdaric"]
CMD ["app.handler"]
