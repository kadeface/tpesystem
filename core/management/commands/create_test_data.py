from django.core.management.base import BaseCommand
from core.models import Region, Semester, School, Grade, Class
from datetime import date

class Command(BaseCommand):
    help = '创建测试数据'

    def handle(self, *args, **kwargs):
        # 创建区域
        region1, _ = Region.objects.get_or_create(
            region_id='REG001',
            defaults={
                'region_name': '朝阳区',
                'level': 'DISTRICT',
                'description': '北京市朝阳区'
            }
        )
        
        # 创建学期
        semester1, _ = Semester.objects.get_or_create(
            semester_id='SEM001',
            defaults={
                'year': '2023-2024',
                'term': '1',
                'start_date': date(2023, 9, 1),
                'end_date': date(2024, 1, 15)
            }
        )
        
        # 创建学校
        school1, _ = School.objects.get_or_create(
            school_id='SCH001',
            defaults={
                'school_name': '朝阳第一中学',
                'school_type': 'HIGH',
                'school_nature': 'PUBLIC',
                'address': '北京市朝阳区xxx路xx号',
                'phone': '010-12345678',
                'email': 'school1@example.com',
                'principal': '张校长',
                'region': region1
            }
        )
        
        self.stdout.write(self.style.SUCCESS('成功创建测试数据')) 