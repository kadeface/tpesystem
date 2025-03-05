from django.core.management.base import BaseCommand
from django.db import connections

class Command(BaseCommand):
    help = '检查数据库字段长度限制'
    
    def handle(self, *args, **options):
        with connections['default'].cursor() as cursor:
            cursor.execute("""
                SELECT table_name, column_name, character_maximum_length 
                FROM information_schema.columns 
                WHERE table_schema = 'public'
                AND data_type = 'character varying'
                ORDER BY table_name, column_name
            """)
            self.stdout.write("表名\t列名\t最大长度")
            for row in cursor.fetchall():
                self.stdout.write(f"{row[0]}\t{row[1]}\t{row[2]}") 