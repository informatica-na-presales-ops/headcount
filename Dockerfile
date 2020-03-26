FROM python:3.8.2-alpine3.11

COPY requirements.txt /headcount/requirements.txt

RUN /usr/bin/wget https://download.microsoft.com/download/e/4/e/e4e67866-dffd-428c-aac7-8d28ddafb39b/msodbcsql17_17.5.2.1-1_amd64.apk https://download.microsoft.com/download/e/4/e/e4e67866-dffd-428c-aac7-8d28ddafb39b/mssql-tools_17.5.2.1-1_amd64.apk \
 && /sbin/apk add --allow-untrusted --no-cache /msodbcsql17_17.5.2.1-1_amd64.apk /mssql-tools_17.5.2.1-1_amd64.apk < /usr/bin/yes \
 && /bin/rm /msodbcsql17_17.5.2.1-1_amd64.apk /mssql-tools_17.5.2.1-1_amd64.apk \
 && /sbin/apk add --no-cache --virtual .deps g++ gcc unixodbc-dev \
 && /usr/local/bin/pip install --no-cache-dir --requirement /headcount/requirements.txt \
 && /sbin/apk del --no-cache .deps
