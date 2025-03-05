from django.core.management.base import BaseCommand
from django.db import connections
from django.db.utils import OperationalError

class Command(BaseCommand):
    help = '测试数据库连接'

    def handle(self, *args, **kwargs):
        try:
            db_conn = connections['default']
            db_conn.cursor()
            self.stdout.write(self.style.SUCCESS('数据库连接成功'))
        except OperationalError:
            self.stdout.write(self.style.ERROR('数据库连接失败，请检查配置')) 