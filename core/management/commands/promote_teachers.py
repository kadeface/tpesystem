"""
教师学期升级命令。

此命令处理教师从一个学期到下一个学期的任课信息变更，保留历史数据。
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from core.models import Teacher, TeacherHistory, TeacherSubjectClass, Semester, Class, Grade

class Command(BaseCommand):
    """
    教师学期升级的Django管理命令。
    
    处理教师从一个学期到下一个学期的任课变更，同时维护历史记录数据。
    
    Args:
        BaseCommand: Django管理命令基类
    
    Returns:
        无
    """
    
    help = '处理教师从一个学期到下一个学期的任课变更'
    
    def add_arguments(self, parser):
        """添加命令参数"""
        parser.add_argument('--from-semester', type=str, required=True, help='源学期ID')
        parser.add_argument('--to-semester', type=str, required=True, help='目标学期ID')
        parser.add_argument('--dry-run', action='store_true', help='试运行模式，不修改数据库')
        parser.add_argument('--auto-match', action='store_true', help='自动匹配班级')
        parser.add_argument('--keep-structure', action='store_true', help='保持原班级结构')
    
    def handle(self, *args, **options):
        """主命令处理函数"""
        from_semester_id = options['from_semester']
        to_semester_id = options['to_semester']
        dry_run = options.get('dry_run', False)
        auto_match = options.get('auto_match', False)
        keep_structure = options.get('keep_structure', False)
        
        try:
            from_semester = Semester.objects.get(semester_id=from_semester_id)
            to_semester = Semester.objects.get(semester_id=to_semester_id)
        except Semester.DoesNotExist:
            self.stdout.write(self.style.ERROR('找不到指定的学期，请检查学期ID'))
            return
        
        # 验证学期顺序
        if from_semester.start_date >= to_semester.start_date:
            self.stdout.write(self.style.ERROR('源学期必须早于目标学期'))
            return
        
        # 获取上一学期所有教师任课记录
        tsc_records = TeacherSubjectClass.objects.filter(
            semester=from_semester
        ).select_related(
            'teacher', 'subject', 'class_obj', 'class_obj__grade', 'school'
        )
        
        if not tsc_records.exists():
            self.stdout.write(self.style.WARNING(f'未找到学期 {from_semester_id} 的任课记录'))
            return
        
        self.stdout.write(f'找到 {tsc_records.count()} 条上学期任课记录')
        
        # 开始升级处理
        if dry_run:
            self.stdout.write(self.style.WARNING('试运行模式，不会修改数据库'))
            return
        
        with transaction.atomic():
            promote_count = 0
            skip_count = 0
            
            for tsc in tsc_records:
                try:
                    # 查找目标学期对应班级
                    target_class = None
                    
                    if keep_structure:
                        # 尝试找到相同班级名称但属于新学期的班级
                        target_classes = Class.objects.filter(
                            class_name=tsc.class_obj.class_name,
                            grade__school=tsc.class_obj.grade.school,
                            grade__semester=to_semester
                        )
                        if target_classes.exists():
                            target_class = target_classes.first()
                    
                    if not target_class and auto_match:
                        # 根据年级级别自动匹配下一学期班级
                        current_grade_level = tsc.class_obj.grade.grade_level
                        try:
                            # 假设下一学期年级级别+1
                            next_grade_level = str(int(current_grade_level) + 1)
                            target_grades = Grade.objects.filter(
                                school=tsc.class_obj.grade.school,
                                grade_level=next_grade_level,
                                semester=to_semester
                            )
                            
                            if target_grades.exists():
                                target_grade = target_grades.first()
                                # 找到对应班号的班级
                                class_number = tsc.class_obj.class_name.split('(')[0].strip()
                                target_classes = Class.objects.filter(
                                    grade=target_grade,
                                    class_name__contains=class_number
                                )
                                if target_classes.exists():
                                    target_class = target_classes.first()
                        except (ValueError, IndexError):
                            pass
                    
                    if not target_class:
                        self.stdout.write(self.style.WARNING(f'无法为 {tsc.teacher.name} 的 {tsc.subject.subject_name} 课找到目标班级'))
                        skip_count += 1
                        continue
                    
                    # 创建历史记录
                    TeacherHistory.objects.create(
                        teacher=tsc.teacher,
                        school=tsc.school or tsc.teacher.current_school,
                        semester=from_semester,
                        subject=tsc.subject,
                        grade=tsc.class_obj.grade,
                        class_field=tsc.class_obj,
                        is_class_teacher=tsc.teacher.is_class_teacher,
                        admin_position=tsc.teacher.admin_position,
                        start_date=from_semester.start_date,
                        end_date=from_semester.end_date,
                        status='COMPLETED'
                    )
                    
                    # 创建新学期任课记录
                    TeacherSubjectClass.objects.create(
                        teacher=tsc.teacher,
                        subject=tsc.subject,
                        class_obj=target_class,
                        school=tsc.school or tsc.teacher.current_school,
                        semester=to_semester,
                        is_main=tsc.is_main,
                        status='ACTIVE'
                    )
                    
                    promote_count += 1
                    self.stdout.write(f'成功升级 {tsc.teacher.name} 的 {tsc.subject.subject_name} 课从 {tsc.class_obj.class_name} 到 {target_class.class_name}')
                    
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'处理教师 {tsc.teacher.name} 时出错: {str(e)}'))
                    skip_count += 1
            
            self.stdout.write(self.style.SUCCESS(f'教师升级完成! 成功: {promote_count}, 跳过: {skip_count}')) 