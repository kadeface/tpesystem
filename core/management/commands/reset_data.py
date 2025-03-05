"""
重置系统数据的管理命令。

此命令清空系统中的所有或部分业务数据，为重新导入数据做准备。
支持选择性清空特定表，保留基础数据。
"""

from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.apps import apps
from core.models import Score, StudentHistory, Exam, TeacherSubjectClass, TeacherSubject, Student, Class, Grade, School, Teacher, Semester, Family, Region, Subject

class Command(BaseCommand):
    """
    重置系统数据的Django管理命令。
    
    按照特定顺序清空表，避免外键约束问题。
    支持选择性清空特定表，保留其他数据。
    
    Args:
        BaseCommand: Django管理命令基类
    
    Returns:
        无
    """
    
    help = '清空系统中的业务数据，支持选择性清空特定表'
    
    def add_arguments(self, parser):
        parser.add_argument('--confirm', action='store_true', help='确认执行数据重置')
        parser.add_argument('--keep-settings', action='store_true', help='保留学期、区域和学科等基础设置数据') #python manage.py reset_data --confirm --keep-settings
        parser.add_argument('--only', nargs='+', help='只清空指定的表(score, history, exam, tsc, ts, student, class, grade)') #python manage.py reset_data --confirm --keep-settings --only score exam
    
    def handle(self, *args, **options):
        confirm = options.get('confirm', False)
        keep_settings = options.get('keep_settings', False)
        only_tables = options.get('only') or []
        
        # 将only_tables转换为小写以便比较
        only_tables = [t.lower() for t in only_tables]
        
        if not confirm:
            self.stdout.write(self.style.WARNING('警告: 此操作将清空数据!'))
            self.stdout.write('如果您确认要执行此操作，请添加 --confirm 参数:')
            self.stdout.write('python manage.py reset_data --confirm')
            return
        
        # 检查是否只清空特定表
        is_selective = len(only_tables) > 0
        
        def should_clear(table_name):
            if not is_selective:
                return True
            return table_name in only_tables
        
        try:
            with transaction.atomic():
                # 按依赖关系顺序清空数据
                self.stdout.write('开始清空数据...')
                
                # 1. 清空成绩数据
                if should_clear('score'):
                    count = Score.objects.all().delete()[0]
                    self.stdout.write(f'  - 成绩数据: {count} 条记录已删除')
                
                # 2. 清空学生历史记录
                if should_clear('history'):
                    count = StudentHistory.objects.all().delete()[0]
                    self.stdout.write(f'  - 学生历史记录: {count} 条记录已删除')
                
                # 3. 清空考试数据
                if should_clear('exam'):
                    count = Exam.objects.all().delete()[0]
                    self.stdout.write(f'  - 考试数据: {count} 条记录已删除')
                
                # 4. 清空教师-学科-班级关联
                if should_clear('tsc'):
                    count = TeacherSubjectClass.objects.all().delete()[0]
                    self.stdout.write(f'  - 教师-学科-班级关联: {count} 条记录已删除')
                
                # 5. 清空教师-学科关联
                if should_clear('ts'):
                    count = TeacherSubject.objects.all().delete()[0]
                    self.stdout.write(f'  - 教师-学科关联: {count} 条记录已删除')
                
                # 6. 清空学生数据
                if should_clear('student'):
                    count = Student.objects.all().delete()[0]
                    self.stdout.write(f'  - 学生数据: {count} 条记录已删除')
                
                # 7. 清空班级数据
                if should_clear('class'):
                    count = Class.objects.all().delete()[0]
                    self.stdout.write(f'  - 班级数据: {count} 条记录已删除')
                
                # 8. 清空年级数据
                if should_clear('grade'):
                    count = Grade.objects.all().delete()[0]
                    self.stdout.write(f'  - 年级数据: {count} 条记录已删除')
                
                if not keep_settings and not is_selective:
                    # 9. 清空学校数据
                    count = School.objects.all().delete()[0]
                    self.stdout.write(f'  - 学校数据: {count} 条记录已删除')
                    
                    # 10. 清空教师数据
                    count = Teacher.objects.all().delete()[0]
                    self.stdout.write(f'  - 教师数据: {count} 条记录已删除')
                    
                    # 11. 清空学期数据
                    count = Semester.objects.all().delete()[0]
                    self.stdout.write(f'  - 学期数据: {count} 条记录已删除')
                    
                    # 12. 清空家庭数据
                    count = Family.objects.all().delete()[0]
                    self.stdout.write(f'  - 家庭数据: {count} 条记录已删除')
                    
                    # 13. 清空区域数据
                    count = Region.objects.all().delete()[0]
                    self.stdout.write(f'  - 区域数据: {count} 条记录已删除')
                    
                    # 14. 清空学科数据
                    count = Subject.objects.all().delete()[0]
                    self.stdout.write(f'  - 学科数据: {count} 条记录已删除')
                else:
                    if is_selective:
                        self.stdout.write(self.style.SUCCESS('  - 仅清空指定的表，保留其他数据'))
                    else:
                        self.stdout.write(self.style.SUCCESS('  - 已保留学期、区域、学校、教师和学科等基础设置数据'))
                
                self.stdout.write(self.style.SUCCESS('数据清空完成!'))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'数据清空过程中出错: {str(e)}')) 