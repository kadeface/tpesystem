"""
重置系统数据的管理命令。

此命令清空系统中的所有或部分业务数据，为重新导入数据做准备。
支持选择性清空特定表，保留基础数据。
"""

from django.core.management.base import BaseCommand
from django.db import connection

from core.models import Score, StudentHistory, Exam, TeacherSubjectClass, TeacherSubject, Student, Class, Grade, School, Teacher, Semester, Family, Region, Subject, TeacherHistory

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
        parser.add_argument('--backup', action='store_true', help='在重置数据前创建数据库备份')
        parser.add_argument('--backup-dir', default='backups', help='备份文件保存目录')
    
    def handle(self, *args, **options):
        confirm = options.get('confirm', False)
        keep_settings = options.get('keep_settings', False)
        only_tables = options.get('only') or []
        create_backup = options.get('backup', False)
        backup_dir = options.get('backup_dir')
        
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
        
        # 如果需要创建备份
        if create_backup:
            self.stdout.write('在清空数据前创建数据库备份...')
            from django.core.management import call_command
            try:
                call_command('backup_db', output_dir=backup_dir)
                self.stdout.write(self.style.SUCCESS('数据库备份成功，继续执行数据清空...'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'数据库备份失败: {str(e)}'))
                self.stdout.write(self.style.WARNING('数据库备份失败，是否继续清空数据?(y/n):'))
                answer = input().strip().lower()
                if answer != 'y':
                    self.stdout.write('取消数据清空操作。')
                    return
        
        try:
            self.stdout.write('开始清空数据...')
            
            # 对于有问题的表，使用原生SQL删除
            with connection.cursor() as cursor:
                try:
                    # 注意TRUNCATE可能会导致约束问题，所以使用DELETE
                    cursor.execute("DELETE FROM core_score;")
                    self.stdout.write(f'  - Score数据已通过SQL清空')
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'SQL删除Score数据失败: {str(e)}'))
            
            # 2. 清空学生历史记录
            if should_clear('history'):
                self.stdout.write(f'  尝试清空 StudentHistory 数据...')
                try:
                    count = StudentHistory.objects.all().delete()[0]
                    self.stdout.write(f'  已成功清空 StudentHistory 数据: {count} 条记录已删除')
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'SQL删除StudentHistory数据失败: {str(e)}'))
            
            # 3. 清空考试数据
            if should_clear('exam'):
                self.stdout.write(f'  尝试清空 Exam 数据...')
                try:
                    count = Exam.objects.all().delete()[0]
                    self.stdout.write(f'  已成功清空 Exam 数据: {count} 条记录已删除')
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'SQL删除Exam数据失败: {str(e)}'))
            
            # 4. 清空教师-学科-班级关联
            if should_clear('tsc'):
                self.stdout.write(f'  尝试清空 TeacherSubjectClass 数据...')
                try:
                    count = TeacherSubjectClass.objects.all().delete()[0]
                    self.stdout.write(f'  已成功清空 TeacherSubjectClass 数据: {count} 条记录已删除')
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'SQL删除TeacherSubjectClass数据失败: {str(e)}'))
            
            # 5. 清空教师-学科关联
            if should_clear('ts'):
                self.stdout.write(f'  尝试清空 TeacherSubject 数据...')
                try:
                    count = TeacherSubject.objects.all().delete()[0]
                    self.stdout.write(f'  已成功清空 TeacherSubject 数据: {count} 条记录已删除')
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'SQL删除TeacherSubject数据失败: {str(e)}'))
            
            # 6. 清空学生数据
            if should_clear('student'):
                self.stdout.write(f'  尝试清空 Student 数据...')
                try:
                    count = Student.objects.all().delete()[0]
                    self.stdout.write(f'  已成功清空 Student 数据: {count} 条记录已删除')
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'SQL删除Student数据失败: {str(e)}'))
            
            # 7. 清空班级数据
            if should_clear('class'):
                self.stdout.write(f'  尝试清空 Class 数据...')
                try:
                    count = Class.objects.all().delete()[0]
                    self.stdout.write(f'  已成功清空 Class 数据: {count} 条记录已删除')
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'SQL删除Class数据失败: {str(e)}'))
            
            # 8. 清空年级数据
            if should_clear('grade'):
                self.stdout.write(f'  尝试清空 Grade 数据...')
                try:
                    count = Grade.objects.all().delete()[0]
                    self.stdout.write(f'  已成功清空 Grade 数据: {count} 条记录已删除')
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'SQL删除Grade数据失败: {str(e)}'))
            
            # 9. 清空教师历史记录 (不再删除教师数据)
            if should_clear('teacher_history') or (not keep_settings and not is_selective):
                self.stdout.write(f'  尝试清空 TeacherHistory 数据...')
                try:
                    # TeacherHistory如果引用Teacher，先断开引用
                    with connection.cursor() as cursor:
                        try:
                            cursor.execute("UPDATE core_teacherhistory SET teacher_id = NULL;")
                            self.stdout.write(f'  - 已断开TeacherHistory与Teacher的关联')
                        except Exception as e:
                            self.stdout.write(self.style.ERROR(f'断开关联失败: {str(e)}'))

                    # 只删除教师历史记录，保留教师数据
                    count = TeacherHistory.objects.all().delete()[0]
                    self.stdout.write(f'  已成功清空 TeacherHistory 数据: {count} 条记录已删除')
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'删除TeacherHistory数据失败: {str(e)}'))
            
            if not keep_settings and not is_selective:
                # 10. 清空学校数据
                self.stdout.write(f'  尝试清空 School 数据...')
                try:
                    count = School.objects.all().delete()[0]
                    self.stdout.write(f'  已成功清空 School 数据: {count} 条记录已删除')
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'删除School数据失败: {str(e)}'))
                
                # 11. 清空教师数据
                # self.stdout.write(f'  尝试清空 Teacher 数据...')
                # try:
                #     count = Teacher.objects.all().delete()[0]
                #     self.stdout.write(f'  已成功清空 Teacher 数据: {count} 条记录已删除')
                # except Exception as e:
                #     self.stdout.write(self.style.ERROR(f'删除Teacher数据失败: {str(e)}'))
                
                # 12. 清空学期数据
                self.stdout.write(f'  尝试清空 Semester 数据...')
                try:
                    count = Semester.objects.all().delete()[0]
                    self.stdout.write(f'  已成功清空 Semester 数据: {count} 条记录已删除')
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'SQL删除Semester数据失败: {str(e)}'))
                
                # 13. 清空家庭数据
                self.stdout.write(f'  尝试清空 Family 数据...')
                try:
                    count = Family.objects.all().delete()[0]
                    self.stdout.write(f'  已成功清空 Family 数据: {count} 条记录已删除')
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'SQL删除Family数据失败: {str(e)}'))
                
                # 14. 清空区域数据
                self.stdout.write(f'  尝试清空 Region 数据...')
                try:
                    count = Region.objects.all().delete()[0]
                    self.stdout.write(f'  已成功清空 Region 数据: {count} 条记录已删除')
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'SQL删除Region数据失败: {str(e)}'))
                
                # 15. 清空学科数据
                self.stdout.write(f'  尝试清空 Subject 数据...')
                try:
                    count = Subject.objects.all().delete()[0]
                    self.stdout.write(f'  已成功清空 Subject 数据: {count} 条记录已删除')
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'SQL删除Subject数据失败: {str(e)}'))
            else:
                if is_selective:
                    self.stdout.write(self.style.SUCCESS('  已成功清空指定的表，保留其他数据'))
                else:
                    self.stdout.write(self.style.SUCCESS('  已成功保留学期、区域、学校、教师和学科等基础设置数据'))
            
            # 添加数据库连接检查
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_database();")
                db_name = cursor.fetchone()[0]
                self.stdout.write(f'当前连接的数据库: {db_name}')
            
            self.stdout.write(self.style.SUCCESS('数据清空完成!'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'数据清空过程中出错: {str(e)}')) 