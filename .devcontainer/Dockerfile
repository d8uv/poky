FROM mcr.microsoft.com/devcontainers/python
RUN apt-get update && export DEBIAN_FRONTEND=noninteractive && \
    apt-get -y install gawk wget git diffstat unzip texinfo gcc build-essential \
    chrpath socat cpio python3 python3-pip python3-pexpect xz-utils debianutils \
    iputils-ping python3-git python3-jinja2 python3-subunit zstd liblz4-tool \
    file locales libacl1
RUN locale-gen en_US.UTF-8
RUN pip install websockets Django==4.2.17 beautifulsoup4==4.4.1 pytz django-log-viewer==1.1.7