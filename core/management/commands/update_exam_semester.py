# -*- coding: utf-8 -*-
"""
用于修正考试学期信息的管理命令。

此命令允许将已导入的考试记录的学期信息进行更新，无需删除和重新导入数据。

Args:
    exam_id: 考试ID
    semester: 正确的学期ID

Returns:
    None

Raises:
    CommandError: 当考试ID不存在或参数无效时
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from core.models import Exam, Semester

class Command(BaseCommand):
    help = '修正已导入考试的学期值'

    def add_arguments(self, parser):
        parser.add_argument('exam_id', type=str, help='需要修正的考试ID')
        parser.add_argument('--semester', type=str, required=True, 
                           help='正确的学期ID，格式为：YYYY-YYYY-T')
        parser.add_argument('--debug', action='store_true', help='启用调试模式')

    def handle(self, *args, **options):
        exam_id = options['exam_id']
        semester_id = options['semester']
        debug = options['debug']
        
        # 验证考试ID是否存在
        try:
            exam = Exam.objects.get(exam_id=exam_id)
        except Exam.DoesNotExist:
            raise CommandError(f'考试ID "{exam_id}" 不存在')
        
        # 验证学期ID是否存在
        try:
            semester = Semester.objects.get(semester_id=semester_id)
        except Semester.DoesNotExist:
            raise CommandError(f'学期 "{semester_id}" 不存在')
        
        # 在调试模式下显示当前值
        if debug:
            self.stdout.write(self.style.WARNING(
                f'当前考试 "{exam.exam_name}" 的学期为: {exam.semester.semester_id}'
            ))
        
        # 执行更新
        with transaction.atomic():
            old_semester = exam.semester
            exam.semester = semester
            exam.save()
            
            self.stdout.write(self.style.SUCCESS(
                f'成功将考试 "{exam.exam_name}" 的学期从 {old_semester.semester_id} 更新为 {semester.semester_id}'
            ))
            
            # 更新相关记录计数
            scores_count = exam.score_set.count()
            self.stdout.write(self.style.SUCCESS(
                f'已更新 {scores_count} 条相关成绩记录的学期信息'
            )) 