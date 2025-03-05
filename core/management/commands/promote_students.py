"""
学生升级管理命令。

此命令处理学年结束时的学生升级，将学生移至下一年级和班级，同时保存历史记录。
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import Student, Grade, Class, Semester, StudentHistory
from django.db import transaction

class Command(BaseCommand):
    """
    学生升级的Django管理命令。
    
    处理学生从一个年级到下一个年级的升级，同时保存历史记录。
    
    Args:
        BaseCommand: Django管理命令基类
    
    Returns:
        无
    """
    
    help = '处理学年结束时的学生升级，将学生移至下一年级和班级'
    
    def add_arguments(self, parser):
        parser.add_argument('--from-semester', required=True, help='起始学期ID')
        parser.add_argument('--to-semester', required=True, help='目标学期ID')
        parser.add_argument('--grade', help='指定要升级的年级ID（可选）')
        parser.add_argument('--dry-run', action='store_true', help='试运行模式，不实际修改数据')
    
    def handle(self, *args, **options):
        # 实现学生升级逻辑
        from_semester_id = options['from_semester']
        to_semester_id = options['to_semester']
        grade_id = options.get('grade')
        dry_run = options.get('dry_run', False)
        
        try:
            from_semester = Semester.objects.get(semester_id=from_semester_id)
            to_semester = Semester.objects.get(semester_id=to_semester_id)
        except Semester.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'指定的学期不存在'))
            return
            
        # 构建学生查询集
        students = Student.objects.filter(status='ACTIVE')
        if grade_id:
            students = students.filter(current_grade_id=grade_id)
            
        count = students.count()
        self.stdout.write(f'找到 {count} 个需要升级的学生记录')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('试运行模式，不会修改数据库'))
            return
            
        # 开始升级处理
        with transaction.atomic():
            for student in students:
                # 1. 保存学生当前班级信息到历史记录，但要明确指明这是from_semester的记录
                StudentHistory.objects.create(
                    student=student,
                    grade_id=student.current_grade_id,
                    class_field_id=student.current_class_id,
                    school_id=student.current_school_id,
                    semester=from_semester,
                    start_date=from_semester.start_date,
                    end_date=from_semester.end_date,
                    status='COMPLETED'
                )
                
                # 2. 查找下一个年级
                current_grade_level = int(student.current_grade.grade_level)
                next_grade_level = current_grade_level + 1
                
                # 查找目标学期下对应学校的下一年级
                try:
                    next_grade = Grade.objects.get(
                        school=student.current_school,
                        grade_level=str(next_grade_level),
                        semester=to_semester
                    )
                    
                    # 查找该年级下的班级（简单策略：找第一个可用班级）
                    next_class = Class.objects.filter(
                        grade=next_grade,
                        status='ACTIVE'
                    ).first()
                    
                    if next_class:
                        # 3. 更新学生的年级和班级
                        old_grade = student.current_grade
                        old_class = student.current_class
                        
                        student.current_grade = next_grade
                        student.current_class = next_class
                        student.save()
                        
                        # 4. 创建新学期的历史记录
                        StudentHistory.objects.create(
                            student=student,
                            grade=next_grade,
                            class_field=next_class,
                            school=student.current_school,
                            semester=to_semester,
                            start_date=to_semester.start_date,
                            end_date=None,  # 尚未结束
                            status='ACTIVE'
                        )
                        
                        self.stdout.write(
                            f'升级学生: {student.name} 从 {old_grade.grade_name}/{old_class.class_name} '
                            f'到 {next_grade.grade_name}/{next_class.class_name}'
                        )
                    else:
                        self.stdout.write(self.style.WARNING(
                            f'无法找到学生 {student.name} 的目标班级 (年级级别 {next_grade_level})'
                        ))
                except Grade.DoesNotExist:
                    self.stdout.write(self.style.WARNING(
                        f'无法找到学生 {student.name} 的目标年级 (年级级别 {next_grade_level})'
                    ))
        
        self.stdout.write(self.style.SUCCESS(f'已完成 {count} 个学生的升级')) 