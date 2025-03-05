"""
学校数据导入命令。

此模块实现从CSV文件导入学校数据到数据库的功能。
"""

import csv
import os
from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import Region, School

class Command(BaseCommand):
    """
    导入学校数据的管理命令。
    
    Args:
        BaseCommand: Django管理命令基类
    
    Returns:
        None
    """
    help = '从CSV文件导入学校数据'

    def add_arguments(self, parser):
        """
        添加命令参数。
        
        Args:
            parser: 参数解析器
        
        Returns:
            None
        """
        parser.add_argument('file_path', type=str, help='CSV文件的路径')

    def handle(self, *args, **options):
        """
        命令处理主函数。
        
        Args:
            args: 位置参数
            options: 命名参数
        
        Returns:
            None
        """
        file_path = options['file_path']
        
        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR(f'文件不存在: {file_path}'))
            return
        
        self.stdout.write(self.style.NOTICE('开始导入学校数据...'))
        
        # 使用事务处理确保数据完整性
        with transaction.atomic():
            # 使用utf-8编码打开CSV文件
            with open(file_path, 'r', encoding='utf-8') as file:
                # 定义列名，因为输入CSV没有标题行
                fieldnames = ['id', 'district_id', 'school_code', 'school_name', 'school_type', 'school_level', 'created_at', 'updated_at']
                reader = csv.DictReader(file, fieldnames=fieldnames)
                
                school_count = 0
                error_count = 0
                
                for row in reader:
                    try:
                        # 获取或创建对应的区域
                        region, _ = Region.objects.get_or_create(
                            region_id=row['district_id'],
                            defaults={
                                'region_name': f'区域{row["district_id"]}',
                                'level': 'DISTRICT'
                            }
                        )
                        
                        # 根据school_level确定学校类型
                        if row['school_level'] == 'P':
                            school_type = 'PRIMARY'
                        elif row['school_level'] == 'M':
                            school_type = 'JUNIOR'
                        elif row['school_level'] == 'H':
                            school_type = 'HIGH'
                        else:
                            # 默认为小学
                            school_type = 'PRIMARY'
                        
                        # 创建或更新学校
                        school, created = School.objects.update_or_create(
                            school_id=row['school_code'],
                            defaults={
                                'school_name': row['school_name'],
                                'school_type': school_type,
                                'school_nature': 'PUBLIC',  # 默认为公立
                                'region': region,
                                'address': '',  # 默认空
                                'phone': '',    # 默认空
                                'email': '',    # 默认空
                                'principal': '' # 默认空
                            }
                        )
                        
                        school_count += 1
                        status = '新建' if created else '更新'
                        self.stdout.write(self.style.SUCCESS(f'{status}学校: {school.school_name}'))
                    
                    except Exception as e:
                        error_count += 1
                        self.stdout.write(self.style.ERROR(f'处理行时出错: {row}, 错误: {str(e)}'))
        
        self.stdout.write(self.style.SUCCESS(f'导入完成! 成功导入 {school_count} 所学校, 失败 {error_count} 条记录。')) 