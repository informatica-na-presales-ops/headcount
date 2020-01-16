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

### Report date

By default, the tool will report on organizational changes for the current day. If you want to report on a different
day, set the environment variable `CHECK_DATE` to an [ISO 8601][a] date, e.g. `2020-01-16`.

[a]: https://www.iso.org/iso-8601-date-and-time-format.html

### Report output folder

Set the environment variable `REPORT_PATH` to a folder where the reports will be generated. The default value is
`/reports`, so it is usually sufficient to mount a volume in the container at that path.
