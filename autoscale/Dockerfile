FROM alpine:latest
RUN apk add python3 && apk add py3-pip && \
    #pip3 install kubernetes && \
    apk add py3-requests py3-kubernetes && \
    mkdir /code
COPY autoscale.py /code
WORKDIR /code
ENTRYPOINT ["python3", "autoscale.py"]
