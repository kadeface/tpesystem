"""
修复教师历史记录数据的管理命令。

此命令检测并修复教师历史记录中的不一致，确保教师在不同学期的任教记录正确保存。
"""

from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.utils import timezone
from core.models import Teacher, TeacherHistory, TeacherSubjectClass, Semester, Subject

class Command(BaseCommand):
    """
    修复教师历史记录的Django管理命令。
    
    根据教师任课记录重建教师历史数据，支持数据修复和重置。
    
    Args:
        BaseCommand: Django管理命令基类
    
    Returns:
        无
    """
    
    help = '修复教师历史记录数据'
    
    def add_arguments(self, parser):
        """添加命令参数"""
        parser.add_argument('--teacher-id', type=str, help='修复特定教师的历史记录')
        parser.add_argument('--reset', action='store_true', help='重置并重建所有教师历史记录')
        parser.add_argument('--dry-run', action='store_true', help='试运行模式，不修改数据库')
    
    def handle(self, *args, **options):
        """主命令处理函数"""
        teacher_id = options.get('teacher_id')
        reset = options.get('reset', False)
        dry_run = options.get('dry_run', False)
        
        if reset:
            self.reset_all_history(dry_run)
        elif teacher_id:
            self.fix_teacher(teacher_id, dry_run)
        else:
            teachers = Teacher.objects.filter(status='ACTIVE')
            self.stdout.write(f'准备检查 {teachers.count()} 名教师的历史记录...')
            
            for teacher in teachers:
                self.fix_teacher(teacher.teacher_id, dry_run)
    
    def fix_teacher(self, teacher_id, dry_run=False):
        """修复单个教师的历史记录"""
        try:
            teacher = Teacher.objects.get(teacher_id=teacher_id)
        except Teacher.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'找不到教师 {teacher_id}'))
            return
            
        self.stdout.write(f'正在修复教师 {teacher.name} ({teacher_id}) 的历史记录...')
        
        # 获取该教师的所有任课记录，按学期排序
        tsc_records = TeacherSubjectClass.objects.filter(
            teacher=teacher
        ).select_related('semester', 'subject', 'class_obj', 'class_obj__grade', 'school').order_by('semester__start_date')
        
        if not tsc_records.exists():
            self.stdout.write(self.style.WARNING(f'教师 {teacher.name} 没有任课记录，无法创建历史'))
            return
        
        # 按学期和班级分组记录
        semesters = set()
        for tsc in tsc_records:
            semesters.add(tsc.semester)
        
        semesters = sorted(list(semesters), key=lambda x: x.start_date)
        
        if dry_run:
            self.stdout.write(f'试运行模式: 教师 {teacher.name} 有 {len(semesters)} 个学期的任课记录')
            return
        
        with transaction.atomic():
            # 1. 清除该教师的所有历史记录
            TeacherHistory.objects.filter(teacher=teacher).delete()
            
            # 2. 为每个教师-学科-班级任课记录创建历史记录
            history_count = 0
            for tsc in tsc_records:
                status = 'COMPLETED' if tsc.semester.end_date and tsc.semester.end_date < timezone.now().date() else 'ACTIVE'
                
                # 创建历史记录
                TeacherHistory.objects.create(
                    teacher=teacher,
                    school=tsc.school or teacher.current_school,
                    semester=tsc.semester,
                    subject=tsc.subject,
                    grade=tsc.class_obj.grade if tsc.class_obj else None,
                    class_field=tsc.class_obj,
                    is_class_teacher=teacher.is_class_teacher,
                    admin_position=teacher.admin_position,
                    start_date=tsc.semester.start_date,
                    end_date=tsc.semester.end_date if status == 'COMPLETED' else None,
                    status=status
                )
                history_count += 1
            
            self.stdout.write(self.style.SUCCESS(f'为教师 {teacher.name} 创建了 {history_count} 条历史记录'))
    
    def reset_all_history(self, dry_run=False):
        """重置所有教师历史记录并根据任课记录重新创建"""
        self.stdout.write('准备重置所有教师历史记录...')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('试运行模式，不会修改数据库'))
            count = TeacherHistory.objects.count()
            self.stdout.write(f'将删除 {count} 条教师历史记录')
            return
            
        with transaction.atomic():
            # 清除所有历史记录
            count = TeacherHistory.objects.all().delete()[0]
            self.stdout.write(f'已删除 {count} 条教师历史记录')
            
            # 重建所有教师的历史记录
            teachers = Teacher.objects.filter(status='ACTIVE')
            self.stdout.write(f'开始为 {teachers.count()} 名教师重建历史记录')
            
            for teacher in teachers:
                self.fix_teacher(teacher.teacher_id, False)
                
        self.stdout.write(self.style.SUCCESS('所有教师历史记录已重置并重建')) 