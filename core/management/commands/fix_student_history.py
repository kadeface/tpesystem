"""
修复学生历史记录数据的管理命令。

此命令检测并修复学生历史记录中的不一致，确保学生在不同学期的年级和班级记录正确反映升学情况。
"""

from django.core.management.base import BaseCommand
from django.db import connection, transaction
from core.models import Student, Grade, Class, Semester, StudentHistory, Exam, Score
from django.db.models import Count, Min, Max
from django.utils import timezone

class Command(BaseCommand):
    """
    修复学生历史记录的Django管理命令。
    
    检测并修复学生历史记录中的不一致情况。
    
    Args:
        BaseCommand: Django管理命令基类
    
    Returns:
        无
    """
    
    help = '检测并修复学生历史记录中的不一致'
    
    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='试运行模式，不实际修改数据')
        parser.add_argument('--student-id', help='指定要修复的学生ID')
        parser.add_argument('--reset', action='store_true', help='重置所有历史记录并根据考试成绩重建')
    
    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        student_id = options.get('student_id')
        reset = options.get('reset', False)
        
        if reset:
            self.reset_all_history(dry_run)
            return
            
        # 找出问题记录
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    student_id, 
                    COUNT(DISTINCT semester_id) as semester_count, 
                    COUNT(DISTINCT grade_id) as grade_count, 
                    COUNT(DISTINCT class_field_id) as class_count
                FROM 
                    core_studenthistory
                GROUP BY 
                    student_id
                HAVING 
                    COUNT(DISTINCT semester_id) > 1 
                    AND (COUNT(DISTINCT grade_id) = 1 OR COUNT(DISTINCT class_field_id) = 1)
            """)
            
            problem_students = cursor.fetchall()
        
        if student_id:
            self.fix_student(student_id, dry_run)
        else:
            self.stdout.write(f'发现 {len(problem_students)} 个存在历史记录问题的学生')
            
            if problem_students:
                for student_data in problem_students:
                    student_id = student_data[0]
                    semester_count = student_data[1]
                    grade_count = student_data[2]
                    class_count = student_data[3]
                    
                    self.stdout.write(f'学生 {student_id}: {semester_count} 个学期, {grade_count} 个年级, {class_count} 个班级')
                    
                    if not dry_run:
                        self.fix_student(student_id, False)
    
    def fix_student(self, student_id, dry_run=False):
        """修复单个学生的历史记录"""
        try:
            student = Student.objects.get(student_id=student_id)
        except Student.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'找不到学生 {student_id}'))
            return
            
        self.stdout.write(f'正在修复学生 {student.name} ({student_id}) 的历史记录...')
        
        # 获取该学生的考试成绩记录，按学期排序
        scores = Score.objects.filter(
            student=student
        ).select_related('exam', 'exam__semester').order_by('exam__semester__start_date')
        
        semesters = set()
        for score in scores:
            semesters.add(score.exam.semester)
        
        semesters = sorted(list(semesters), key=lambda x: x.start_date)
        
        if len(semesters) <= 1:
            self.stdout.write(self.style.WARNING(f'学生 {student.name} 只有一个学期的成绩记录，无法确定升学轨迹'))
            return
            
        if dry_run:
            self.stdout.write('试运行模式，不修改数据库')
            for i, semester in enumerate(semesters):
                self.stdout.write(f'  学期 {semester.semester_id}: 将设置为年级 {7 + i} 年级')
            return
            
        # 实际修复操作
        with transaction.atomic():
            # 1. 清除该学生的所有历史记录
            StudentHistory.objects.filter(student=student).delete()
            
            # 2. 获取所有可用年级，按级别排序
            available_grades = {}
            for semester in semesters:
                grades = Grade.objects.filter(
                    school=student.current_school,
                    semester=semester
                )
                available_grades[semester.semester_id] = {g.grade_level: g for g in grades}
            
            # 确定起始年级级别
            start_grade_level = 7  # 默认从7级开始
            
            # 如果无法找到初始年级，尝试使用其他可用年级
            if not any(start_grade_level in grades for grades in available_grades.values()):
                # 找出所有可用年级级别
                all_levels = set()
                for grades in available_grades.values():
                    all_levels.update(grades.keys())
                
                if all_levels:
                    start_grade_level = min(int(level) for level in all_levels)
                    self.stdout.write(f'  找不到7年级，使用最低可用年级：{start_grade_level}年级')
            
            # 3. 为每个学期创建新记录
            last_grade = None
            last_class = None
            
            for i, semester in enumerate(semesters):
                # 计算本学期应该使用的年级级别
                target_level = start_grade_level + i
                current_level = str(target_level)
                
                # 尝试找到匹配的年级
                grade = None
                semester_grades = available_grades.get(semester.semester_id, {})
                
                # 先尝试找到精确匹配的年级
                if current_level in semester_grades:
                    grade = semester_grades[current_level]
                else:
                    # 如果找不到精确匹配，尝试使用最接近的可用年级
                    if semester_grades:
                        available_levels = [int(l) for l in semester_grades.keys()]
                        closest_level = min(available_levels, key=lambda x: abs(x - target_level))
                        grade = semester_grades[str(closest_level)]
                        self.stdout.write(f'  找不到{target_level}年级，使用最接近的{closest_level}年级')
                    elif last_grade:
                        # 如果找不到任何年级，使用上一个学期的年级
                        grade = last_grade
                        self.stdout.write(f'  找不到任何年级，复用上一学期的年级：{grade.grade_name}')
                
                if grade:
                    # 找到年级后，寻找班级
                    class_obj = Class.objects.filter(
                        grade=grade,
                        status='ACTIVE'
                    ).first()
                    
                    if not class_obj and last_class:
                        # 如果找不到班级，尝试使用上一个学期的班级所在年级的班级
                        similar_classes = Class.objects.filter(
                            grade=grade,
                        ).first()
                        if similar_classes:
                            class_obj = similar_classes
                            self.stdout.write(f'  找不到活动班级，使用：{class_obj.class_name}')
                    
                    if class_obj:
                        # 保存本次找到的年级和班级，用于下一学期的回退选项
                        last_grade = grade
                        last_class = class_obj
                        
                        # 创建历史记录
                        status = 'COMPLETED' if semester.end_date < timezone.now().date() else 'ACTIVE'
                        
                        StudentHistory.objects.create(
                            student=student,
                            grade=grade,
                            class_field=class_obj,
                            school=student.current_school,
                            semester=semester,
                            start_date=semester.start_date,
                            end_date=semester.end_date if status == 'COMPLETED' else None,
                            status=status
                        )
                        
                        self.stdout.write(f'  为学期 {semester.semester_id} 创建历史记录: {grade.grade_name}/{class_obj.class_name}')
                        
                        # 更新学生当前年级/班级到最后一个学期
                        if i == len(semesters) - 1:
                            student.current_grade = grade
                            student.current_class = class_obj
                            student.save()
                            self.stdout.write(f'  更新学生当前年级/班级为: {grade.grade_name}/{class_obj.class_name}')
                    else:
                        self.stdout.write(self.style.WARNING(f'  无法找到年级 {grade.grade_name} 的班级'))
                else:
                    self.stdout.write(self.style.WARNING(f'  无法为学期 {semester.semester_id} 找到合适的年级'))
    
    def reset_all_history(self, dry_run=False):
        """重置所有学生历史记录并根据考试成绩重新创建"""
        self.stdout.write('准备重置所有学生历史记录...')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('试运行模式，不会修改数据库'))
            count = StudentHistory.objects.count()
            self.stdout.write(f'将删除 {count} 条学生历史记录')
            return
            
        with transaction.atomic():
            # 清除所有历史记录
            count = StudentHistory.objects.all().delete()[0]
            self.stdout.write(f'已删除 {count} 条学生历史记录')
            
            # 重建所有学生的历史记录
            students = Student.objects.filter(status='ACTIVE')
            self.stdout.write(f'开始为 {students.count()} 个学生重建历史记录')
            
            for student in students:
                self.fix_student(student.student_id, False)
                
        self.stdout.write(self.style.SUCCESS('所有学生历史记录已重置并重建')) 