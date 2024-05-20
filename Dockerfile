FROM mcr.microsoft.com/cbl-mariner/base/python:3

# install ca-certificates for curl
RUN \
 yum update -y && \
 yum -y install ca-certificates && \
 yum clean all

# install kubectl for tests
RUN curl -LO https://dl.k8s.io/release/v1.30.0/bin/linux/amd64/kubectl
RUN chmod +x ./kubectl && mv ./kubectl /usr/local/bin

# working directory
WORKDIR /usr/src/azure-iot-ops

# copy all source to working dir
COPY . .

# create empty kubeconfig to mount later as a file
RUN mkdir -p /root/.kube && touch /root/.kube/config 

# venv
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# tox setup
RUN pip install tox

# run tests
ENTRYPOINT ["tox", "r", "-vv", "-e", "python-int", "--", "--durations=0"]