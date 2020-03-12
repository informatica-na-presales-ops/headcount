FROM oraclelinux:7.7

COPY requirements.txt /headcount/requirements.txt

RUN /usr/bin/yum --assumeyes update \
 && /usr/bin/yum --assumeyes install oracle-release-el7 python3 \
 && /usr/bin/yum --assumeyes install oracle-instantclient18.3-basic \
 && /usr/bin/yum --verbose clean all \
 && /usr/bin/python3 -m pip install --no-cache-dir --requirement /headcount/requirements.txt

ENV APP_VERSION="2020.8" \
    LD_LIBRARY_PATH="/usr/lib/oracle/18.3/client64/lib" \
    PYTHONUNBUFFERED="1" \
    TZ="Etc/UTC"

COPY . /headcount

ENTRYPOINT ["/usr/bin/python3"]
CMD ["/headcount/headcount.py"]
