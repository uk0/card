FROM python:3.12-slim-bullseye

MAINTAINER firsh.me  neoj


WORKDIR /app

ADD . /app

RUN pip install -r package.txt

CMD ["/bin/bash","./start.sh"]