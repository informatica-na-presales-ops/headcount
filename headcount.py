import apscheduler.schedulers.blocking
import cx_Oracle
import datetime
import email
import jinja2
import logging
import os
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
        sql = '''
            WITH e AS (
                SELECT EMPLOYEE_ID, EMPLOYEE_NAME, BUSINESS_TITLE, WORKER_STATUS, EMPLOYEE_TYPE, JOB_CODE, JOB_TITLE,
                    JOB_FAMILY, COST_CENTER, MANAGER, MANAGEMENT_LEVEL, EMAIL_PRIMARY_WORK,
                    ROW_NUMBER() OVER (PARTITION BY EMPLOYEE_ID ORDER BY HIRE_DATE DESC) JOB_RANK
                FROM SALES_DM.V_WD_PUBLIC_HC_TERM_COMBINED
                WHERE SNAP_DATE = :snap_date
            )
            SELECT EMPLOYEE_ID, EMPLOYEE_NAME, BUSINESS_TITLE, WORKER_STATUS, EMPLOYEE_TYPE, JOB_CODE, JOB_TITLE,
                JOB_FAMILY, COST_CENTER, MANAGER, MANAGEMENT_LEVEL, EMAIL_PRIMARY_WORK
            FROM e
            WHERE JOB_RANK = 1
        '''
        params = {
            'snap_date': day
        }
        return self.q(sql, params)


class Settings:
    def __init__(self):
        self.aws_ses_configuration_set = os.getenv('AWS_SES_CONFIGURATION_SET')
        self.db_host = os.getenv('DB_HOST')
        self.db_service = os.getenv('DB_SERVICE')
        self.db_password = os.getenv('DB_PASSWORD')
        self.db_username = os.getenv('DB_USERNAME')
        self.log_format = os.getenv('LOG_FORMAT', '%(levelname)s [%(name)s] %(message)s')
        self.log_level = os.getenv('LOG_LEVEL', 'INFO')
        self.report_recipients = os.getenv('REPORT_RECIPIENTS', '').split()
        self.smtp_from = os.getenv('SMTP_FROM')
        self.smtp_host = os.getenv('SMTP_HOST')
        self.smtp_username = os.getenv('SMTP_USERNAME')
        self.smtp_password = os.getenv('SMTP_PASSWORD')
        self.template_path = os.getenv('TEMPLATE_PATH', '/headcount/templates')
        self.version = os.getenv('APP_VERSION', 'unknown')

    @property
    def db(self) -> Database:
        return Database(self)


def get_changes(db: Database) -> List[Dict]:
    old_day = datetime.date.today() - datetime.timedelta(days=1)
    old_dict = {r.get('employee_id'): r for r in db.get_data(old_day)}
    log.debug(f'Number of old records: {len(old_dict)}')
    results = []
    for new in db.get_data(datetime.date.today()):
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
    msg.set_content(body)
    with smtplib.SMTP_SSL(host=settings.smtp_host) as s:
        s.login(user=settings.smtp_username, password=settings.smtp_password)
        try:
            s.send_message(msg)
        except smtplib.SMTPRecipientsRefused as e:
            log.error(f'{e}')
            return False
    return True


def main_job(settings: Settings):
    start = datetime.datetime.utcnow()
    check_date = datetime.date.today()
    log.info(f'Getting changes for {check_date}')
    changes = get_changes(settings.db)
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

    scheduler = apscheduler.schedulers.blocking.BlockingScheduler()
    scheduler.add_job(main_job, 'cron', hour=6, args=[settings])

    scheduler.start()


def handle_sigterm(_signal, _frame):
    sys.exit()


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, handle_sigterm)
    main()
