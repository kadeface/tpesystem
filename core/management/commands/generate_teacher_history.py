"""
根据已有的教师学科班级关联生成教师历史记录的管理命令。

此命令基于TeacherSubjectClass表中的数据，为指定学期的每条记录生成对应的TeacherHistory记录，
以便跟踪教师的教学历史。
"""

import logging
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from core.models import TeacherSubjectClass, TeacherHistory, Semester

# 配置日志
logger = logging.getLogger(__name__)

class Command(BaseCommand):
    """
    根据已有的教师学科班级关联生成教师历史记录的Django管理命令。
    
    根据TeacherSubjectClass表中的数据，为指定学期生成TeacherHistory记录。
    
    Args:
        BaseCommand: Django管理命令基类
    
    Returns:
        无
    
    Raises:
        CommandError: 当处理过程出错时抛出
    """
    
    help = '根据已有的教师学科班级关联生成教师历史记录'
    
    def add_arguments(self, parser):
        """
        添加命令行参数配置。
        
        Args:
            parser: 参数解析器对象
            
        Returns:
            无
        """
        parser.add_argument('--semester-id', type=str, help='学期ID，例如：2023-2024-1', required=True)
        parser.add_argument('--debug', action='store_true', help='启用调试模式')
        parser.add_argument('--batch-size', type=int, default=100, help='批量处理大小')
        parser.add_argument('--dry-run', action='store_true', help='试运行模式，不实际写入数据库')
    
    def handle(self, *args, **options):
        """
        命令处理主函数。
        
        Args:
            *args: 位置参数
            **options: 关键字参数，包含命令行选项
            
        Returns:
            无
            
        Raises:
            CommandError: 当处理过程出错时抛出
        """
        semester_id = options['semester_id']
        debug = options['debug']
        batch_size = options['batch_size']
        dry_run = options['dry_run']
        
        # 配置日志级别
        if debug:
            logger.setLevel(logging.DEBUG)
        
        try:
            # 显示导入开始信息
            self.stdout.write("="*80)
            self.stdout.write(self.style.SUCCESS("开始生成教师历史记录"))
            self.stdout.write(f"使用学期ID: {semester_id}")
            if dry_run:
                self.stdout.write(self.style.WARNING("试运行模式：不会实际写入数据库"))
            self.stdout.write("="*80)
            
            # 获取学期对象
            try:
                semester = Semester.objects.get(semester_id=semester_id)
            except Semester.DoesNotExist:
                raise CommandError(f"学期不存在: {semester_id}")
            
            # 查询指定学期的所有教师学科班级关联
            tsc_records = TeacherSubjectClass.objects.filter(semester=semester)
            total_records = tsc_records.count()
            
            self.stdout.write(f"找到 {total_records} 条教师学科班级关联记录")
            
            if total_records == 0:
                self.stdout.write(self.style.WARNING(f"没有找到学期 {semester_id} 的关联记录"))
                return
            
            created_count = 0
            updated_count = 0
            error_count = 0
            
            # 按批次处理数据
            batches = (total_records + batch_size - 1) // batch_size
            
            for batch_idx in range(batches):
                start_idx = batch_idx * batch_size
                end_idx = min((batch_idx + 1) * batch_size, total_records)
                
                self.stdout.write(f"处理批次 {batch_idx+1}/{batches} (记录 {start_idx+1}-{end_idx})")
                
                batch_created = 0
                batch_updated = 0
                batch_error = 0
                
                # 获取当前批次的记录
                batch_records = tsc_records[start_idx:end_idx]
                
                # 为每个批次创建独立的事务
                with transaction.atomic():
                    sid = transaction.savepoint()
                    
                    try:
                        for tsc in batch_records:
                            # 为每条记录创建独立的保存点
                            record_sid = transaction.savepoint()
                            
                            try:
                                # 检查是否已存在相同记录
                                exists = TeacherHistory.objects.filter(
                                    teacher=tsc.teacher,
                                    school=tsc.school,
                                    semester=tsc.semester,
                                    subject=tsc.subject,
                                    class_field=tsc.class_obj
                                ).exists()
                                
                                if exists:
                                    # 更新现有记录
                                    history, created = TeacherHistory.objects.update_or_create(
                                        teacher=tsc.teacher,
                                        school=tsc.school,
                                        semester=tsc.semester,
                                        subject=tsc.subject,
                                        class_field=tsc.class_obj,
                                        defaults={
                                            'grade': tsc.class_obj.grade,
                                            'is_class_teacher': tsc.teacher.is_class_teacher,
                                            'admin_position': tsc.teacher.admin_position,
                                            'start_date': tsc.semester.start_date,
                                            'end_date': tsc.semester.end_date,
                                            'status': 'COMPLETED'
                                        }
                                    )
                                    
                                    if created:
                                        batch_created += 1
                                    else:
                                        batch_updated += 1
                                else:
                                    # 创建新记录
                                    TeacherHistory.objects.create(
                                        teacher=tsc.teacher,
                                        school=tsc.school,
                                        semester=tsc.semester,
                                        subject=tsc.subject,
                                        grade=tsc.class_obj.grade,
                                        class_field=tsc.class_obj,
                                        is_class_teacher=tsc.teacher.is_class_teacher,
                                        admin_position=tsc.teacher.admin_position,
                                        start_date=tsc.semester.start_date,
                                        end_date=tsc.semester.end_date,
                                        status='COMPLETED'
                                    )
                                    batch_created += 1
                                
                            except Exception as e:
                                # 如果处理记录时出错，回滚到该记录的保存点，但继续处理其他记录
                                transaction.savepoint_rollback(record_sid)
                                batch_error += 1
                                self.stdout.write(self.style.ERROR(f"处理关联记录时出错: {str(e)}"))
                        
                        if dry_run:
                            # 试运行模式下回滚整个批次
                            transaction.savepoint_rollback(sid)
                            self.stdout.write(self.style.WARNING(f"批次 {batch_idx+1} 试运行完成，已回滚更改"))
                    
                    except Exception as e:
                        # 如果批次处理过程中出现未捕获的异常，回滚整个批次
                        transaction.savepoint_rollback(sid)
                        self.stdout.write(self.style.ERROR(f"处理批次 {batch_idx+1} 时发生严重错误: {str(e)}"))
                        batch_error = end_idx - start_idx  # 将整个批次标记为错误
                
                created_count += batch_created
                updated_count += batch_updated
                error_count += batch_error
                
                self.stdout.write(f"批次 {batch_idx+1} 处理完成: 新建 {batch_created}, 更新 {batch_updated}, 错误 {batch_error}")
            
            # 输出生成结果摘要
            self.stdout.write("="*80)
            status_msg = "历史记录生成试运行完成!" if dry_run else "历史记录生成完成!"
            self.stdout.write(self.style.SUCCESS(status_msg))
            self.stdout.write(f"新建历史记录: {created_count}")
            self.stdout.write(f"更新历史记录: {updated_count}")
            self.stdout.write(f"错误记录: {error_count}")
            self.stdout.write("="*80)
        
        except Exception as e:
            raise CommandError(f'生成过程出错: {str(e)}') 