import apscheduler.schedulers.blocking
import cx_Oracle
import datetime
import email
import jinja2
import logging
import os
import pathlib
import signal
import smtplib
import sys

from typing import Dict, List, Optional

log = logging.getLogger(__name__)


class Database:
    def __init__(self, settings):
        self.settings = settings
        self.cnx = cx_Oracle.connect(user=settings.db_username, password=settings.db_password,
                                     dsn=f'{settings.db_host}/{settings.db_service}')

    @staticmethod
    def make_dict_factory(cursor):
        col_names = [d[0].lower() for d in cursor.description]

        def convert_row(*args):
            return dict(zip(col_names, args))

        return convert_row

    def q(self, sql: str, params: Dict = None) -> List[Dict]:
        if params is None:
            params = {}
        with self.cnx.cursor() as c:
            c.execute(sql, params)
            c.rowfactory = self.make_dict_factory(c)
            return c.fetchall()

    def q_one(self, sql: str, params: Dict = None) -> Optional[Dict]:
        for r in self.q(sql, params):
            return r

    def get_data(self, day: datetime.date) -> List[Dict]:
        # This query is complicated because sometimes there are multiple records for a single employee on a single day.
        # For example, an employee can be both a terminated contractor and an active regular employee on the same day.
        # Calls to CAST_TO_RAW help with text encoding problems.
        sql = '''
            WITH E AS (
                SELECT
                    EMPLOYEE_ID, WORKER_STATUS, EMPLOYEE_TYPE, JOB_CODE, JOB_TITLE, JOB_FAMILY, COST_CENTER,
                    MANAGEMENT_LEVEL, EMAIL_PRIMARY_WORK,
                    UTL_RAW.CAST_TO_RAW(EMPLOYEE_NAME) EMPLOYEE_NAME_RAW,
                    UTL_RAW.CAST_TO_RAW(BUSINESS_TITLE) BUSINESS_TITLE_RAW,
                    UTL_RAW.CAST_TO_RAW(MANAGER) MANAGER_RAW,
                    ROW_NUMBER() OVER (PARTITION BY EMPLOYEE_ID ORDER BY HIRE_DATE DESC) JOB_RANK
                FROM SALES_DM.V_WD_PUBLIC_HC_TERM_COMBINED
                WHERE SNAP_DATE = :snap_date
            )
            SELECT
                EMPLOYEE_ID, WORKER_STATUS, EMPLOYEE_TYPE, JOB_CODE, JOB_TITLE, JOB_FAMILY, COST_CENTER,
                MANAGEMENT_LEVEL, EMAIL_PRIMARY_WORK, EMPLOYEE_NAME_RAW, BUSINESS_TITLE_RAW, MANAGER_RAW
            FROM E
            WHERE JOB_RANK = 1
        '''
        params = {
            'snap_date': day
        }
        result = self.q(sql, params)
        for r in result:
            r['employee_name'] = r.get('employee_name_raw').decode()
            if r.get('business_title_raw') is None:
                r['business_title'] = None
            else:
                r['business_title'] = r.get('business_title_raw').decode()
            if r.get('manager_raw') is None:
                r['manager'] = None
            else:
                r['manager'] = r.get('manager_raw').decode()
        return result


class Settings:
    _true_values = ('true', '1', 'on', 'yes')

    def __init__(self):
        self.aws_ses_configuration_set = os.getenv('AWS_SES_CONFIGURATION_SET')
        self.custom_date = datetime.datetime.strptime(os.getenv('CUSTOM_DATE', '0001-01-01'), '%Y-%m-%d').date()
        self.db_host = os.getenv('DB_HOST')
        self.db_service = os.getenv('DB_SERVICE')
        self.db_password = os.getenv('DB_PASSWORD')
        self.db_username = os.getenv('DB_USERNAME')
        self.log_format = os.getenv('LOG_FORMAT', '%(levelname)s [%(name)s] %(message)s')
        self.log_level = os.getenv('LOG_LEVEL', 'INFO')
        self.report_recipients = os.getenv('REPORT_RECIPIENTS', '').split()
        self.run_hour = int(os.getenv('RUN_HOUR', '8'))
        self.run_and_exit = os.getenv('RUN_AND_EXIT', 'False').lower() in self._true_values
        self.smtp_from = os.getenv('SMTP_FROM')
        self.smtp_host = os.getenv('SMTP_HOST')
        self.smtp_username = os.getenv('SMTP_USERNAME')
        self.smtp_password = os.getenv('SMTP_PASSWORD')
        self.template_path = pathlib.Path(os.getenv('TEMPLATE_PATH', '/headcount/templates'))
        self.version = os.getenv('APP_VERSION', 'unknown')

    @property
    def db(self) -> Database:
        return Database(self)


def get_changes(db: Database, check_date: datetime.date) -> List[Dict]:
    old_day = check_date - datetime.timedelta(days=1)
    old_dict = {r.get('employee_id'): r for r in db.get_data(old_day)}
    log.debug(f'Number of old records: {len(old_dict)}')
    results = []
    for new in db.get_data(check_date):
        employee_id = new.get('employee_id')
        log.debug(f'Checking {employee_id}')
        old = old_dict.get(employee_id)
        if old is None:
            results.append({
                'result': 'added',
                'data': new
            })
        else:
            changes = []
            for field in ('employee_name', 'last_name', 'first_name', 'business_title', 'worker_status',
                          'employee_type', 'job_code', 'job_title', 'job_family', 'cost_center', 'manager',
                          'management_level', 'email_primary_work'):
                old_value = old.get(field)
                new_value = new.get(field)
                if not old_value == new_value:
                    changes.append({'field': field, 'old': old_value, 'new': new_value})
            if changes:
                results.append({
                    'result': 'changed',
                    'data': new,
                    'changes': changes
                })
    return results


def send_email(settings, subject, body) -> bool:
    """Send an email. Return True if successful, False if not."""
    log.warning(f'Sending email to {settings.report_recipients}')
    msg = email.message.EmailMessage()
    msg['X-SES-CONFIGURATION-SET'] = settings.aws_ses_configuration_set
    msg['Subject'] = subject
    msg['From'] = settings.smtp_from
    msg['To'] = settings.report_recipients
    msg.set_content(body, subtype='html')
    with smtplib.SMTP_SSL(host=settings.smtp_host) as s:
        s.login(user=settings.smtp_username, password=settings.smtp_password)
        try:
            s.send_message(msg)
        except smtplib.SMTPRecipientsRefused as e:
            log.error(f'{e}')
            return False
    return True


def main_job(settings: Settings, check_date: datetime.date = None):
    start = datetime.datetime.utcnow()
    if check_date is None:
        check_date = datetime.date.today()
    log.info(f'Getting changes for {check_date}')
    changes = get_changes(settings.db, check_date)
    log.debug(changes)
    loader = jinja2.FileSystemLoader(settings.template_path)
    jinja_env = jinja2.Environment(trim_blocks=True, lstrip_blocks=True, loader=loader)
    template = jinja_env.get_template('changes-report.jinja2')
    report = template.render(check_date=check_date, changes=changes)
    send_email(settings, f'Organizational changes for {check_date}', report)
    log.info(f'Duration: {datetime.datetime.utcnow() - start}')


def main():
    settings = Settings()
    logging.basicConfig(format=settings.log_format, level='DEBUG', stream=sys.stdout)
    log.debug(f'headcount {settings.version}')
    if not settings.log_level == 'DEBUG':
        log.debug(f'Changing log level to {settings.log_level}')
    logging.getLogger().setLevel(settings.log_level)

    log.info(f'RUN_AND_EXIT: {settings.run_and_exit}')
    if settings.run_and_exit:
        check_date = settings.custom_date
        if check_date.year == 1:
            check_date = datetime.date.today()
        main_job(settings, check_date)
    else:
        scheduler = apscheduler.schedulers.blocking.BlockingScheduler()
        scheduler.add_job(main_job, 'cron', hour=settings.run_hour, args=[settings])
        scheduler.start()


def handle_sigterm(_signal, _frame):
    sys.exit()


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, handle_sigterm)
    main()
