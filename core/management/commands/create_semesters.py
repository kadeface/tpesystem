"""
创建学期数据的管理命令。

此命令用于批量创建连续多个学年的学期数据。
"""

from django.core.management.base import BaseCommand
from core.models import Semester
from datetime import date

class Command(BaseCommand):
    """
    创建学期数据的管理命令。
    
    批量创建多个学年的学期数据，自动设置开始和结束日期。
    
    Args:
        BaseCommand: Django管理命令基类
    
    Returns:
        无
    """
    
    help = '批量创建学期数据'
    
    def add_arguments(self, parser):
        """
        添加命令行参数配置。
        
        Args:
            parser: 参数解析器对象
            
        Returns:
            无
        """
        parser.add_argument('--start_year', type=int, help='起始学年的开始年份', required=True)
        parser.add_argument('--num_years', type=int, help='要创建的学年数量', default=1)
        parser.add_argument('--debug', action='store_true', help='启用调试模式')
    
    def handle(self, *args, **options):
        """
        命令处理主函数。
        
        Args:
            *args: 位置参数
            **options: 关键字参数，包含命令行选项
            
        Returns:
            无
        """
        start_year = options['start_year']
        num_years = options['num_years']
        debug = options['debug']
        
        created_count = 0
        
        # 遍历学年
        for i in range(num_years):
            year_start = start_year + i
            year_end = year_start + 1
            academic_year = f"{year_start}-{year_end}"
            
            # 第一学期（秋季学期：9月-1月）
            semester_id_1 = f"{academic_year}-1"
            semester_name_1 = f"{academic_year}学年第一学期"
            start_date_1 = date(year_start, 9, 1)  # 9月1日
            end_date_1 = date(year_start + 1, 1, 31)  # 次年1月31日
            
            # 第二学期（春季学期：2月-7月）
            semester_id_2 = f"{academic_year}-2"
            semester_name_2 = f"{academic_year}学年第二学期"
            start_date_2 = date(year_start + 1, 2, 1)  # 次年2月1日
            end_date_2 = date(year_start + 1, 7, 31)  # 次年7月31日
            
            # 创建第一学期
            semester1, created1 = Semester.objects.get_or_create(
                semester_id=semester_id_1,
                defaults={
                    'year': academic_year,  # 使用学年
                    'term': '1',            # 第一学期
                    'start_date': start_date_1,
                    'end_date': end_date_1,
                    'status': 'ACTIVE'
                }
            )
            
            if created1:
                created_count += 1
                if debug:
                    self.stdout.write(f"创建学期: {semester_name_1} (ID: {semester_id_1})")
            else:
                if debug:
                    self.stdout.write(f"学期已存在: {semester_name_1} (ID: {semester_id_1})")
            
            # 创建第二学期
            semester2, created2 = Semester.objects.get_or_create(
                semester_id=semester_id_2,
                defaults={
                    'year': academic_year,  # 使用学年
                    'term': '2',            # 第二学期
                    'start_date': start_date_2,
                    'end_date': end_date_2,
                    'status': 'ACTIVE'
                }
            )
            
            if created2:
                created_count += 1
                if debug:
                    self.stdout.write(f"创建学期: {semester_name_2} (ID: {semester_id_2})")
            else:
                if debug:
                    self.stdout.write(f"学期已存在: {semester_name_2} (ID: {semester_id_2})")
        
        self.stdout.write(self.style.SUCCESS(f"完成学期创建: 共创建 {created_count} 个学期")) 