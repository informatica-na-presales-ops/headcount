import cx_Oracle
import datetime
import jinja2
import logging
import os
import pathlib
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
        env_check_date = os.getenv('CHECK_DATE')
        if env_check_date is None:
            self.check_date = datetime.date.today()
        else:
            self.check_date = datetime.datetime.strptime(env_check_date, '%Y-%m-%d').date()
        self.db_host = os.getenv('DB_HOST')
        self.db_service = os.getenv('DB_SERVICE')
        self.db_password = os.getenv('DB_PASSWORD')
        self.db_username = os.getenv('DB_USERNAME')
        self.log_format = os.getenv('LOG_FORMAT', '%(levelname)s [%(name)s] %(message)s')
        self.log_level = os.getenv('LOG_LEVEL', 'INFO')
        self.report_path = pathlib.Path(os.getenv('REPORT_PATH', '/reports')).resolve()
        self.template_path = os.getenv('TEMPLATE_PATH', '/headcount/templates')
        self.version = os.getenv('APP_VERSION', 'unknown')

    @property
    def db(self) -> Database:
        return Database(self)


def get_changes(settings: Settings) -> List[Dict]:
    old_day = settings.check_date - datetime.timedelta(days=1)
    old_dict = {r.get('employee_id'): r for r in settings.db.get_data(old_day)}
    log.debug(f'Number of old records: {len(old_dict)}')
    results = []
    for new in settings.db.get_data(settings.check_date):
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


def main():
    settings = Settings()
    logging.basicConfig(format=settings.log_format, level='DEBUG', stream=sys.stdout)
    log.debug(f'headcount {settings.version}')
    if not settings.log_level == 'DEBUG':
        log.debug(f'Changing log level to {settings.log_level}')
    logging.getLogger().setLevel(settings.log_level)

    start = datetime.datetime.utcnow()
    log.info(f'Getting changes for {settings.check_date}')
    changes = get_changes(settings)
    log.debug(changes)
    jinja_env = jinja2.Environment(trim_blocks=True, lstrip_blocks=True,
                                   loader=jinja2.FileSystemLoader(settings.template_path))
    template = jinja_env.get_template('changes-report.jinja2')
    report = template.render(settings=settings, changes=changes)
    report_file = settings.report_path / f'{settings.check_date}.txt'
    log.info(f'Writing report to {report_file}')
    with report_file.open('w') as f:
        f.write(report)
    log.info(f'Duration: {datetime.datetime.utcnow() - start}')


if __name__ == '__main__':
    main()
