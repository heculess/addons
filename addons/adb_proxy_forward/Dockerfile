ARG BUILD_FROM
FROM $BUILD_FROM

ENV LANG C.UTF-8
ENV NGINX_VERSION 1.16.1

RUN echo "http://mirrors.aliyun.com/alpine/latest-stable/main/" > /etc/apk/repositories && \
    echo "http://mirrors.aliyun.com/alpine/latest-stable/community/" >> /etc/apk/repositories

RUN apk add --no-cache nginx-mod-stream=1.16.1-r6 nginx=1.16.1-r6 


# Copy data for add-on
COPY run.sh /
RUN chmod a+x /run.sh

COPY nginx.conf /etc/
CMD [ "/run.sh" ]