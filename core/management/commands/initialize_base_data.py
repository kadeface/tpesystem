"""
初始化系统基础数据的管理命令。

此命令用于创建系统运行所需的基础数据，包括学期和默认教师等。
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import Semester, Teacher, School, Region
from datetime import date

class Command(BaseCommand):
    """
    初始化系统基础数据的Django管理命令。
    
    创建系统运行所需的学期记录和教师记录。
    
    Args:
        BaseCommand: Django管理命令基类
    
    Returns:
        无
    """
    
    help = '初始化系统基础数据（学期、教师等）'
    
    def add_arguments(self, parser):
        """
        添加命令行参数配置。
        
        Args:
            parser: 参数解析器对象
            
        Returns:
            无
        """
        parser.add_argument('--school_id', type=str, help='默认学校ID', default='SCH001')
        parser.add_argument('--school_name', type=str, help='默认学校名称', default='示范学校')
        parser.add_argument('--region_id', type=str, help='默认区域ID', default='REG001')
        parser.add_argument('--region_name', type=str, help='默认区域名称', default='示范区')
        parser.add_argument('--force', action='store_true', help='强制重新创建已存在的记录')
    
    def handle(self, *args, **options):
        """
        命令处理主函数。
        
        Args:
            *args: 位置参数
            **options: 关键字参数，包含命令行选项
            
        Returns:
            无
        """
        school_id = options['school_id']
        school_name = options['school_name']
        region_id = options['region_id']
        region_name = options['region_name']
        force = options['force']
        
        try:
            with transaction.atomic():
                # 1. 创建默认区域
                region, created = Region.objects.get_or_create(
                    region_id=region_id,
                    defaults={
                        'region_name': region_name,
                        'level': 'DISTRICT',
                        'description': f'{region_name}教育区'
                    }
                )
                if created:
                    self.stdout.write(self.style.SUCCESS(f'创建区域: {region_name}'))
                else:
                    self.stdout.write(f'区域已存在: {region_name}')
                
                # 2. 创建默认学校
                school, created = School.objects.get_or_create(
                    school_id=school_id,
                    defaults={
                        'school_name': school_name,
                        'school_type': 'JUNIOR',  # 默认为初中
                        'school_nature': 'PUBLIC',  # 公立学校
                        'region': region,
                        'address': f'{region_name}{school_name}地址',
                        'phone': '010-12345678',
                        'email': 'example@school.edu.cn',
                        'principal': '张校长',
                        'status': 'ACTIVE'
                    }
                )
                if created:
                    self.stdout.write(self.style.SUCCESS(f'创建学校: {school_name}'))
                else:
                    self.stdout.write(f'学校已存在: {school_name}')
                
                # 3. 创建常用学期记录
                current_year = date.today().year
                semesters_to_create = [
                    # 上一学年
                    {
                        'semester_id': f'{current_year-1}-1',
                        'year': f'{current_year-1}-{current_year}',
                        'term': '1',
                        'start_date': date(current_year-1, 9, 1),
                        'end_date': date(current_year, 1, 31)
                    },
                    {
                        'semester_id': f'{current_year-1}-2',
                        'year': f'{current_year-1}-{current_year}',
                        'term': '2',
                        'start_date': date(current_year, 2, 1),
                        'end_date': date(current_year, 7, 31)
                    },
                    # 当前学年
                    {
                        'semester_id': f'{current_year}-1',
                        'year': f'{current_year}-{current_year+1}',
                        'term': '1',
                        'start_date': date(current_year, 9, 1),
                        'end_date': date(current_year+1, 1, 31)
                    },
                    {
                        'semester_id': f'{current_year}-2',
                        'year': f'{current_year}-{current_year+1}',
                        'term': '2',
                        'start_date': date(current_year+1, 2, 1),
                        'end_date': date(current_year+1, 7, 31)
                    }
                ]
                
                semester_count = 0
                for sem_data in semesters_to_create:
                    semester, created = Semester.objects.get_or_create(
                        semester_id=sem_data['semester_id'],
                        defaults={
                            'year': sem_data['year'],
                            'term': sem_data['term'],
                            'start_date': sem_data['start_date'],
                            'end_date': sem_data['end_date']
                        }
                    )
                    if created:
                        semester_count += 1
                        self.stdout.write(self.style.SUCCESS(
                            f"创建学期: {sem_data['year']}学年第{sem_data['term']}学期"
                        ))
                
                self.stdout.write(f'总共创建 {semester_count} 个学期记录')
                
                # 4. 创建默认教师
                teachers_to_create = [
                    {
                        'teacher_id': 'T001',
                        'name': '张老师',
                        'gender': 'M',
                        'birth_date': date(1980, 1, 1),
                        'qualification': 'SENIOR'
                    },
                    {
                        'teacher_id': 'T002',
                        'name': '王老师',
                        'gender': 'F',
                        'birth_date': date(1985, 6, 15),
                        'qualification': 'MIDDLE'
                    }
                ]
                
                teacher_count = 0
                for teacher_data in teachers_to_create:
                    teacher, created = Teacher.objects.get_or_create(
                        teacher_id=teacher_data['teacher_id'],
                        defaults={
                            'name': teacher_data['name'],
                            'gender': teacher_data['gender'],
                            'birth_date': teacher_data['birth_date'],
                            'phone': '13800138000',
                            'email': f"{teacher_data['name']}@example.com",
                            'current_school': school,
                            'qualification': teacher_data['qualification'],
                            'status': 'ACTIVE'
                        }
                    )
                    if created:
                        teacher_count += 1
                        self.stdout.write(self.style.SUCCESS(
                            f"创建教师: {teacher_data['name']} (ID: {teacher_data['teacher_id']})"
                        ))
                
                self.stdout.write(f'总共创建 {teacher_count} 个教师记录')
                
            self.stdout.write(self.style.SUCCESS('基础数据初始化完成!'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'初始化过程出错: {str(e)}')) 