FROM oraclelinux:8.5

COPY requirements.txt /headcount/requirements.txt

RUN /usr/bin/yum --assumeyes update \
 && /usr/bin/yum --assumeyes install python38 https://download.oracle.com/otn_software/linux/instantclient/19800/oracle-instantclient19.8-basic-19.8.0.0.0-1.x86_64.rpm \
 && /usr/bin/yum --verbose clean all \
 && /usr/bin/python3 -m ensurepip \
 && /usr/bin/python3 -m pip install --upgrade --no-cache-dir pip \
 && /usr/bin/python3 -m pip install --no-cache-dir --requirement /headcount/requirements.txt

ENV APP_VERSION="2020.10" \
    LD_LIBRARY_PATH="/usr/lib/oracle/19.8/client64/lib" \
    PYTHONUNBUFFERED="1" \
    TZ="Etc/UTC"

COPY . /headcount

ENTRYPOINT ["/usr/bin/python3"]
CMD ["/headcount/headcount.py"]
