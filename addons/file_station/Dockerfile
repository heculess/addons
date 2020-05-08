ARG BUILD_FROM
FROM $BUILD_FROM

ENV LANG C.UTF-8

RUN echo "http://mirrors.aliyun.com/alpine/latest-stable/main/" > /etc/apk/repositories && \
    echo "http://mirrors.aliyun.com/alpine/latest-stable/community/" >> /etc/apk/repositories

RUN apk add --no-cache nginx openssl curl

# Copy data for add-on
COPY run.sh /
RUN chmod a+x /run.sh

COPY nginx.conf /etc/

CMD [ "/run.sh" ]