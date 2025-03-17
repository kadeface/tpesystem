"""
删除指定班级记录，暂时禁用外键约束。
   python manage.py delete_classes --semester=2024-2025-1 --grade=10 --dry_run #测试模式（不实际删除）:
   python manage.py delete_classes --semester=2024-2025-1 --class_id=C01_101_251 #删除指定班级:
   python manage.py delete_classes --semester=2024-2025-1 --grade=10 --school=01 #删除指定年级:
此命令用于清理因ID截断导致信息丢失的班级记录，以便重新导入。
"""

from django.core.management.base import BaseCommand
from django.db import connection
from core.models import Class, TeacherHistory, StudentHistory

class Command(BaseCommand):
    help = '删除特定班级记录，暂时禁用外键约束'
    
    def add_arguments(self, parser):
        parser.add_argument('--semester', required=True, help='学期ID，例如 2024-2025-1')
        parser.add_argument('--grade', help='年级，例如 10')
        parser.add_argument('--school', help='学校ID')
        parser.add_argument('--class_id', help='具体的班级ID')
        parser.add_argument('--dry_run', action='store_true', help='只显示将要删除的记录，不实际删除')
        
    def handle(self, *args, **options):
        semester = options['semester']
        grade = options.get('grade')
        school_id = options.get('school')
        class_id = options.get('class_id')
        dry_run = options.get('dry_run', False)
        
        # 构建查询条件
        query = Class.objects.filter(semester__semester_id=semester)
        
        if grade:
            query = query.filter(grade__grade_level=grade)
        
        if school_id:
            query = query.filter(grade__school__school_id=school_id)
            
        if class_id:
            query = query.filter(class_id=class_id)
        
        # 先显示将要删除的记录
        classes = query.all()
        count = classes.count()
        
        self.stdout.write(f"查询到 {count} 个班级记录")
        
        for cls in classes[:10]:  # 仅显示前10个
            self.stdout.write(f"班级ID: {cls.class_id}, 名称: {cls.class_name}, 年级: {cls.grade.grade_name}")
        
        if count > 10:
            self.stdout.write("... 更多记录 ...")
        
        if dry_run:
            self.stdout.write(self.style.WARNING("试运行模式 - 未执行实际删除"))
            return
        
        # 确认是否继续
        confirm = input("是否继续删除这些班级记录? (y/n): ")
        if confirm.lower() != 'y':
            self.stdout.write(self.style.WARNING("操作已取消"))
            return
        
        # 先检查外键引用
        for cls in classes:
            teacher_refs = TeacherHistory.objects.filter(class_field=cls).count()
            student_refs = StudentHistory.objects.filter(class_field=cls).count()
            
            if teacher_refs > 0 or student_refs > 0:
                self.stdout.write(self.style.WARNING(
                    f"班级 {cls.class_id} 有关联记录: {teacher_refs} 条教师历史, {student_refs} 条学生历史"
                ))
        
        # 再次确认删除包括关联记录
        confirm = input("警告: 此操作将删除班级及其关联记录! 是否继续? (yes/no): ")
        if confirm.lower() != 'yes':
            self.stdout.write(self.style.WARNING("操作已取消"))
            return
        
        # 暂时禁用外键约束
        with connection.cursor() as cursor:
            if connection.vendor == 'postgresql':
                cursor.execute('SET CONSTRAINTS ALL DEFERRED;')
            elif connection.vendor == 'mysql':
                cursor.execute('SET FOREIGN_KEY_CHECKS=0;')
            elif connection.vendor == 'sqlite':
                cursor.execute('PRAGMA foreign_keys=OFF;')
        
        try:
            # 删除相关的历史记录
            for cls in classes:
                th_count = TeacherHistory.objects.filter(class_field=cls).delete()[0]
                sh_count = StudentHistory.objects.filter(class_field=cls).delete()[0]
                self.stdout.write(f"删除关联记录: 班级={cls.class_id}, 教师历史={th_count}, 学生历史={sh_count}")
            
            # 删除班级记录
            deleted = query.delete()[0]
            self.stdout.write(self.style.SUCCESS(f"成功删除 {deleted} 个班级记录"))
            
        finally:
            # 恢复外键约束
            with connection.cursor() as cursor:
                if connection.vendor == 'postgresql':
                    cursor.execute('SET CONSTRAINTS ALL IMMEDIATE;')
                elif connection.vendor == 'mysql':
                    cursor.execute('SET FOREIGN_KEY_CHECKS=1;')
                elif connection.vendor == 'sqlite':
                    cursor.execute('PRAGMA foreign_keys=ON;') 