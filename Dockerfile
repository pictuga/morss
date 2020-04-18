FROM alpine:latest

RUN apk add python3 py3-lxml py3-pip git

RUN pip3 install gunicorn
RUN pip3 install git+https://git.pictuga.com/pictuga/morss.git@master

CMD gunicorn --bind 0.0.0.0:8080 -w 4 morss:cgi_standalone_app
