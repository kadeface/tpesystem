"""
导入教师历史数据的管理命令。

此命令从Excel文件中读取教师-学科-班级关联数据，并将其导入到系统的TeacherHistory表。
记录教师在特定学期内的教学历史，包括所教学科、班级等信息。

python manage.py import_teacher_history .\7-1_Teacher_subject.xlsx --semester-id 2022-2023-1 --debug --auto-create-classes
"""

import pandas as pd
from datetime import datetime, date
import os
import logging
import re
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from core.models import Teacher, Subject, Class, School, Semester, TeacherHistory, Grade, StudentHistory
import json

# 配置日志
logger = logging.getLogger(__name__)

class Command(BaseCommand):
    """
    导入教师历史数据的Django管理命令。
    
    从Excel文件导入教师历史数据，记录教师在特定学期的教学情况。
    支持"宽表"格式，即一行数据包含一个班级的多个学科教师。
    
    Args:
        BaseCommand: Django管理命令基类
    
    Returns:
        无
    
    Raises:
        CommandError: 当文件不存在或格式不正确时抛出
    """
    
    help = '从Excel文件导入教师历史数据'
    
    def add_arguments(self, parser):
        """
        添加命令行参数配置。
        
        Args:
            parser: 参数解析器对象
            
        Returns:
            无
        """
        parser.add_argument('file_path', type=str, help='历史数据Excel文件路径')
        parser.add_argument('--sheet', type=str, help='Excel工作表名称', default='Sheet1')
        parser.add_argument('--debug', action='store_true', help='启用调试模式')
        parser.add_argument('--update', action='store_true', help='更新现有记录')
        parser.add_argument('--batch-size', type=int, default=100, help='批量处理大小')
        parser.add_argument('--skip-validation', action='store_true', help='跳过数据验证')
        parser.add_argument('--dry-run', action='store_true', help='试运行模式，不实际写入数据库')
        parser.add_argument('--semester-id', type=str, help='学期ID，例如：2023-2024-1', required=True)
        parser.add_argument('--auto-create-classes', action='store_true', 
                            help='自动创建不存在的班级')
        
    def validate_data(self, df):
        """
        验证导入数据的有效性。
        
        Args:
            df: DataFrame对象，包含要验证的数据
            
        Returns:
            tuple: (是否有效, 学科列列表)
            
        Raises:
            CommandError: 当数据无效时抛出
        """
        # 打印所有列名，帮助调试
        self.stdout.write("Excel文件中的列名:")
        for col_idx, col_name in enumerate(df.columns):
            self.stdout.write(f"  {col_idx+1}. '{col_name}'")
        
        # 列名映射 - 支持多种可能的列名
        column_mappings = {
            '学校代码': ['学校代码', '学校编号', '校码'],
            '年级': ['年级', '级别', 'Grade'],
            '班别': ['班别', '班级', '班号', '班组', 'Class']
        }
        
        # 初始化列名映射结果
        actual_column_names = {}
        missing_columns = []
        
        # 检查每个所需列，寻找匹配
        for required_col, possible_names in column_mappings.items():
            found = False
            for name in possible_names:
                if name in df.columns:
                    actual_column_names[required_col] = name
                    found = True
                    break
            
            if not found:
                missing_columns.append(required_col)
        
        # 如果有缺失列，抛出错误
        if missing_columns:
            error_msg = f"缺少必要列: {', '.join(missing_columns)}\n可能的列名: {column_mappings}"
            raise CommandError(error_msg)
        
        # 确定学科列 - 排除已识别的列和学校名称列
        identified_columns = list(actual_column_names.values()) + ['学校名称']
        subject_columns = [col for col in df.columns if col not in identified_columns]
        
        if not subject_columns:
            raise CommandError('未找到学科教师列')
        
        # 将实际列名保存到类属性中，供process_row使用
        self.column_map = actual_column_names
        
        return True, subject_columns
    
    def get_subject_id_map(self):
        """
        获取学科名称到学科ID的映射。
        
        Returns:
            dict: 学科名称到学科ID的映射
        """
        # 先打印所有学科供参考
        self.stdout.write("数据库中的所有学科:")
        subjects = Subject.objects.all()
        subject_ids = []
        for subject in subjects:
            self.stdout.write(f"  {subject.subject_name} (ID: {subject.subject_id})")
            subject_ids.append(subject.subject_id)
        
        # 根据实际数据库中的学科ID创建映射
        subject_map = {
            '语文': 'CHN',
            '数学': 'MATH',
            '英语': 'ENG',
            '物理': 'PHY',
            '化学': 'CHEM' if 'CHEM' in subject_ids else None,
            '生物': 'BIO' if 'BIO' in subject_ids else None,
            '政治': 'MOR',  # 政治映射到道德与法治
            '道德与法治': 'MOR',
            '历史': 'HIS',
            '地理': 'GEO' if 'GEO' in subject_ids else None
        }
        
        # 移除映射到不存在学科ID的项
        subject_map = {k: v for k, v in subject_map.items() if v is not None}
        
        # 实际获取数据库中的学科
        self.subject_name_map = {}  # 用于存储ID到名称的映射，便于反查
        
        for subject in subjects:
            # 存储ID到名称的映射
            self.subject_name_map[subject.subject_id] = subject.subject_name
            
            # 生成多种可能的键名以提高匹配率
            key = subject.subject_name
            subject_map[key] = subject.subject_id  # 完整名称
            
            # 特殊处理科任列名
            key_with_suffix = f"{key}科任"
            subject_map[key_with_suffix] = subject.subject_id
        
        return subject_map
    
    def process_row(self, row, subject_columns, subject_map, semester, debug=False, update_existing=False):
        """
        处理单行数据，为每个学科教师创建历史记录。
        
        Args:
            row: Series对象，包含一行数据
            subject_columns: 学科教师列名列表
            subject_map: 学科名称到学科ID的映射
            semester: 学期对象
            debug: 是否启用调试模式
            update_existing: 是否更新现有记录
            
        Returns:
            tuple: (创建数, 更新数, 错误数)
        """
        created_count = 0
        updated_count = 0
        error_count = 0
        
        try:
            # 使用validate_data中识别的列名获取基本数据
            school_id = str(row[self.column_map['学校代码']]).strip()
            grade_level = str(row[self.column_map['年级']]).strip()
            class_name = str(row[self.column_map['班别']]).strip()
            
            # 输出调试信息
            if debug:
                self.stdout.write(f"处理行: 学校={school_id}, 年级={grade_level}, 班级={class_name}")
            
            # 查找学校
            try:
                school = School.objects.get(school_id=school_id)
            except School.DoesNotExist:
                if debug:
                    self.stdout.write(self.style.ERROR(f"学校不存在: {school_id}"))
                return 0, 0, 1
            
            # 生成与导入分数时相同格式的班级ID和年级ID
            semester_id = semester.semester_id
            semester_short = semester_id.replace("-", "")[-3:]  # 例如 "2022-2023-1" 变为 "231"
            
            # 按照import_scores.py的格式构造ID
            grade_id = f"G{school_id[:3]}_{grade_level}_{semester_short}"
            class_id = f"C{school_id[:2]}_{grade_level}{class_name}_{semester_short}"
            
            # 还保留旧格式ID以增加匹配可能性
            old_class_id = f"{school_id}_{grade_level}_{class_name}"
            
            # 查找班级 - 多种匹配方式
            class_obj = None
            grade = None
            
            # 1. 先尝试使用新格式ID查找
            try:
                class_obj = Class.objects.get(class_id=class_id)
                grade = class_obj.grade
                if debug:
                    self.stdout.write(f"通过新格式班级ID找到班级: {class_id}")
            except Class.DoesNotExist:
                # 2. 尝试使用旧格式ID查找
                try:
                    class_obj = Class.objects.get(class_id=old_class_id)
                    grade = class_obj.grade
                    if debug:
                        self.stdout.write(f"通过旧格式班级ID找到班级: {old_class_id}")
                except Class.DoesNotExist:
                    # 3. 尝试从学校和班级名称查找
                    class_obj = Class.objects.filter(
                        grade__school__school_id=school_id,
                        class_name=class_name
                    ).first()
                    
                    if class_obj:
                        grade = class_obj.grade
                        if debug:
                            self.stdout.write(f"通过学校和班级名称找到班级: {class_obj.class_id}")
                    else:
                        # 4. 通过学生历史记录查找班级
                        student_history = StudentHistory.objects.filter(
                            school__school_id=school_id,
                            semester=semester,
                            grade__grade_name=grade_level
                        ).first()
                        
                        if student_history and student_history.class_field:
                            class_obj = student_history.class_field
                            grade = student_history.grade
                            if debug:
                                self.stdout.write(f"通过学生历史记录找到班级: {class_obj.class_id}")
                        else:
                            # 5. 尝试查找年级以便创建班级
                            try:
                                # 先用新格式ID查找年级
                                grade_obj = Grade.objects.get(grade_id=grade_id)
                            except Grade.DoesNotExist:
                                # 再尝试通过学校和年级名称查找
                                grade_obj = Grade.objects.filter(
                                    school__school_id=school_id,
                                    grade_name=grade_level
                                ).first()
                            
                            if grade_obj:
                                if debug:
                                    self.stdout.write(f"找到年级但未找到班级: {grade_level}")
                                if self.options.get('auto_create_classes'):
                                    # 创建新班级，使用与导入分数相同的ID格式
                                    class_obj = Class.objects.create(
                                        class_id=class_id,
                                        class_name=class_name,
                                        grade=grade_obj,
                                        status='ACTIVE'
                                    )
                                    grade = grade_obj
                                    if debug:
                                        self.stdout.write(self.style.SUCCESS(f"自动创建班级: {class_id}"))
                                else:
                                    if debug:
                                        self.stdout.write(self.style.ERROR(f"找不到班级且未启用自动创建: {class_name}"))
                                    return 0, 0, 1
                            else:
                                if debug:
                                    self.stdout.write(self.style.ERROR(f"找不到年级: {grade_level} (学校: {school_id})"))
                                return 0, 0, 1

            if not class_obj:
                if debug:
                    self.stdout.write(self.style.ERROR(f"无法找到班级: {class_name} (年级: {grade_level}, 学校: {school_id})"))
                return 0, 0, 1
            
            # 处理每个学科教师
            for subject_col in subject_columns:
                if pd.isna(row[subject_col]):
                    continue
                
                teacher_name = str(row[subject_col]).strip()
                if not teacher_name:
                    continue
                
                if debug:
                    self.stdout.write(f"处理学科: {subject_col}, 教师: {teacher_name}")
                
                # 获取学科ID
                subject_id = None
                
                # 1. 直接从映射中查找完整的列名
                if subject_col in subject_map:
                    subject_id = subject_map[subject_col]
                else:
                    # 2. 尝试从映射中查找部分匹配
                    for key, value in subject_map.items():
                        if key in subject_col or subject_col in key:
                            subject_id = value
                            break
                
                if not subject_id:
                    if debug:
                        self.stdout.write(self.style.ERROR(f"无法识别学科: {subject_col}"))
                    error_count += 1
                    continue
                
                # 查找学科
                try:
                    subject = Subject.objects.get(subject_id=subject_id)
                except Subject.DoesNotExist:
                    if debug:
                        self.stdout.write(self.style.ERROR(f"学科不存在: {subject_id}"))
                    error_count += 1
                    continue
                
                # 根据教师姓名查找教师记录 - 更灵活的匹配方式
                try:
                    # 1. 精确匹配当前学校教师
                    teacher = Teacher.objects.filter(
                        name=teacher_name,
                        current_school__school_id=school_id
                    ).first()
                    
                    # 2. 如果未找到，尝试在所有教师中查找
                    if not teacher:
                        teacher = Teacher.objects.filter(name=teacher_name).first()
                    
                    # 3. 如果仍未找到，尝试模糊匹配
                    if not teacher and len(teacher_name) > 1:
                        if debug:
                            self.stdout.write(f"尝试模糊匹配教师: {teacher_name}")
                        # 使用包含查询
                        possible_teachers = Teacher.objects.filter(
                            name__contains=teacher_name[:2],
                            current_school__school_id=school_id
                        )
                        if possible_teachers.exists():
                            if debug:
                                self.stdout.write(f"找到可能匹配的教师: {[t.name for t in possible_teachers]}")
                            teacher = possible_teachers.first()
                    
                    if not teacher:
                        if debug:
                            self.stdout.write(self.style.ERROR(f"教师不存在: {teacher_name} (在学校 {school_id})"))
                        error_count += 1
                        continue
                        
                except Exception as e:
                    if debug:
                        self.stdout.write(self.style.ERROR(f"查找教师错误: {str(e)}"))
                    error_count += 1
                    continue
                
                # 判断教师是否班主任（通常一个班级只有一个班主任）
                is_class_teacher = False
                admin_position = ''
                
                # 创建或更新TeacherHistory记录
                try:
                    # 检查是否已存在相同记录
                    exists = TeacherHistory.objects.filter(
                        teacher=teacher,
                        school=school,
                        semester=semester,
                        subject=subject,
                        class_field=class_obj
                    ).exists()
                    
                    if exists and not update_existing:
                        # 如果记录已存在且不更新，跳过
                        if debug:
                            self.stdout.write(f"跳过已存在的记录: {teacher.name} - {subject.subject_name} - {class_obj.class_name}")
                        continue
                    
                    # 创建或更新历史记录
                    history, created = TeacherHistory.objects.update_or_create(
                        teacher=teacher,
                        school=school,
                        semester=semester,
                        subject=subject,
                        class_field=class_obj,
                        defaults={
                            'grade': grade,
                            'is_class_teacher': is_class_teacher,
                            'admin_position': admin_position,
                            'start_date': semester.start_date,
                            'end_date': semester.end_date,
                            'status': 'COMPLETED'
                        }
                    )
                    
                    if created:
                        created_count += 1
                        if debug:
                            self.stdout.write(self.style.SUCCESS(f"创建教师历史记录: {teacher.name} - {subject.subject_name} - {class_obj.class_name}"))
                    else:
                        updated_count += 1
                        if debug:
                            self.stdout.write(f"更新教师历史记录: {teacher.name} - {subject.subject_name} - {class_obj.class_name}")
                            
                except Exception as e:
                    if debug:
                        self.stdout.write(self.style.ERROR(f"创建历史记录错误: {str(e)}"))
                    error_count += 1
                    
        except Exception as e:
            if debug:
                self.stdout.write(self.style.ERROR(f"处理行数据错误: {str(e)}"))
            error_count += 1
            
        return created_count, updated_count, error_count
    
    def handle(self, *args, **options):
        """
        命令处理主函数。
        
        Args:
            *args: 位置参数
            **options: 关键字参数，包含命令行选项
            
        Returns:
            无
            
        Raises:
            CommandError: 当文件不存在或处理过程出错时抛出
        """
        file_path = options['file_path']
        sheet_name = options['sheet']
        debug = options['debug']
        update_existing = options['update']
        batch_size = options['batch_size']
        skip_validation = options['skip_validation']
        dry_run = options['dry_run']
        semester_id = options['semester_id']
        
        # 配置日志级别
        if debug:
            logger.setLevel(logging.DEBUG)
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            raise CommandError(f'文件不存在: {file_path}')
        
        try:
            # 显示导入开始信息
            self.stdout.write("="*80)
            self.stdout.write(self.style.SUCCESS(f"开始从 {file_path} 导入教师历史数据"))
            self.stdout.write(f"使用学期ID: {semester_id}")
            if dry_run:
                self.stdout.write(self.style.WARNING("试运行模式：不会实际写入数据库"))
            self.stdout.write("="*80)
            
            # 读取Excel文件
            try:
                df = pd.read_excel(file_path, sheet_name=sheet_name)
                self.stdout.write(f'成功读取文件，共 {len(df)} 条记录')
            except Exception as e:
                raise CommandError(f'读取Excel文件失败: {str(e)}')
            
            # 获取学科映射
            subject_map = self.get_subject_id_map()
            self.stdout.write(f'获取到学科映射: {len(subject_map)} 个学科')
            
            # 数据验证
            if not skip_validation:
                valid, subject_columns = self.validate_data(df)
                if valid:
                    self.stdout.write(self.style.SUCCESS("数据验证通过"))
                    self.stdout.write(f"识别到的学科列: {', '.join(subject_columns)}")
            else:
                # 如果跳过验证，手动设置列名映射
                self.column_map = {
                    '学校代码': '学校代码',
                    '年级': '年级',
                    '班别': '班别'  # 请确保这与Excel中的实际列名匹配
                }
                
                # 排除基本列的其余列视为学科列
                identified_columns = list(self.column_map.values()) + ['学校名称']
                subject_columns = [col for col in df.columns if col not in identified_columns]
                self.stdout.write(f"跳过验证，识别到的学科列: {', '.join(subject_columns)}")
            
            # 获取学期对象
            try:
                semester = Semester.objects.get(semester_id=semester_id)
            except Semester.DoesNotExist:
                raise CommandError(f"学期不存在: {semester_id}")
            
            created_count = 0
            updated_count = 0
            error_count = 0
            
            # 初始化错误记录列表
            self.error_records = []
            
            # 按批次处理数据
            total_rows = len(df)
            batches = (total_rows + batch_size - 1) // batch_size
            
            for batch_idx in range(batches):
                start_idx = batch_idx * batch_size
                end_idx = min((batch_idx + 1) * batch_size, total_rows)
                
                self.stdout.write(f"处理批次 {batch_idx+1}/{batches} (记录 {start_idx+1}-{end_idx})")
                
                batch_created = 0
                batch_updated = 0
                batch_error = 0
                
                # 为每个批次创建独立的事务
                with transaction.atomic():
                    sid = transaction.savepoint()
                    
                    try:
                        for idx in range(start_idx, end_idx):
                            row = df.iloc[idx]
                            
                            # 为每行创建独立的保存点
                            row_sid = transaction.savepoint()
                            
                            try:
                                row_created, row_updated, row_error = self.process_row(
                                    row, 
                                    subject_columns, 
                                    subject_map, 
                                    semester,
                                    debug, 
                                    update_existing
                                )
                                
                                batch_created += row_created
                                batch_updated += row_updated
                                batch_error += row_error
                                
                            except Exception as e:
                                # 如果处理行时出错，回滚到该行的保存点，但继续处理其他行
                                transaction.savepoint_rollback(row_sid)
                                batch_error += 1
                                self.stdout.write(self.style.ERROR(f"处理行 {idx+1} 时出错: {str(e)}"))
                                
                                # 添加错误记录
                                try:
                                    # 尝试从当前行获取这些值1
                                    school_id = str(row[self.column_map['学校代码']]).strip() if self.column_map.get('学校代码') in row else '未知'
                                    grade_level = str(row[self.column_map['年级']]).strip() if self.column_map.get('年级') in row else '未知'
                                    class_name = str(row[self.column_map['班别']]).strip() if self.column_map.get('班别') in row else '未知'
                                except:
                                    # 如果获取失败，使用通用标记
                                    school_id = grade_level = class_name = '未知'
                                
                                self.error_records.append({"行号": idx+1, "学校": school_id, "年级": grade_level, "班级": class_name, "错误": str(e)})
                        
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
            
            # 输出导入结果摘要
            self.stdout.write("="*80)
            status_msg = "历史数据试运行完成!" if dry_run else "历史数据导入完成!"
            self.stdout.write(self.style.SUCCESS(status_msg))
            self.stdout.write(f"新建历史记录: {created_count}")
            self.stdout.write(f"更新历史记录: {updated_count}")
            self.stdout.write(f"错误记录: {error_count}")
            
            # 在处理完所有批次后，如果有错误记录，则输出
            if self.error_records:
                self.stdout.write("="*80)
                self.stdout.write(self.style.ERROR("错误记录明细:"))
                for idx, error in enumerate(self.error_records):
                    self.stdout.write(f"{idx+1}. 行 {error['行号']}: {error['学校']} {error['年级']} {error['班级']} - {error['错误']}")
            
            # 在所有批次处理完成后，保存错误记录
            if self.error_records:
                error_file = 'import_errors.json'
                with open(error_file, 'w') as f:
                    json.dump(self.error_records, f, ensure_ascii=False, indent=2)
                self.stdout.write(self.style.WARNING(f"错误记录已保存到 {error_file}"))
            
            self.stdout.write("="*80)
        
        except Exception as e:
            raise CommandError(f'导入过程出错: {str(e)}') 