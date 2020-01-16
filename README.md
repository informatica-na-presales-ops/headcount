# Headcount

This tool is used to track changes to organizational data. It is probably not generally useful outside Informatica.

## Usage

### Database location and credentials

Specify database location and credentials with the following environment variables.

* `DB_HOST`
* `DB_SERVICE`
* `DB_USERNAME`
* `DB_PASSWORD`

These `DB_*` environment variables describe how to connect to the Oracle database with the organizational data.

### Email credentials

Specify SMTP host and credentials with the following environment variables.

* `SMTP_FROM`
* `SMTP_HOST`
* `SMTP_USERNAME`
* `SMTP_PASSWORD`

If you are sending email with Amazon SES, you can specify a configuration set by name in the environment variable
`AWS_SES_CONFIGURATION_SET`. The value of this variable will be added to outgoing emails in the
`X-SES-CONFIGURATION-SET` header.

Specify report recipients with the environment variable `REPORT_RECIPIENTS`. Separate multiple email addresses with a
space.

### Time zone

Once started, the tool will wait until 06:00 in the time zone specified by the `TZ` environment variable, then run.
