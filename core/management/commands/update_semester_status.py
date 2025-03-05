"""
更新学期状态的管理命令。

此命令根据当前日期自动更新所有学期的状态，确保系统中只有当前学期为"ACTIVE"状态。
同时更新教师-学科-班级关联状态以及考试状态，保持系统一致性。
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import Semester, TeacherSubjectClass, Exam, TeacherSubject
from django.db import connection

class Command(BaseCommand):
    """
    更新学期状态的Django管理命令。
    
    根据当前日期自动更新所有学期的状态。
    
    Args:
        BaseCommand: Django管理命令基类
    
    Returns:
        无
    
    Raises:
        无
    """
    
    help = '根据当前日期自动更新所有学期的状态'
    
    def handle(self, *args, **options):
        """
        命令处理主函数。
        
        根据当前日期对学期状态进行如下更新：
        1. 结束日期早于当前日期的学期状态更新为'COMPLETED'
        2. 当前日期在学期开始和结束日期之间的学期状态更新为'ACTIVE'
        3. 开始日期晚于当前日期的学期状态更新为'UPCOMING'
        
        Args:
            *args: 位置参数
            **options: 关键字参数
            
        Returns:
            无
        """
        today = timezone.now().date()
        
        # 获取所有学期
        semesters = Semester.objects.all()
        
        # 统计状态变更数
        completed_count = 0
        active_count = 0
        upcoming_count = 0
        
        # 教师学科班级关联更新计数
        tsc_updated = 0
        
        # 考试更新计数
        exam_updated = 0
        
        # 教师学科关联更新计数
        teacher_subject_updated = 0
        
        for semester in semesters:
            old_status = semester.status
            
            # 更新状态逻辑
            if semester.end_date < today:
                # 已结束学期
                semester.status = 'COMPLETED'
                if old_status != 'COMPLETED':
                    completed_count += 1
                    
                    # 更新此学期的教师-学科-班级关联状态
                    tsc_count = TeacherSubjectClass.objects.filter(
                        semester=semester, 
                        status='ACTIVE'
                    ).update(status='COMPLETED')
                    tsc_updated += tsc_count
                    
                    # 更新考试状态 - 确保使用正确的状态值
                    exam_count = Exam.objects.filter(
                        semester=semester,
                        status__in=['PLANNED', 'ONGOING', 'ACTIVE', 'DRAFT']
                    ).update(status='COMPLETED')
                    exam_updated += exam_count
                    
                    # 更新教师学科关联
                    teacher_subject_count = TeacherSubject.objects.filter(
                        semester=semester,
                        status='ACTIVE',
                        end_date__isnull=True
                    ).update(status='COMPLETED', end_date=today)
                    teacher_subject_updated += teacher_subject_count
                    
            elif semester.start_date <= today <= semester.end_date:
                # 当前学期
                semester.status = 'ACTIVE'
                if old_status != 'ACTIVE':
                    active_count += 1
                    
                    # 如果学期从UPCOMING变为ACTIVE，激活计划中的关联
                    if old_status == 'UPCOMING':
                        tsc_count = TeacherSubjectClass.objects.filter(
                            semester=semester, 
                            status='PLANNED'
                        ).update(status='ACTIVE')
                        tsc_updated += tsc_count
                        
                        # 同样更新计划中的考试为活动状态
                        exam_count = Exam.objects.filter(
                            semester=semester,
                            status='PLANNED'
                        ).update(status='ACTIVE')
                        exam_updated += exam_count
                    
            else:
                # 未来学期
                semester.status = 'UPCOMING'
                if old_status != 'UPCOMING':
                    upcoming_count += 1
            
            # 保存更新
            if old_status != semester.status:
                semester.save()
        
        # 输出结果
        self.stdout.write(self.style.SUCCESS(f'学期状态更新完成：'))
        self.stdout.write(f'  - 已完成学期: {completed_count}个')
        self.stdout.write(f'  - 当前学期: {active_count}个')
        self.stdout.write(f'  - 即将到来的学期: {upcoming_count}个')
        self.stdout.write(f'  - 更新的教师-学科-班级关联: {tsc_updated}个')
        self.stdout.write(f'  - 更新的考试: {exam_updated}个')
        self.stdout.write(f'  - 更新的教师学科关联: {teacher_subject_updated}个')
        
        # 添加诊断SQL，查看core_exam表的状态分布
        with connection.cursor() as cursor:
            cursor.execute("SELECT status, COUNT(*) FROM core_exam GROUP BY status")
            rows = cursor.fetchall()
            self.stdout.write(f'考试状态分布:')
            for status, count in rows:
                self.stdout.write(f'  - {status}: {count}个')
        
        # 添加专门处理考试状态的代码块
        self.stdout.write("开始针对已完成学期强制更新考试状态...")
        completed_semesters = Semester.objects.filter(status='COMPLETED')
        exam_updated_total = 0
        
        for semester in completed_semesters:
            # 强制更新所有该学期的考试为COMPLETED
            exam_count = Exam.objects.filter(
                semester=semester
            ).update(status='COMPLETED')
            exam_updated_total += exam_count
            
            if exam_count > 0:
                self.stdout.write(f"  - 学期 {semester.semester_id}: 更新了 {exam_count} 个考试状态")
        
        self.stdout.write(self.style.SUCCESS(f"总共更新了 {exam_updated_total} 个考试状态为COMPLETED"))

        # 添加专门处理教师-学科-班级关联状态的代码块
        self.stdout.write("开始针对已完成学期强制更新教师-学科-班级关联状态...")
        tsc_updated_total = 0

        for semester in completed_semesters:
            # 强制更新所有该学期的教师-学科-班级关联为COMPLETED
            tsc_count = TeacherSubjectClass.objects.filter(
                semester=semester
            ).update(status='COMPLETED')
            tsc_updated_total += tsc_count
            
            if tsc_count > 0:
                self.stdout.write(f"  - 学期 {semester.semester_id}: 更新了 {tsc_count} 个教师-学科-班级关联状态")

        self.stdout.write(self.style.SUCCESS(f"总共更新了 {tsc_updated_total} 个教师-学科-班级关联状态为COMPLETED"))

        # 处理教师-学科关联
        self.stdout.write("开始基于日期范围更新教师-学科关联状态...")
        ts_updated_total = 0

        for semester in completed_semesters:
            # 使用学期的日期范围来筛选教师学科关联
            ts_count = TeacherSubject.objects.filter(
                start_date__lte=semester.end_date,  # 关联开始日期早于或等于学期结束日期
                status='ACTIVE',
                end_date__isnull=True  # 尚未设置结束日期的记录
            ).update(status='COMPLETED', end_date=today)
            ts_updated_total += ts_count
            
            if ts_count > 0:
                self.stdout.write(f"  - 基于日期范围 {semester.start_date} 至 {semester.end_date}: 更新了 {ts_count} 个教师-学科关联状态")

        self.stdout.write(self.style.SUCCESS(f"总共更新了 {ts_updated_total} 个教师-学科关联状态为COMPLETED"))

        # 在学期状态更新后添加提醒逻辑
        if completed_count > 0 or active_count > 0:
            # 检查是否学年结束
            current_year_end = False
            for semester in semesters:
                if semester.status == 'ACTIVE' and semester.term == '1':
                    # 新学年第一学期变为活动，表示学年已经转换
                    current_year_end = True
                    break
            
            if current_year_end:
                self.stdout.write(self.style.WARNING('检测到新学年开始，请考虑运行学生升级命令:'))
                self.stdout.write('python manage.py promote_students --from-semester=旧学期ID --to-semester=新学期ID') 