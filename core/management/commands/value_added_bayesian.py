"""
基于贝叶斯多层次模型的教育增值评价系统

功能特点：
1. 学生个体成长模型
2. 教师教学效能评估
3. 学校增值效应分析
4. 多时间点纵向数据分析
"""

import pymc as pm
import pandas as pd
import numpy as np
import logging
import uuid
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import transaction
from core.models import (
    ValueAddedEvaluation, 
    Semester, 
    Subject,
    StudentHistory,
    TeacherHistory,
    Score,
    Exam,
)
import matplotlib.pyplot as plt
from io import BytesIO
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.chart import BarChart, Reference
import warnings
import pytensor
import arviz as az

logger = logging.getLogger(__name__)

class ValueAddedDataProcessor:
    """增值分析数据处理器
    
    功能特性：
    - 使用Django ORM进行高效数据查询
    - 自动处理层级编码
    - 标准化分数处理
    - 数据质量验证
    """
    
    def __init__(self, subject_id=None, semester_range=3, exam_ids=None):
        """
        初始化处理器
        
        Args:
            subject_id: str 学科ID，如果指定则只分析该学科
            semester_range: int 分析的学期范围（默认最近3个学期）
            exam_ids: list 指定的考试ID列表
        """
        self.semester_range = semester_range
        self.subject_id = subject_id
        self.exam_ids = exam_ids
        self.mappings = {
            'schools': {},
            'teachers': {},
            'students': {}
        }
        
    def process(self):
        """执行层级化数据处理流程"""
        logger.info("开始层级化数据处理流程")
        
        # 步骤1：获取考试信息 - 传递exam_ids参数
        exams = self._get_target_exams(exam_ids=self.exam_ids)
        if not exams:
            raise ValueError("未找到符合条件的考试")
        
        logger.info(f"找到{len(exams)}个符合条件的考试: {[e.exam_id for e in exams]}")
        
        # 步骤2：获取成绩数据
        raw_scores_df = self._get_scores(exams)
        if raw_scores_df.empty:
            raise ValueError("未找到符合条件的成绩记录")
            
        logger.info(f"初始数据: {len(raw_scores_df)}条成绩记录，涉及{raw_scores_df['student_id'].nunique()}名学生")
        
        # 步骤3：获取学生历史记录并关联班级和学校信息
        student_records = self._get_student_history(raw_scores_df)
        logger.info(f"成功关联{len(student_records)}条学生历史记录")
        
        # 第一层级：学校层面处理
        logger.info("===== 第一层级：学校数据处理 =====")
        
        # 1.1 分析学校分布情况
        school_counts = student_records['school_id'].value_counts()
        logger.info(f"数据中包含{len(school_counts)}所学校")
        
        # 1.2 剔除小规模学校(学生少于10人)
        small_schools = school_counts[school_counts < 10]
        if not small_schools.empty:
            logger.warning(f"发现{len(small_schools)}所小规模学校(学生<10人)，进行移除")
            for school_id, count in small_schools.items():
                logger.warning(f"移除学校: {school_id}, 学生数:{count}")
            
            original_count = len(student_records)
            student_records = student_records[~student_records['school_id'].isin(small_schools.index)]
            logger.info(f"移除小规模学校后，数据减少{original_count-len(student_records)}条")
        
        # 1.3 按学期统计学校出现情况，识别不完整学校
        semester_count = student_records['semester_id'].nunique()
        school_semester_counts = student_records.groupby('school_id')['semester_id'].nunique()
        incomplete_schools = school_semester_counts[school_semester_counts < semester_count]
        
        if not incomplete_schools.empty:
            logger.warning(f"发现{len(incomplete_schools)}所学校未出现在所有{semester_count}个学期中")
            for school_id, count in incomplete_schools.items():
                semesters = student_records[student_records['school_id'] == school_id]['semester_id'].unique()
                logger.warning(f"移除学校: {school_id}, 仅出现在{count}/{semester_count}个学期")
            
            original_count = len(student_records)
            student_records = student_records[~student_records['school_id'].isin(incomplete_schools.index)]
            logger.info(f"移除不完整学期的学校后，数据减少{original_count-len(student_records)}条")
        
        # 第二层级：班级层面处理
        logger.info("===== 第二层级：班级数据处理 =====")
        
        # 2.1 班级规范化
        student_records = self._normalize_class_groups_by_latest_exam(student_records)
        original_class_count = student_records['class_id'].nunique()
        normalized_class_count = student_records['norm_class_group'].nunique()
        logger.info(f"班级规范化: 从{original_class_count}个减少到{normalized_class_count}个 (减少率:{100*(original_class_count-normalized_class_count)/original_class_count:.1f}%)")
        
        # 2.2 进一步合并小班级
        student_records = self._further_consolidate_classes(student_records)
        final_class_count = student_records['norm_class_group'].nunique()
        logger.info(f"小班级合并后: 从{normalized_class_count}个减少到{final_class_count}个")
        
        # 2.3 移除规模太小的班级
        class_sizes = student_records.groupby('norm_class_group')['student_id'].nunique()
        small_classes = class_sizes[class_sizes < 10]
        
        if not small_classes.empty:
            logger.warning(f"发现{len(small_classes)}个小规模班级(学生<10人)，进行移除")
            for class_id, count in small_classes.items():
                logger.warning(f"移除班级: {class_id}, 学生数:{count}")
            
            original_count = len(student_records)
            student_records = student_records[~student_records['norm_class_group'].isin(small_classes.index)]
            logger.info(f"移除小规模班级后，数据减少{original_count-len(student_records)}条")
        
        # 第三层级：学生层面处理  
        logger.info("===== 第三层级：学生数据处理 =====")
        
        # 3.1 清洗数据
        clean_data = self._clean_data(student_records)
        logger.info(f"数据清洗后: {len(clean_data)}条记录，{clean_data['student_id'].nunique()}名学生")
        
        # 3.2 准备模型数据
        prep_data = self._prepare_for_model(clean_data)
        
        # 总结处理结果
        logger.info(f"层级化数据处理完成: {len(prep_data)}条记录, {prep_data['student_id'].nunique()}名学生, "
                    f"{prep_data['school_id'].nunique()}所学校, {prep_data['norm_class_group'].nunique()}个班级")
        
        return prep_data, self.mappings
        
    def _get_target_exams(self, exam_ids=None, exam_type=None):
        """获取目标学期范围内的考试"""
        # 如果直接指定了考试ID，则优先使用
        if exam_ids:
            # 添加一个宽松查询选项
            exam_query = Exam.objects.filter(status='COMPLETE')
            
            # 尝试精确匹配
            exact_match = exam_query.filter(exam_id__in=exam_ids)
            if exact_match.exists():
                logger.info(f"找到精确匹配的考试: {list(exact_match.values_list('exam_id', flat=True))}")
                return list(exact_match.select_related('semester'))
                
            # 如果精确匹配失败，尝试使用包含匹配
            contains_matches = []
            for exam_id in exam_ids:
                partial_matches = exam_query.filter(exam_id__contains=exam_id)
                contains_matches.extend(list(partial_matches))
                
            if contains_matches:
                logger.info(f"未找到精确匹配，使用部分匹配: {[e.exam_id for e in contains_matches]}")
                return contains_matches
                
            # 两种方式都失败，提示可用的考试ID
            available_ids = list(exam_query.values_list('exam_id', flat=True)[:10])
            raise ValueError(f"未找到指定的考试ID: {exam_ids}\n可用的考试ID示例: {available_ids}")
        
        # 获取目标学期
        latest_semester = Semester.objects.filter(status='ACTIVE').order_by('-end_date').first()
        if not latest_semester:
            raise ValueError("未找到活动学期")
            
        target_semesters = list(Semester.objects.filter(
            end_date__lte=latest_semester.end_date
        ).order_by('-end_date')[:self.semester_range].values_list('semester_id', flat=True))
        
        # 构建考试查询
        exam_query = Exam.objects.filter(
            semester_id__in=target_semesters,
            status='COMPLETE'
        )
        
        # 如果指定了考试类型，添加过滤
        if exam_type:
            exam_query = exam_query.filter(exam_type=exam_type)
        
        exams = list(exam_query.select_related('semester'))
        
        # 验证是否获取到考试
        if not exams:
            filters = f"学期: {target_semesters}"
            if exam_type:
                filters += f", 类型: {exam_type}"
            raise ValueError(f"未找到符合条件的考试 ({filters})")
        
        return exams
        
    def _get_scores(self, exams):
        """从Score表获取成绩数据"""
        exam_ids = [exam.exam_id for exam in exams]
        
        # 构建成绩查询
        score_query = Score.objects.filter(
            exam_id__in=exam_ids
        ).select_related('exam', 'subject', 'student')
        
        # 如果指定了学科，添加过滤
        if self.subject_id:
            score_query = score_query.filter(subject_id=self.subject_id)
            
        # 获取成绩记录
        scores = []
        for score in score_query:
            # 验证T分数有效性
            if score.standard_score < 200 or score.standard_score > 900:
                logger.warning(f"发现无效T分数: {score.standard_score}, student_id={score.student_id}, exam_id={score.exam_id}")
                continue
                
            # 记录学生信息
            self.mappings['students'][score.student_id] = score.student.name
                
            # 添加记录
            scores.append({
                'student_id': score.student_id,
                'exam_id': score.exam_id,
                'subject_id': score.subject_id,
                'semester_id': score.exam.semester_id,
                'standard_score': score.standard_score,
                'exam_date': score.exam.start_time
            })
            
        return pd.DataFrame(scores)
    
    def _get_student_history(self, scores_df):
        """获取学生历史记录，包括班级和学校信息"""
        # 获取需要查询的学生ID列表
        student_ids = scores_df['student_id'].unique().tolist()
        
        # 先使用select_related，然后再使用values
        student_records = StudentHistory.objects.filter(
            student_id__in=student_ids,
            status='ACTIVE'
        ).select_related('school', 'class_field').values(
            'student_id', 'semester_id', 'class_field_id', 
            'grade_id', 'school_id', 'school__school_name'
        )
        
        # 转换为DataFrame并重命名列
        records_df = pd.DataFrame(list(student_records))
        if not records_df.empty:
            # 重命名列以保持一致性
            records_df = records_df.rename(columns={
                'class_field_id': 'class_id',
                'school__school_name': 'school_name',
                'grade_id': 'grade_level'
            })
            
            # 添加班级名称（尝试从关联对象获取）
            try:
                records_df['class_name'] = records_df['class_id'].apply(
                    lambda x: str(x).split('_')[1] if isinstance(x, str) and '_' in str(x) else str(x)
                )
            except Exception as e:
                logger.warning(f"无法提取班级名称: {e}")
                records_df['class_name'] = records_df['class_id']
        
        # 如果记录为空，提供有用的错误信息
        if records_df.empty:
            logger.error(f"未找到任何学生历史记录。检查的学生ID: {student_ids[:5]}...")
            raise ValueError("未能获取学生班级和学校信息")
        
        # 与成绩数据合并
        merged_df = pd.merge(
            scores_df, 
            records_df,
            on=['student_id', 'semester_id'],
            how='left'
        )
        
        # 检查是否有缺失的记录
        missing_count = merged_df['class_id'].isna().sum()
        if missing_count > 0:
            missing_pct = 100 * missing_count / len(merged_df)
            logger.warning(f"有{missing_count}条记录({missing_pct:.1f}%)未找到班级信息")
        
        # 为班级和学校编码创建映射
        self.mappings['schools'] = dict(zip(
            records_df['school_id'], 
            records_df['school_name']
        ))
        
        # 创建班级编码
        class_mapping = {}
        for _, row in records_df.drop_duplicates(['class_id']).iterrows():
            class_mapping[row['class_id']] = row['class_name']
        
        self.mappings['classes'] = class_mapping
        
        return merged_df
    
    def _clean_data(self, df):
        """数据清洗和验证"""
        logger.info(f"清洗前数据条数: {len(df)}, 学生数: {df['student_id'].nunique()}")
        
        # 保存重要列列表，确保这些列在清洗过程中不会丢失
        preserved_columns = ['norm_class_group'] 
        has_norm_class = 'norm_class_group' in df.columns
        
        # 步骤1: 移除缺失关键字段的记录(保留这步是必要的，确保数据完整性)
        clean_df = df.dropna(subset=['school_id', 'class_id', 'standard_score'])
        logger.info(f"移除缺失字段后剩余: {len(clean_df)}")
        
        # 移除标准分异常的记录
        clean_df = clean_df[(clean_df['standard_score'] >= 200) & (clean_df['standard_score'] <= 900)]
        logger.info(f"移除异常标准分后剩余: {len(clean_df)}")
        
        # 步骤2: 如果指定了多个考试ID，只保留参加了所有考试的学生
        if self.subject_id and len(self.subject_id) > 1:
            # 分析每个学生参加的考试数量
            student_exam_counts = clean_df.groupby('student_id')['exam_id'].nunique()
            required_exams_count = len(self.subject_id)
            
            # 找出参加了所有考试的学生
            complete_students = student_exam_counts[student_exam_counts >= required_exams_count].index
            
            # 筛选数据
            clean_df = clean_df[clean_df['student_id'].isin(complete_students)]
            logger.info(f"要求参加全部{required_exams_count}个考试后剩余: {len(clean_df)}条记录，{len(complete_students)}名学生")
        
        # 确保数据集不为空
        if len(clean_df) == 0:
            raise ValueError("清洗后无有效数据剩余，请检查数据质量或考试参与情况")
        
        logger.info(f"清洗后最终数据：{len(clean_df)}条记录，{clean_df['student_id'].nunique()}名学生")
        
        # 确保规范化班级ID被保留
        if has_norm_class and 'norm_class_group' not in clean_df.columns:
            logger.warning("在清洗过程中规范化班级ID列丢失，重新添加")
            # 如果有记录原始映射关系，则恢复；否则重新规范化
            clean_df = self._normalize_class_groups_by_latest_exam(clean_df)
        
        return clean_df
    
    def _prepare_for_model(self, clean_df):
        """准备模型输入数据，包括编码和标准化"""
        df = clean_df.copy()
        
        # 添加数值编码（使用分类编码）
        df['student_code'] = df['student_id'].astype('category').cat.codes
        df['school_code'] = df['school_id'].astype('category').cat.codes
        
        # 检查是否存在teacher_id，如果不存在则跳过教师编码
        if 'teacher_id' in df.columns:
            df['teacher_code'] = df['teacher_id'].astype('category').cat.codes
        else:
            # 为模型兼容性添加一个默认值
            logger.info("没有教师信息，使用班级ID作为教师代码")
            df['teacher_id'] = df['class_id']  # 使用班级ID代替
            df['teacher_code'] = df['class_id'].astype('category').cat.codes
        
        # 确保使用规范化的班级群组ID
        if 'norm_class_group' in df.columns:
            norm_classes = df['norm_class_group'].nunique()
            orig_classes = df['class_id'].nunique()
            reduction = orig_classes - norm_classes
            
            logger.info(f"使用规范化班级ID: 从{orig_classes}减少到{norm_classes}个班级(减少{reduction}个，{100*reduction/orig_classes:.1f}%)")
            df['class_code'] = df['norm_class_group'].astype('category').cat.codes
        else:
            # 如果规范化班级ID不存在，重新规范化
            logger.warning("缺少规范化班级群组ID，重新进行班级规范化")
            df = self._normalize_class_groups_by_latest_exam(df)
            df = self._further_consolidate_classes(df)
            df['class_code'] = df['norm_class_group'].astype('category').cat.codes
        
        # 时间点编码
        if 'time_point' not in df.columns:
            logger.info("添加时间点索引")
            # 按学生ID和学期排序
            df = df.sort_values(['student_id', 'semester_id'])
            # 为每个学生的记录添加时间点索引
            df['time_point'] = df.groupby('student_id').cumcount()
        
        # 确保有先前成绩信息
        if 'prior_score' not in df.columns:
            logger.info("计算先前成绩")
            # 使用第一次考试成绩作为基线
            baseline = df[df['time_point'] == 0][['student_id', 'standard_score']]
            baseline = baseline.rename(columns={'standard_score': 'prior_score'})
            # 合并回原始数据
            df = pd.merge(df, baseline, on='student_id', how='left')
            # 对于第一次考试，使用该考试成绩作为prior_score
            df.loc[df['time_point'] == 0, 'prior_score'] = df.loc[df['time_point'] == 0, 'standard_score']
        
        logger.info(f"数据准备完成: {len(df)}条记录, {df['student_id'].nunique()}名学生, " + 
                   f"{df['school_id'].nunique()}所学校, {df['norm_class_group'].nunique()}个班级群组")
        
        return df

    def _extract_class_info(self, class_field_id):
        """解析班级ID信息
        
        Args:
            class_field_id: str 班级ID，格式如"C02_71_231"
            
        Returns:
            tuple: (学校编号, 年级, 班号, 学年)
        """
        if not class_field_id or not isinstance(class_field_id, str):
            return None, None, None, None
        
        try:
            # 解析格式: C02_71_231
            parts = class_field_id.split('_')
            if len(parts) != 3:
                return None, None, None, None
            
            school_code = parts[0].replace('C', '')  # 提取"02"
            grade_class = parts[1]  # 提取"71"
            year_code = parts[2]    # 提取"231"
            
            grade = grade_class[0]  # 年级:"7" 
            class_num = grade_class[1:]  # 班号:"1"
            
            return school_code, grade, class_num, year_code
        except Exception as e:
            logger.warning(f"班级ID解析失败: {class_field_id}, 错误: {e}")
            return None, None, None, None
        
    def _track_class_changes(self, class_records):
        """追踪班级变化
        
        Args:
            class_records: list 班级记录列表，按学期排序
            
        Returns:
            dict: 学期到班级的映射
        """
        # 如果只有一条记录，直接返回
        if len(class_records) <= 1:
            return {record['semester_id']: record['class_id'] for record in class_records}
        
        # 按学期排序
        sorted_records = sorted(class_records, key=lambda x: x['semester_id'])
        
        # 初始化结果
        class_map = {sorted_records[0]['semester_id']: sorted_records[0]['class_id']}
        
        # 提取第一个班级的信息
        first_record = sorted_records[0]
        school_code, grade, class_num, _ = self._extract_class_info(first_record['class_id'])
        
        # 如果无法解析第一个班级ID，直接返回
        if not school_code:
            return {record['semester_id']: record['class_id'] for record in sorted_records}
        
        # 遍历后续学期，预测班级ID
        curr_grade = int(grade)
        for i in range(1, len(sorted_records)):
            prev_record = sorted_records[i-1]
            curr_record = sorted_records[i]
            
            # 检查是否为不同学年
            if curr_record['semester_id'] > prev_record['semester_id']:
                # 这是新学年，年级应该加1
                curr_grade += 1
                
                # 解析当前班级ID，确认变化是否符合预期
                _, new_grade, new_class, _ = self._extract_class_info(curr_record['class_id'])
                
                if new_grade and int(new_grade) == curr_grade:
                    # 班级变化符合预期
                    class_map[curr_record['semester_id']] = curr_record['class_id']
                else:
                    # 如果解析失败或年级不符合预期，尝试构建预期的班级ID
                    _, _, _, year_code = self._extract_class_info(curr_record['class_id'])
                    if year_code:
                        predicted_class = f"C{school_code}_{curr_grade}{class_num}_{year_code}"
                        logger.info(f"学生班级变化: {prev_record['class_id']} -> {predicted_class} (预测)")
                        class_map[curr_record['semester_id']] = predicted_class
                    else:
                        # 无法预测，使用实际班级
                        class_map[curr_record['semester_id']] = curr_record['class_id']
            else:
                # 同一学年，使用实际班级
                class_map[curr_record['semester_id']] = curr_record['class_id']
        
        return class_map

    def _normalize_class_groups(self, data):
        """创建规范化班级群体ID，识别跨学期的相同班级"""
        logger.info("开始分析班级连续性...")
        
        # 确保数据包含必要的列
        required_cols = ['student_id', 'semester_id', 'class_id', 'school_id']
        missing_cols = [col for col in required_cols if col not in data.columns]
        if missing_cols:
            # 如果缺少class_id列但有class_field_id列，进行重命名
            if 'class_id' in missing_cols and 'class_field_id' in data.columns:
                data = data.rename(columns={'class_field_id': 'class_id'})
                missing_cols.remove('class_id')
            
            # 如果仍有缺失列，则报错
            if missing_cols:
                raise ValueError(f"数据缺少必要的列: {missing_cols}")
        
        # 按学生ID和学期ID排序数据
        data = data.sort_values(['student_id', 'semester_id'])
        
        # 跟踪学生在不同学期的班级
        student_classes = data.groupby('student_id')['class_id'].apply(list)
        
        # 创建班级连续性映射字典
        class_continuity = {}
        transitions_count = 0
        
        # 分析每个学生的班级连续性
        for classes in student_classes:
            if len(classes) > 1:  # 只分析有多个学期记录的学生
                for i in range(len(classes)-1):
                    current = classes[i]
                    next_class = classes[i+1]
                    
                    if current not in class_continuity:
                        class_continuity[current] = {}
                        
                    if next_class not in class_continuity[current]:
                        class_continuity[current][next_class] = 0
                        
                    class_continuity[current][next_class] += 1
                    transitions_count += 1
        
        logger.info(f"分析了{transitions_count}个班级转换记录")
        
        # 创建班级规范化映射
        normalized_classes = {}
        used_classes = set()
        class_group_id = 0
        
        # 首先处理连续性强的班级
        for current, transitions in sorted(
            class_continuity.items(), 
            key=lambda x: max(x[1].values()) if x[1] else 0,
            reverse=True
        ):
            if current in used_classes:
                continue
            
            # 找到最可能的班级连续链
            class_chain = [current]
            current_class = current
            used_classes.add(current)
            
            while current_class in class_continuity and class_continuity[current_class]:
                # 找到最强的连续性
                next_class, count = max(
                    class_continuity[current_class].items(),
                    key=lambda x: x[1]
                )
                
                # 学生连续性至少要有5名学生
                if count < 5:
                    break
                
                class_chain.append(next_class)
                used_classes.add(next_class)
                current_class = next_class
            
            # 创建班级群体ID
            if len(class_chain) > 1:  # 只为确实有连续性的班级创建群体
                group_id = f"G{class_group_id}"
                for cls in class_chain:
                    normalized_classes[cls] = group_id
                class_group_id += 1
        
        # 处理剩余未分组的班级
        for cls in set(data['class_id'].unique()) - used_classes:
            group_id = f"G{class_group_id}"
            normalized_classes[cls] = group_id
            class_group_id += 1
        
        # 添加规范化班级ID到数据中
        data['norm_class_group'] = data['class_id'].map(normalized_classes)
        
        # 记录统计信息
        original_classes = len(data['class_id'].unique())
        normalized_classes = len(data['norm_class_group'].unique())
        reduction = original_classes - normalized_classes
        
        logger.info(f"原始班级数量: {original_classes}")
        logger.info(f"规范化后班级群体数量: {normalized_classes}")
        logger.info(f"减少了{reduction}个班级({100*reduction/original_classes:.1f}%)")
        
        return data

    def _normalize_class_groups_by_latest_exam(self, data):
        """使用最后一次考试的班级作为规范化班级ID
        
        这种方法假设最后一次考试时的班级编排已经稳定，且能代表整个学习期间的学生群体
        """
        logger.info("使用最后一次考试班级作为规范化班级ID...")
        
        # 1. 确定每个学生的最后一次考试
        data = data.sort_values(['student_id', 'semester_id'])
        
        # 获取每个学生最后一次考试记录
        latest_exams = data.groupby('student_id').tail(1)
        
        # 2. 提取学生最后一次考试的班级ID
        student_latest_class = dict(zip(latest_exams['student_id'], latest_exams['class_id']))
        
        # 3. 为每个学生的所有记录分配最后一次考试的班级ID
        data['norm_class_group'] = data['student_id'].map(student_latest_class)
        
        # 4. 记录规范化效果
        original_classes = len(data['class_id'].unique())
        normalized_classes = len(data['norm_class_group'].unique())
        reduction = original_classes - normalized_classes
        reduction_pct = 100 * reduction / original_classes if original_classes > 0 else 0
        
        logger.info(f"原始班级数量: {original_classes}")
        logger.info(f"规范化后班级数量: {normalized_classes} (减少了{reduction}个，{reduction_pct:.1f}%)")
        
        # 5. 分析每个规范化班级群体的学生数量
        class_sizes = data.groupby('norm_class_group')['student_id'].nunique()
        logger.info(f"班级群体大小统计: 最小{class_sizes.min()}人，中位数{class_sizes.median()}人，最大{class_sizes.max()}人")
        
        return data

    def _further_consolidate_classes(self, data):
        """进一步合并班级，基于班级名称模式和学校
        
        例如："7年级1班上"和"7年级1班下"应合并为同一个班级群体
        """
        # 提取班级核心标识（如班号）
        data['class_core'] = data['class_name'].apply(
            lambda x: ''.join(filter(str.isdigit, str(x))) if x else 'unknown'
        )
        
        # 按学校和班级核心ID分组
        grouped = data.groupby(['school_id', 'class_core'])
        
        # 创建新的合并ID
        merge_mapping = {}
        for i, ((school, core), group) in enumerate(grouped):
            for class_id in group['norm_class_group'].unique():
                merge_mapping[class_id] = f"M{i}"
        
        # 应用合并
        original_count = data['norm_class_group'].nunique()
        data['norm_class_group'] = data['norm_class_group'].map(merge_mapping)
        merged_count = data['norm_class_group'].nunique()
        
        logger.info(f"班级进一步合并: 从{original_count}个减少到{merged_count}个 (减少{original_count-merged_count}个)")
        
        return data

    def _aggressive_class_consolidation(self, data):
        """强制班级合并策略，显著减少班级数量
        
        此方法基于学校、年级和班号进行合并，不考虑历史连续性
        """
        logger.info("执行强制班级合并以显著减少班级数量...")
        
        # 首先提取班号（假设班号是class_id中的数字部分）
        def extract_class_number(class_id):
            if not class_id or not isinstance(class_id, str):
                return "00"
            # 提取所有数字
            digits = ''.join(filter(str.isdigit, class_id))
            return digits[-2:] if len(digits) >= 2 else digits.zfill(2)
        
        # 提取年级（尝试多种可能的格式）
        def extract_grade(row):
            # 如果有grade_level字段，优先使用
            if 'grade_level' in row and pd.notna(row['grade_level']):
                grade = str(row['grade_level'])
                if grade and grade.isdigit():
                    return grade
            
            # 尝试从class_id中提取
            if isinstance(row['class_id'], str):
                # 尝试从格式如"C07_"中提取
                if '_' in row['class_id']:
                    prefix = row['class_id'].split('_')[0]
                    grade = ''.join(filter(str.isdigit, prefix))
                    if grade:
                        return grade
            
            # 默认返回
            return "0"
        
        # 提取特征并创建合并ID
        data['extract_grade'] = data.apply(extract_grade, axis=1)
        data['extract_class_num'] = data['class_id'].apply(extract_class_number)
        
        # 创建合并键：学校ID + 年级 + 班号
        data['merge_key'] = data['school_id'].astype(str) + "_" + \
                            data['extract_grade'].astype(str) + "_" + \
                            data['extract_class_num'].astype(str)
        
        # 创建映射
        merge_mapping = {}
        for i, key in enumerate(data['merge_key'].unique()):
            merge_mapping[key] = f"M{i:03d}"
        
        # 应用合并
        original_count = data['class_id'].nunique()
        data['norm_class_group'] = data['merge_key'].map(merge_mapping)
        merged_count = data['norm_class_group'].nunique()
        
        logger.info(f"强制班级合并结果: 从{original_count}个减少到{merged_count}个 (减少{original_count-merged_count}个，{100*(original_count-merged_count)/original_count:.1f}%)")
        
        # 检查合并后每个班级的学生数量
        class_sizes = data.groupby('norm_class_group')['student_id'].nunique()
        logger.info(f"合并后班级规模: 最小{class_sizes.min()}人, 中位数{class_sizes.median()}人, 最大{class_sizes.max()}人, 平均{class_sizes.mean():.1f}人")
        
        return data

    def _optimized_class_consolidation(self, data):
        """基于精确班级ID格式的班级合并方法
        
        班级ID格式: C{校代码末尾}_{年级+班号}_{其他标识符}
        例如: C02_71_231 表示学校02的7年级1班
        """
        logger.info("基于班级ID格式进行精确班级合并...")
        
        # 解析班级ID格式
        def parse_class_id(class_id):
            if not isinstance(class_id, str) or '_' not in class_id:
                return None, None, None
            
            try:
                # 分解格式C02_71_231
                parts = class_id.split('_')
                if len(parts) < 2:
                    return None, None, None
                    
                # 提取学校代码
                school_code = parts[0].replace('C', '')
                
                # 提取年级和班号
                if len(parts[1]) >= 2:
                    grade_class = parts[1]
                    # 71表示7年级1班
                    grade = grade_class[0] if grade_class[0].isdigit() else None
                    class_num = grade_class[1:] if len(grade_class) > 1 else None
                    
                    return school_code, grade, class_num
            except:
                pass
            
            return None, None, None
        
        # 应用解析函数
        parsed_data = []
        for _, row in data.iterrows():
            class_id = row['class_id']
            school_code, grade, class_num = parse_class_id(class_id)
            
            parsed_data.append({
                'row_index': _,
                'school_code': school_code,
                'grade': grade,
                'class_num': class_num
            })
        
        # 转为DataFrame并合并回原始数据
        parsed_df = pd.DataFrame(parsed_data)
        data = pd.concat([data.reset_index(drop=True), parsed_df], axis=1)
        
        # 创建合并键：学校ID + 班号 (忽略年级变化)
        data['merge_key'] = data.apply(
            lambda row: f"{row['school_id']}_{row['class_num']}" 
                        if pd.notna(row['class_num']) else f"{row['school_id']}_unknown_{row.name}",
            axis=1
        )
        
        # 创建映射
        merge_mapping = {}
        for i, key in enumerate(data['merge_key'].unique()):
            merge_mapping[key] = f"M{i:03d}"
        
        # 应用合并
        original_count = data['class_id'].nunique()
        data['norm_class_group'] = data['merge_key'].map(merge_mapping)
        merged_count = data['norm_class_group'].nunique()
        
        logger.info(f"精确班级合并结果: 从{original_count}个减少到{merged_count}个 (减少{original_count-merged_count}个，{100*(original_count-merged_count)/original_count:.1f}%)")
        
        # 验证每个合并班级的年级分布
        grade_distribution = data.groupby('norm_class_group')['grade'].nunique()
        multi_grade = grade_distribution[grade_distribution > 1].count()
        if multi_grade > 0:
            logger.info(f"有{multi_grade}个合并班级包含多个年级，这符合学生升学规律")
        
        # 检查合并后每个班级的学生数量
        class_sizes = data.groupby('norm_class_group')['student_id'].nunique()
        logger.info(f"合并后班级规模: 最小{class_sizes.min()}人, 中位数{class_sizes.median()}人, 最大{class_sizes.max()}人, 平均{class_sizes.mean():.1f}人")
        
        return data

    def process_data_hierarchically(self):
        """层级化数据处理流程：自上而下处理学校-班级-学生"""
        logger.info("===== 开始层级化数据处理 =====")
        
        # 1. 学校层级处理
        logger.info("第一步：学校层级处理")
        
        # 1.1 收集和展示学校信息
        school_info = {}
        for school_id in self.data['school_id'].unique():
            school_name = "未知"
            if 'school_name' in self.data.columns:
                school_names = self.data[self.data['school_id'] == school_id]['school_name'].unique()
                if len(school_names) > 0:
                    school_name = school_names[0]
            school_info[school_id] = school_name
        
        logger.info(f"数据中包含{len(school_info)}所学校:")
        for school_id, name in sorted(school_info.items()):
            logger.info(f"学校ID: {school_id}, 名称: {name}")
        
        # 1.2 剔除小规模学校(学生少于10人)
        school_student_counts = self.data.groupby('school_id')['student_id'].nunique()
        small_schools = school_student_counts[school_student_counts < 10]
        
        if not small_schools.empty:
            logger.warning(f"发现{len(small_schools)}所小规模学校(学生<10人)，进行移除")
            for school_id in small_schools.index:
                logger.warning(f"移除学校: {school_id} ({school_info.get(school_id,'未知')}), 学生数:{small_schools[school_id]}")
            
            original_count = len(self.data)
            self.data = self.data[~self.data['school_id'].isin(small_schools.index)]
            logger.info(f"移除小规模学校后，数据减少{original_count-len(self.data)}条")
        
        # 1.3 处理不在所有学期出现的学校
        school_analysis = self.analyze_school_data()
        semester_count = self.data['semester_id'].nunique()
        
        school_semester_counts = self.data.groupby('school_id')['semester_id'].nunique()
        incomplete_schools = school_semester_counts[school_semester_counts < semester_count]
        
        if not incomplete_schools.empty:
            logger.warning(f"发现{len(incomplete_schools)}所学校未出现在所有{semester_count}个学期中")
            for school_id in incomplete_schools.index:
                semesters = self.data[self.data['school_id'] == school_id]['semester_id'].unique()
                logger.warning(f"移除学校: {school_id} ({school_info.get(school_id,'未知')}), "
                              f"仅出现在{len(semesters)}/{semester_count}个学期")
            
            original_count = len(self.data)
            self.data = self.data[~self.data['school_id'].isin(incomplete_schools.index)]
            logger.info(f"移除不完整学期的学校后，数据减少{original_count-len(self.data)}条")
        
        # 2. 班级层级处理
        logger.info("\n第二步：班级层级处理")
        
        # 2.1 只针对保留的学校数据进行班级规范化
        logger.info("对保留的学校数据进行班级规范化")
        # 实施班级规范化（例如_normalize_class_groups_by_latest_exam和_further_consolidate_classes）
        self.data = self._normalize_class_groups_by_latest_exam(self.data)
        self.data = self._further_consolidate_classes(self.data)
        
        # 2.2 分析规范化后的班级信息
        class_counts = self.data['norm_class_group'].nunique()
        logger.info(f"规范化后班级数量: {class_counts}个班级")
        
        # 2.3 移除小规模班级
        class_student_counts = self.data.groupby('norm_class_group')['student_id'].nunique()
        small_classes = class_student_counts[class_student_counts < 10]
        
        if not small_classes.empty:
            logger.warning(f"发现{len(small_classes)}个小规模班级(学生<10人)，进行移除")
            for class_id in small_classes.index:
                logger.warning(f"移除班级: {class_id}, 学生数:{small_classes[class_id]}")
            
            original_count = len(self.data)
            self.data = self.data[~self.data['norm_class_group'].isin(small_classes.index)]
            logger.info(f"移除小规模班级后，数据减少{original_count-len(self.data)}条")
            logger.info(f"最终剩余{self.data['norm_class_group'].nunique()}个班级，{self.data['student_id'].nunique()}名学生")
        
        # 3. 学生层级处理和数据准备
        logger.info("\n第三步：学生层级处理和数据准备")
        # 可以添加学生层级的处理，如异常值检测等
        
        logger.info(f"层级化处理完成，最终数据包含: {self.data['school_id'].nunique()}所学校，"
                    f"{self.data['norm_class_group'].nunique()}个班级，{self.data['student_id'].nunique()}名学生")
        return self.data

    def get_prepared_data(self):
        """获取处理后的数据"""
        # 如果已经有process()方法处理数据，我们可以调用它
        data, _ = self.process()
        return data

    def get_mappings(self):
        """获取各种ID到名称的映射"""
        # 如果已经有process()方法生成映射，我们可以调用它
        _, mappings = self.process()
        return mappings

class ValueAddedAnalyzer:
    """基于贝叶斯多层次模型的增值分析器"""
    
    def __init__(self, data, teacher_map=None, school_map=None, mappings=None):
        """
        初始化增值分析器
        
        Args:
            data: DataFrame 包含学生成绩数据
            teacher_map: dict 教师ID到名称的映射
            school_map: dict 学校ID到名称的映射
            mappings: dict 包含多种ID映射的字典
        """
        self.data = data
        
        # 处理mappings参数 (新增)
        if mappings:
            self.teacher_map = mappings.get('teachers', {})
            self.school_map = mappings.get('schools', {})
            self.student_map = mappings.get('students', {})
        else:
            self.teacher_map = teacher_map or {}
            self.school_map = school_map or {}
            self.student_map = {}
        
        # 获取数据基本信息
        self.n_students = data['student_id'].nunique()
        self.n_schools = data['school_id'].nunique()
        
        # 教师信息 - 使用norm_class_group而非class_id
        if 'norm_class_group' in data.columns:
            # 使用规范化班级作为教师代码
            self.n_teachers = data['norm_class_group'].nunique()
            logger.info(f"使用规范化班级ID作为教师代码: {self.n_teachers}个教师")
        else:
            # 如果没有规范化班级ID，退回到使用class_id
            self.n_teachers = data['class_id'].nunique() if 'class_id' in data.columns else 0
            logger.warning(f"未找到规范化班级ID，使用原始班级ID: {self.n_teachers}个教师")
        
        # 班级信息 - 确保使用规范化班级ID
        if 'norm_class_group' in data.columns:
            self.n_classes = data['norm_class_group'].nunique()
        else:
            # 如果没有找到norm_class_group，使用class_id
            self.n_classes = data['class_id'].nunique()
            logger.warning("未找到规范化班级ID列，使用原始班级ID计算班级数量")
        
        self.trace = None
        logger.info(f"初始化分析器：{self.n_students}名学生, "
                   f"{self.n_classes}个班级群组, {self.n_schools}所学校")
    
    def _normalize_class_id(self, class_id):
        """标准化班级ID，提取学校和班号，忽略年级和学期变化
        
        例如：将"C02_71_231"转为"C02_1"（学校02的1班）
        
        Args:
            class_id: str 原始班级ID
            
        Returns:
            str 标准化的班级ID
        """
        if not class_id or not isinstance(class_id, str):
            return class_id
        
        try:
            # 解析格式: C02_71_231
            parts = class_id.split('_')
            if len(parts) < 2:
                return class_id
            
            school_code = parts[0]  # 提取"C02"
            grade_class = parts[1]  # 提取"71"
            
            # 只保留班号部分，忽略年级
            class_num = grade_class[1:] if len(grade_class) > 1 else grade_class
            
            # 返回标准化班级ID：学校+班号
            return f"{school_code}_{class_num}"
        except Exception as e:
            logger.warning(f"班级ID标准化失败: {class_id}, 错误: {e}")
            return class_id
    
    def _aggregate_data(self, data):
        """按规范化班级群体聚合数据"""
        logger.info(f"聚合前数据规模：{len(data)}条记录, {data['student_id'].nunique()}名学生")
        
        # 确保使用规范化班级群体ID
        if 'norm_class_group' not in data.columns:
            logger.error("缺少规范化班级群体ID列，无法正确聚合")
            data = self._normalize_class_groups_by_latest_exam(data)
            data = self._further_consolidate_classes(data)
        
        # 检查规范化效果
        original_classes = data['class_id'].nunique()
        norm_classes = data['norm_class_group'].nunique()
        reduction = original_classes - norm_classes
        logger.info(f"聚合前班级规范化效果: 从{original_classes}个减少到{norm_classes}个 (减少{reduction}个，{100*reduction/original_classes:.1f}%)")
        
        # 分析班级跨年级情况，但使用规范化后的班级ID
        classes_across_grades = data.groupby('norm_class_group')['grade_level'].nunique()
        multi_grade_classes = classes_across_grades[classes_across_grades > 1]
        
        if not multi_grade_classes.empty:
            percent = 100 * len(multi_grade_classes) / len(classes_across_grades)
            logger.info(f"跨年级班级数量：{len(multi_grade_classes)}个(占{percent:.1f}%)")
        
        # 按规范化班级群体和学期聚合，确保使用norm_class_group而非class_id
        agg_data = data.groupby(['norm_class_group', 'semester_id']).agg({
            'school_id': 'first',
            'standard_score': 'mean',
            'prior_score': 'mean',
            'grade_level': lambda x: x.mode().iloc[0] if not x.mode().empty else x.iloc[0],
            'class_name': lambda x: x.iloc[0] if 'class_name' in data.columns else None,
            'class_id': 'first',
            'student_id': 'count'
        }).rename(columns={'student_id': 'student_count'}).reset_index()
        
        logger.info(f"按班级群体聚合后数据规模：{len(agg_data)}条记录，{agg_data['norm_class_group'].nunique()}个班级群体")
        
        return agg_data

    def build_hierarchical_model(self):
        """构建贝叶斯多层次模型"""
        logger.info(f"开始构建贝叶斯层级模型...")
        
        # 获取基本数据维度
        n_records = len(self.data)
        n_students = self.data['student_id'].nunique()
        n_classes = self.data['norm_class_group'].nunique()  # 使用规范化班级作为教师代理
        n_schools = self.data['school_id'].nunique()
        
        self._create_numeric_indices()
        
        # 获取数据索引映射
        student_idx = self.data['student_idx'].values
        class_idx = self.data['class_idx'].values  # 班级索引
        school_idx = self.data['school_idx'].values
        
        # 获取模型输入数据 - 确保使用正确的字段名称
        y = self.data['standard_score'].values  # 确保这是标准化成绩
        prior_score = self.data['prior_score'].values  # 先前成绩
        
        logger.info(f"模型数据维度: 记录数={n_records}, 学生数={n_students}, 班级数={n_classes}, 学校数={n_schools}")
        
        # 创建模型
        with pm.Model() as model:
            # 超参数先验
            sigma_s = pm.HalfNormal('sigma_s', sigma=1)
            sigma_c = pm.HalfNormal('sigma_c', sigma=1)
            sigma_e = pm.HalfNormal('sigma_e', sigma=1)
            
            # 固定效应
            intercept = pm.Normal('intercept', mu=0, sigma=5)
            beta_prior = pm.Normal('beta_prior', mu=0.8, sigma=0.2)
            
            # 学校随机效应
            school_effects = pm.Normal('school_effects', mu=0, sigma=sigma_s, shape=n_schools)
            
            # 班级随机效应
            class_effects = pm.Normal('class_effects', mu=0, sigma=sigma_c, shape=n_classes)
            
            # 组合效应
            mu = (intercept + beta_prior * prior_score + 
                  school_effects[school_idx] + class_effects[class_idx])
            
            # 观测值
            y_obs = pm.Normal('y_obs', mu=mu, sigma=sigma_e, observed=y)
        
        logger.info("贝叶斯层级模型构建完成")
        return model

    def run_analysis(self, confidence=0.95, return_posteriors=False, use_class_model=True, 
                    samples=5000, tune=500, cores=2, ceiling_adjust=False):
        """
        运行增值分析
        
        Args:
            confidence: float 置信区间水平
            return_posteriors: bool 是否返回后验分布
            use_class_model: bool 是否使用班级模型
            samples: int MCMC采样数
            tune: int MCMC调优样本数
            cores: int 使用的核心数
            ceiling_adjust: bool 是否启用天花板效应调整
        """
        # 显示PyTensor配置信息
        logger.info(f"PyTensor配置: {pytensor.config.cxx}")
        logger.info(f"编译器状态: {'可用' if pytensor.config.cxx else '不可用'}")
        
        # 首先分析并显示所有学校信息
        logger.info("======= 分析所有学校信息 =======")
        
        # 显示学校信息
        schools = set()
        school_names = {}
        
        for school_id in self.data['school_id'].unique():
            schools.add(school_id)
            if 'school_name' in self.data.columns:
                school_names[school_id] = self.data[self.data['school_id'] == school_id]['school_name'].iloc[0]
            else:
                school_names[school_id] = f"学校{school_id}"
        
        logger.info(f"共发现{len(schools)}所不同学校:")
        for school_id in sorted(schools):
            logger.info(f"学校ID: {school_id}, 名称: {school_names.get(school_id, '未知')}")
        
        # 剔除小规模学校
        logger.info("======= 剔除小规模学校 =======")
        school_student_counts = self.data.groupby('school_id')['student_id'].nunique()
        small_schools = school_student_counts[school_student_counts < 10]
        
        if not small_schools.empty:
            for school_id in small_schools.index:
                logger.warning(f"移除小规模学校: {school_id}, 仅有{small_schools[school_id]}名学生")
            
            self.data = self.data[~self.data['school_id'].isin(small_schools.index)]
            logger.info(f"移除后剩余{self.data['school_id'].nunique()}所学校")
        else:
            logger.info("没有发现学生数量少于10人的学校")
        
        # 学校详细分析
        self.analyze_school_data()
        
        # 构建贝叶斯层级模型
        logger.info("======= 构建贝叶斯层级模型 =======")
        if ceiling_adjust:
            logger.info("启用天花板效应调整模型")
            model = self.build_hierarchical_model_ceiling_adjusted()
        else:
            model = self.build_hierarchical_model()
        
        # 运行MCMC采样 - 修改这里，设置return_inferencedata=False
        logger.info(f"======= 运行MCMC采样 (samples={samples}) =======")
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=UserWarning)
                with model:
                    # 使用NUTS采样器进行MCMC采样，添加优化参数
                    trace = pm.sample(
                        draws=samples,
                        tune=tune,
                        chains=1,
                        cores=cores,
                        return_inferencedata=False,  # 改为返回传统的MultiTrace对象
                        target_accept=0.9,
                        init='adapt_diag',
                        progressbar=True
                    )
        except Exception as e:
            logger.error(f"MCMC采样失败: {str(e)}")
            raise ValueError(f"模型采样失败: {str(e)}")
        
        # 保存模型和采样结果
        self.model = model
        self.trace = trace
        
        # 计算增值效应
        logger.info("======= 计算增值效应 =======")
        results = self.calculate_value_added()
        
        # 直接返回calculate_value_added的结果，而不是重新打包
        return results  # 这样会返回包含'schools', 'classes', 'students'键的字典

    def calculate_value_added(self):
        """计算增值效应"""
        if self.trace is None:
            raise ValueError("必须先运行分析才能计算增值")
    
        try:
            # 检查trace对象类型并相应处理
            if hasattr(self.trace, 'posterior'):  # InferenceData对象
                trace_vars = list(self.trace.posterior.data_vars)
                
                # 提取后验分布均值 - 适用于InferenceData
                school_effects = self.trace.posterior.school_effects.mean(dim=["chain", "draw"]).values
                class_effects = self.trace.posterior.class_effects.mean(dim=["chain", "draw"]).values
            else:  # 传统MultiTrace对象
                trace_vars = self.trace.varnames
                
                # 提取后验分布均值 - 适用于MultiTrace
                school_effects = self.trace['school_effects'].mean(axis=0)
                class_effects = self.trace['class_effects'].mean(axis=0)
            
            logger.info(f"可用变量: {trace_vars}")
            
            # 创建映射字典
            school_id_list = sorted(self.data['school_id'].unique())
            class_id_list = sorted(self.data['norm_class_group'].unique())
            
            # 创建结果数据框
            schools_df = pd.DataFrame({
                'school_id': school_id_list,
                'value_added': school_effects
            })
            
            classes_df = pd.DataFrame({
                'class_id': class_id_list,
                'value_added': class_effects,
                'school_id': [self.data[self.data['norm_class_group']==c]['school_id'].iloc[0] 
                             for c in class_id_list]
            })
            
            # 学生的增值基于班级增值
            student_df = pd.DataFrame()
            if not self.data.empty:
                students = self.data[['student_id', 'norm_class_group']].drop_duplicates()
                students = students.merge(
                    classes_df[['class_id', 'value_added']],
                    left_on='norm_class_group',
                    right_on='class_id',
                    how='left'
                )
                student_df = students[['student_id', 'value_added']]
            
            logger.info(f"计算得到{len(schools_df)}所学校和{len(classes_df)}个班级的增值效应")
            
            return {
                'schools': schools_df,
                'classes': classes_df,
                'students': student_df
            }
        except Exception as e:
            logger.error(f"计算增值效应时出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            raise

    def _validate_data(self, df):
        """验证数据完整性"""
        required = {'student_id', 'teacher_id', 'school_id', 't_score', 'time_point'}
        if not required.issubset(df.columns):
            missing = required - set(df.columns)
            raise ValueError(f"缺失必要字段：{missing}")
        
        if df['time_point'].nunique() < 2:
            raise ValueError("至少需要两个时间点的数据")

    def generate_diagnostic_report(self, output_dir):
        """生成模型诊断报告"""
        if self.model is None or self.trace is None:
            raise ValueError("请先运行分析再生成报告")
            
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 将MultiTrace转换为InferenceData以兼容ArviZ可视化
        try:
            import arviz as az
            # 检查trace类型并转换
            if not hasattr(self.trace, 'posterior'):
                # 转换MultiTrace为InferenceData - 使用新版API
                idata = az.from_pymc(trace=self.trace, model=self.model)
            else:
                idata = self.trace
                
            # 使用ArviZ的可视化函数
            az.plot_forest(idata, var_names=['sigma_s', 'sigma_c', 'sigma_e']).savefig(output_dir / 'hyper_params.png')
            az.plot_posterior(idata, var_names=['intercept', 'beta_prior']).savefig(output_dir / 'fixed_effects.png')
            az.plot_trace(idata, var_names=['sigma_s', 'sigma_c', 'sigma_e', 'intercept', 'beta_prior']).savefig(output_dir / 'convergence.png')
            
            # 保存效应分布图
            school_sample = min(20, len(self.data['school_id'].unique()))
            az.plot_forest(idata, var_names=['school_effects'][:school_sample]).savefig(output_dir / 'school_effects.png')
            
            class_sample = min(20, len(self.data['norm_class_group'].unique()))
            az.plot_forest(idata, var_names=['class_effects'][:class_sample]).savefig(output_dir / 'class_effects.png')
            
            logger.info(f"诊断报告已保存到: {output_dir}")
            
        except Exception as e:
            logger.error(f"生成诊断报告时出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())

    def build_class_level_model(self):
        """使用优化的班级群体ID构建模型"""
        df = self.agg_data
        
        # 如果数据量太大，随机抽样
        if len(df) > 500:
            logger.warning(f"数据量过大({len(df)}条)，随机抽样到500条以提高性能")
            df = df.sample(n=500, random_state=42)
        
        # 确保使用规范化班级ID
        if 'norm_class_group' not in df.columns:
            logger.error("模型构建缺少规范化班级ID列，结果将不准确")
        
        # 重新计算索引映射
        logger.info("重新计算索引映射")
        # 使用规范化班级群体ID
        df['class_code'] = pd.factorize(df['norm_class_group'])[0]
        df['school_code'] = pd.factorize(df['school_id'])[0]
        
        # 年级级别转换为数值
        try:
            # 将年级转换为数值
            df['grade_num'] = pd.to_numeric(df['grade_level'], errors='coerce')
            df['grade_num'] = df['grade_num'].fillna(0)  # 处理转换失败的情况
            
            # 记录日志
            logger.info(f"年级分布: {df['grade_num'].value_counts().to_dict()}")
        except Exception as e:
            logger.warning(f"年级转换为数值失败: {e}")
            df['grade_num'] = 0
        
        # 记录映射规模
        n_classes = df['class_code'].nunique()
        n_schools = df['school_code'].nunique()
        
        logger.info(f"抽样后模型规模: {n_classes}个班级, {n_schools}所学校")
        
        # 获取索引和数据 - 将所有要用于PyMC的数据转换为NumPy数组
        class_codes = df['class_code'].values
        school_codes = df['school_code'].values
        scores = df['standard_score'].values
        prior_scores = df['prior_score'].values
        grade_nums = df['grade_num'].values  # 使用提前准备好的NumPy数组
        
        # 如果有班级学生数据，使用它进行加权
        if 'student_count' in df.columns:
            student_counts = df['student_count'].values
        else:
            # 如果没有，使用单位权重
            logger.warning("没有班级学生数量数据，使用单位权重")
            student_counts = np.ones_like(scores)
        
        # 构建模型
        with pm.Model() as model:
            # 全局参数
            global_mean = pm.Normal('global_mean', mu=500, sigma=50)
            
            # 学校效应
            school_sigma = pm.HalfNormal('school_sigma', sigma=20)
            school_effect = pm.Normal('school_effect', mu=0, sigma=school_sigma, shape=n_schools)
            
            # 班级效应(嵌套在学校中)
            class_sigma = pm.HalfNormal('class_sigma', sigma=15)
            class_effect = pm.Normal('class_effect', mu=0, sigma=class_sigma, shape=n_classes)
            
            # 年级效应 - 学生随年级增长的普遍变化
            grade_effect = pm.Normal('grade_effect', mu=0, sigma=10)
            
            # 先前成绩效应
            prior_effect = pm.Normal('prior_effect', mu=0.8, sigma=0.05)
            
            # 加权分析（使用班级人数）
            weight = pm.math.sqrt(student_counts / student_counts.mean())
            
            # 预测值 - 使用提前准备好的NumPy数组
            mu = (global_mean + 
                   school_effect[school_codes] + 
                   class_effect[class_codes] + 
                   grade_effect * grade_nums +  # 使用NumPy数组而不是Pandas Series
                   prior_effect * (prior_scores - 500))
            
            # 观测误差，考虑班级规模（大班级更稳定）
            sigma_base = pm.HalfNormal('sigma_base', sigma=30)
            sigma = sigma_base / weight
            
            # 观测值
            y = pm.Normal('y', mu=mu, sigma=sigma, observed=scores)
        
        return model

    def _extract_value_added(self):
        """提取并解释增值效果"""
        trace = self.trace
        agg_df = self.agg_data
        
        # 提取班级效应
        class_effects = pm.summary(trace, var_names=['class_effect'])
        class_va = class_effects['mean'].values
        
        # 提取学校效应
        school_effects = pm.summary(trace, var_names=['school_effect'])
        school_va = school_effects['mean'].values
        
        # 标准化为50分制
        class_va_std = 50 + 10 * (class_va - class_va.mean()) / class_va.std()
        school_va_std = 50 + 10 * (school_va - school_va.mean()) / school_va.std()
        
        # 创建班级增值结果
        class_df = agg_df.drop_duplicates('norm_class_group').copy()
        class_results = pd.DataFrame({
            'class_id': class_df['class_id'].values,
            'class_name': class_df['class_name'].values,
            'school_id': class_df['school_id'].values,
            'norm_class_group': class_df['norm_class_group'].values,
            'value_added': class_va_std,
            'student_count': agg_df.groupby('norm_class_group')['student_count'].sum().values,
            'grade_levels': agg_df.groupby('norm_class_group')['grade_level'].nunique().values
        })
        
        # 创建学校增值结果
        school_df = agg_df.drop_duplicates('school_id').copy()
        school_results = pd.DataFrame({
            'school_id': school_df['school_id'].values,
            'school_code': school_df['school_code'].values,
            'value_added': school_va_std,
            'student_count': agg_df.groupby('school_id')['student_count'].sum().values,
            'class_count': agg_df.groupby('school_id')['norm_class_group'].nunique().values
        })
        
        # 添加评级
        class_results['rating'] = self._get_rating(class_results['value_added'])
        school_results['rating'] = self._get_rating(school_results['value_added'])
        
        # 添加班级跨年级信息
        class_results['is_multi_grade'] = class_results['grade_levels'] > 1
        class_results['grade_span'] = class_results['grade_levels'].apply(
            lambda x: f"{x}个年级" if x > 1 else "单一年级"
        )
        
        logger.info(f"班级增值结果: {len(class_results)}个班级")
        logger.info(f"其中跨年级班级: {class_results['is_multi_grade'].sum()}个")
        
        return {
            'classes': class_results,
            'schools': school_results
        }

    def _get_rating(self, scores):
        """将分数转换为评级"""
        ratings = []
        for score in scores:
            if score >= 70:
                ratings.append('A+')
            elif score >= 60:
                ratings.append('A')
            elif score >= 55:
                ratings.append('B+')
            elif score >= 50:
                ratings.append('B')
            elif score >= 45:
                ratings.append('C+')
            elif score >= 40:
                ratings.append('C')
            elif score >= 30:
                ratings.append('D')
            else:
                ratings.append('D-')
        return ratings

    def _fallback_analysis(self):
        """当贝叶斯分析失败时的备选方案（移除教师层级）"""
        logger.info("执行备选分析方案")
        
        # 简单的回归分析
        import statsmodels.api as sm
        
        df = self.agg_data
        # 添加常数项
        df['const'] = 1
        
        # 简单回归模型
        X = df[['const', 'prior_score']]
        y = df['standard_score']
        
        # 拟合模型
        model = sm.OLS(y, X).fit()
        
        # 计算残差作为增值
        df['predicted'] = model.predict(X)
        df['value_added'] = df['standard_score'] - df['predicted']
        
        # 标准化增值分数
        mean_va = df['value_added'].mean()
        std_va = df['value_added'].std()
        df['value_added_normalized'] = 50 + 10 * (df['value_added'] - mean_va) / std_va
        
        # 按班级和学校聚合
        class_results = df.groupby('norm_class_group').agg({
            'class_id': 'first',
            'school_id': 'first',
            'class_name': 'first',
            'value_added_normalized': 'mean',
            'student_count': 'sum'
        }).reset_index()
        
        school_results = df.groupby('school_id').agg({
            'value_added_normalized': 'mean',
            'student_count': 'sum'
        }).reset_index()
        
        # 返回简单结果
        return {
            'classes': class_results,
            'schools': school_results,
            'is_fallback': True  # 标记为备选方案结果
        }

    def analyze_school_data(self):
        """分析学校数据，识别潜在的重复学校ID"""
        logger.info("执行详细学校数据分析...")
        
        # 从数据中提取学校信息
        school_data = self.data[['school_id', 'semester_id']].drop_duplicates()
        
        # 按学期统计学校数量
        semester_schools = school_data.groupby('semester_id')['school_id'].nunique()
        logger.info(f"各学期学校数量: {semester_schools.to_dict()}")
        
        # 学校ID在学期间的变化
        school_semester_counts = school_data.groupby('school_id')['semester_id'].nunique()
        if (school_semester_counts < len(semester_schools.index)).any():
            logger.warning("以下学校不在所有学期中出现:")
            for school_id, count in school_semester_counts[school_semester_counts < len(semester_schools.index)].items():
                semesters = school_data[school_data['school_id'] == school_id]['semester_id'].unique()
                logger.warning(f"  学校ID: {school_id}, 出现学期数: {count}, 学期: {semesters}")
        
        # 分析班级ID格式获取学校信息
        class_school_map = {}
        if 'class_id' in self.data.columns:
            for class_id in self.data['class_id'].unique():
                if isinstance(class_id, str) and class_id.startswith('C') and '_' in class_id:
                    school_code = class_id.split('_')[0].replace('C', '')
                    if school_code not in class_school_map:
                        class_school_map[school_code] = set()
                    # 获取对应的学校ID
                    matching_schools = self.data[self.data['class_id'] == class_id]['school_id'].unique()
                    class_school_map[school_code].update(matching_schools)
        
        # 打印班级ID与学校ID的映射关系
        for school_code, school_ids in class_school_map.items():
            if len(school_ids) > 1:
                logger.warning(f"班级代码'{school_code}'对应多个学校ID: {school_ids}")
        
        return {
            'semester_schools': semester_schools.to_dict(),
            'school_semesters': school_semester_counts.to_dict(),
            'class_school_map': class_school_map
        }

    def process_data_hierarchically(self):
        """层级化数据处理流程：自上而下处理学校-班级-学生"""
        logger.info("===== 开始层级化数据处理 =====")
        
        # 1. 学校层级处理
        logger.info("第一步：学校层级处理")
        
        # 1.1 收集和展示学校信息
        school_info = {}
        for school_id in self.data['school_id'].unique():
            school_name = "未知"
            if 'school_name' in self.data.columns:
                school_names = self.data[self.data['school_id'] == school_id]['school_name'].unique()
                if len(school_names) > 0:
                    school_name = school_names[0]
            school_info[school_id] = school_name
        
        logger.info(f"数据中包含{len(school_info)}所学校:")
        for school_id, name in sorted(school_info.items()):
            logger.info(f"学校ID: {school_id}, 名称: {name}")
        
        # 1.2 剔除小规模学校(学生少于10人)
        school_student_counts = self.data.groupby('school_id')['student_id'].nunique()
        small_schools = school_student_counts[school_student_counts < 10]
        
        if not small_schools.empty:
            logger.warning(f"发现{len(small_schools)}所小规模学校(学生<10人)，进行移除")
            for school_id in small_schools.index:
                logger.warning(f"移除学校: {school_id} ({school_info.get(school_id,'未知')}), 学生数:{small_schools[school_id]}")
            
            original_count = len(self.data)
            self.data = self.data[~self.data['school_id'].isin(small_schools.index)]
            logger.info(f"移除小规模学校后，数据减少{original_count-len(self.data)}条")
        
        # 1.3 处理不在所有学期出现的学校
        school_analysis = self.analyze_school_data()
        semester_count = self.data['semester_id'].nunique()
        
        school_semester_counts = self.data.groupby('school_id')['semester_id'].nunique()
        incomplete_schools = school_semester_counts[school_semester_counts < semester_count]
        
        if not incomplete_schools.empty:
            logger.warning(f"发现{len(incomplete_schools)}所学校未出现在所有{semester_count}个学期中")
            for school_id in incomplete_schools.index:
                semesters = self.data[self.data['school_id'] == school_id]['semester_id'].unique()
                logger.warning(f"移除学校: {school_id} ({school_info.get(school_id,'未知')}), "
                              f"仅出现在{len(semesters)}/{semester_count}个学期")
            
            original_count = len(self.data)
            self.data = self.data[~self.data['school_id'].isin(incomplete_schools.index)]
            logger.info(f"移除不完整学期的学校后，数据减少{original_count-len(self.data)}条")
        
        # 2. 班级层级处理
        logger.info("\n第二步：班级层级处理")
        
        # 2.1 只针对保留的学校数据进行班级规范化
        logger.info("对保留的学校数据进行班级规范化")
        # 实施班级规范化（例如_normalize_class_groups_by_latest_exam和_further_consolidate_classes）
        self.data = self._normalize_class_groups_by_latest_exam(self.data)
        self.data = self._further_consolidate_classes(self.data)
        
        # 2.2 分析规范化后的班级信息
        class_counts = self.data['norm_class_group'].nunique()
        logger.info(f"规范化后班级数量: {class_counts}个班级")
        
        # 2.3 移除小规模班级
        class_student_counts = self.data.groupby('norm_class_group')['student_id'].nunique()
        small_classes = class_student_counts[class_student_counts < 10]
        
        if not small_classes.empty:
            logger.warning(f"发现{len(small_classes)}个小规模班级(学生<10人)，进行移除")
            for class_id in small_classes.index:
                logger.warning(f"移除班级: {class_id}, 学生数:{small_classes[class_id]}")
            
            original_count = len(self.data)
            self.data = self.data[~self.data['norm_class_group'].isin(small_classes.index)]
            logger.info(f"移除小规模班级后，数据减少{original_count-len(self.data)}条")
            logger.info(f"最终剩余{self.data['norm_class_group'].nunique()}个班级，{self.data['student_id'].nunique()}名学生")
        
        # 3. 学生层级处理和数据准备
        logger.info("\n第三步：学生层级处理和数据准备")
        # 可以添加学生层级的处理，如异常值检测等
        
        logger.info(f"层级化处理完成，最终数据包含: {self.data['school_id'].nunique()}所学校，"
                    f"{self.data['norm_class_group'].nunique()}个班级，{self.data['student_id'].nunique()}名学生")
        return self.data

    def build_hierarchical_model_ceiling_adjusted(self):
        """构建考虑天花板效应的贝叶斯层级模型"""
        
        # 首先创建数值索引
        self._create_numeric_indices()
        
        # 获取数据维度
        n_records = len(self.data)
        n_students = self.data['student_id'].nunique()
        n_classes = self.data['norm_class_group'].nunique()
        n_schools = len(self.data['school_id'].unique())
        
        # 提取数据向量
        y = self.data['standard_score'].values
        prior_score = self.data['prior_score'].values
        student_idx = self.data['student_idx'].values
        class_idx = self.data['class_idx'].values
        school_idx = self.data['school_idx'].values
        
        # 计算最大可能分数和接近极限分数的学生比例
        max_score = self.data['standard_score'].max()
        near_ceiling = np.mean(self.data['prior_score'] > (max_score * 0.9))
        logger.info(f"接近满分学生比例: {near_ceiling:.2%}")
        
        # 创建模型
        with pm.Model() as model:
            # 超参数先验
            sigma_s = pm.HalfNormal('sigma_s', sigma=1)
            sigma_c = pm.HalfNormal('sigma_c', sigma=1)
            sigma_e = pm.HalfNormal('sigma_e', sigma=1)
            
            # 固定效应
            intercept = pm.Normal('intercept', mu=0, sigma=5)
            
            # 非线性项 - 处理天花板效应
            beta_prior = pm.Normal('beta_prior', mu=0.8, sigma=0.2)
            beta_prior_sq = pm.Normal('beta_prior_sq', mu=-0.1, sigma=0.1)  # 二次项，捕捉非线性关系
            
            # 学校和班级随机效应
            school_effects = pm.Normal('school_effects', mu=0, sigma=sigma_s, shape=n_schools)
            class_effects = pm.Normal('class_effects', mu=0, sigma=sigma_c, shape=n_classes)
            
            # 非线性组合效应
            # 加入二次项以捕捉高分段的非线性关系
            mu_linear = (intercept + beta_prior * prior_score + 
                        beta_prior_sq * (prior_score**2) + 
                        school_effects[school_idx] + class_effects[class_idx])
            
            # 使用转换函数处理极端值的异方差性
            # 高分学生的方差往往更小
            variance_factor = pm.math.switch(prior_score > (max_score * 0.8), 
                                          0.5 * sigma_e,  # 高分学生方差减半
                                          sigma_e)        # 其他学生正常方差
            
            # 观测值
            y_obs = pm.Normal('y_obs', mu=mu_linear, sigma=variance_factor, observed=y)
        
        return model

    def _create_numeric_indices(self):
        """创建模型所需的数值索引映射"""
        if 'student_idx' not in self.data.columns:
            # 创建学生索引映射
            student_ids = self.data['student_id'].unique()
            student_id_to_idx = {id: idx for idx, id in enumerate(student_ids)}
            self.data['student_idx'] = self.data['student_id'].map(student_id_to_idx)
        
        if 'class_idx' not in self.data.columns:
            # 创建班级索引映射
            class_ids = self.data['norm_class_group'].unique()
            class_id_to_idx = {id: idx for idx, id in enumerate(class_ids)}
            self.data['class_idx'] = self.data['norm_class_group'].map(class_id_to_idx)
        
        if 'school_idx' not in self.data.columns:
            # 创建学校索引映射
            school_ids = self.data['school_id'].unique()
            school_id_to_idx = {id: idx for idx, id in enumerate(school_ids)}
            self.data['school_idx'] = self.data['school_id'].map(school_id_to_idx)
        
        return self.data

class Command(BaseCommand):
    """增值分析管理命令"""
    
    help = "执行贝叶斯教育增值分析"
    
    def add_arguments(self, parser):
        parser.add_argument('-s', '--subject',
                          help='指定学科ID进行分析，如"MATH"、"PHYSICS"等')
        parser.add_argument('-e', '--exam',
                          help='指定考试ID，如"EXAM2023-1,EXAM2023-2"，多个ID用逗号分隔')
        parser.add_argument('-r', '--semester-range', type=int, default=3,
                          help='分析的学期范围数量，默认为3个学期')
        parser.add_argument('-o', '--output', type=Path,
                          default=settings.BASE_DIR / 'results' / 'value_added')
        parser.add_argument('--samples', type=int, default=5000,
                          help='MCMC采样次数，增加可提高精度但会降低速度')
        parser.add_argument('--save-db', action='store_true',
                          help='将结果保存到数据库')
        parser.add_argument('--excel', action='store_true',
                          help='导出结果到Excel文件')
        parser.add_argument(
                            '--ceiling-adjust',
                            action='store_true',
                            help='启用天花板效应校正（适用于高分群体评价）'
        )
                          
    def handle(self, *args, **options):
        try:
            subject_id = options.get('subject')
            exam_ids = None
            if options.get('exam'):
                exam_ids = [e.strip() for e in options['exam'].split(',')]
            
            if subject_id:
                self.stdout.write(f"开始分析学科ID: {subject_id}")
            else:
                self.stdout.write("开始全学科教育增值分析...")
            
            if exam_ids:
                self.stdout.write(f"指定考试ID: {', '.join(exam_ids)}")
            
            # 创建数据处理器时传递exam_ids参数
            processor = ValueAddedDataProcessor(
                subject_id=options['subject'],
                semester_range=options['semester_range'],
                exam_ids=exam_ids  # 传递考试ID参数
            )
            
            # 处理数据
            data, mappings = processor.process()
            
            # 初始化分析器并设置数据 - 使用处理后的数据和映射
            analyzer = ValueAddedAnalyzer(
                data,  # 直接使用process()返回的数据
                mappings=mappings  # 直接使用process()返回的映射
            )
            
            # 运行分析，添加天花板效应调整参数
            results = analyzer.run_analysis(
                samples=options['samples'],
                ceiling_adjust=options.get('ceiling_adjust', False)  # 新增参数
            )
            
            # 保存结果
            output_dir = options['output']
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # 修正这部分，确保使用正确的键名
            for entity_name, df in results.items():
                if isinstance(df, pd.DataFrame) and not df.empty:
                    df_path = output_dir / f"{entity_name}_effects.csv"
                    df.to_csv(df_path, index=False)
                    self.stdout.write(f"已保存{entity_name}增值结果到: {df_path}")
                else:
                    self.stdout.write(f"警告: {entity_name}增值结果为空")
            
            # 生成诊断报告
            self.stdout.write("正在生成诊断报告...")
            analyzer.generate_diagnostic_report(output_dir)
            
            # 是否保存结果到数据库
            if options['save_db']:
                self.stdout.write("正在将结果保存到数据库...")
                self._save_to_database(results, subject_id, mappings)
            
            # 导出到Excel
            if options['excel']:
                self.stdout.write("正在导出结果到Excel...")
                excel_path = self._export_to_excel(results, data, output_dir, subject_id, mappings)
                self.stdout.write(f"Excel报告已保存至: {excel_path}")
            
            self.stdout.write(self.style.SUCCESS(f"分析完成！结果保存在：{output_dir}"))
            
        except Exception as e:
            logger.exception("教育增值分析失败")
            self.stderr.write(self.style.ERROR(f"执行失败: {str(e)}"))
            
    @transaction.atomic
    def _save_to_database(self, results, subject_id, mappings):
        """将结果保存到数据库"""
        current_semester = Semester.objects.filter(status='ACTIVE').latest('end_date')
        
        # 如果未指定学科，使用所有学科数据
        subjects = []
        if subject_id:
            subjects = [Subject.objects.get(subject_id=subject_id)]
        else:
            subjects = Subject.objects.filter(status='ACTIVE')
            
        for subject in subjects:
            # 保存学生增值
            for _, row in results['students'].iterrows():
                eval_id = f"VA-S-{uuid.uuid4().hex[:8]}"
                ValueAddedEvaluation.objects.create(
                    eval_id=eval_id,
                    target_type='STUDENT',
                    target_id=row['student_id'],
                    subject=subject,
                    semester=current_semester,
                    base_score=0,  # 需根据实际情况填充
                    current_score=0,  # 需根据实际情况填充
                    added_value=float(row['value_added'] * 100),  # 缩放到实际分数范围
                    factors={
                        'method': 'bayesian_hlm',
                        'score_range': [200, 800],
                        'model_params': {
                            'time_points': 2,
                            'prior_weight': 0.5
                        }
                    },
                    status='PUBLISHED'
                )
                
            # 保存学校增值
            for _, row in results['schools'].iterrows():
                eval_id = f"VA-SC-{uuid.uuid4().hex[:8]}"
                ValueAddedEvaluation.objects.create(
                    eval_id=eval_id,
                    target_type='SCHOOL',
                    target_id=row['school_id'],
                    subject=subject,
                    semester=current_semester,
                    base_score=0,
                    current_score=0,
                    added_value=float(row['value_added'] * 100),
                    factors={
                        'method': 'bayesian_hlm',
                        'score_range': [200, 800],
                        'model_params': {
                            'teachers_count': 0,
                            'students_count': results['students']['student_id'].nunique()
                        }
                    },
                    status='PUBLISHED'
                ) 

    def _export_to_excel(self, results, raw_data, output_dir, subject_id=None, mappings=None):
        """将结果导出为Excel格式"""
        subject_name = "全学科" if not subject_id else Subject.objects.get(subject_id=subject_id).subject_name
        current_semester = Semester.objects.filter(status='ACTIVE').latest('end_date')
        
        # 创建输出文件名
        file_name = f"增值分析报告_{subject_name}_{current_semester.year}{current_semester.term}.xlsx"
        excel_path = output_dir / file_name
        
        # 准备数据
        student_results = results['students'].copy()
        school_results = results['schools'].copy()
        class_results = results.get('classes', pd.DataFrame()).copy()
        
        # 添加名称映射
        if mappings:
            # 添加学校名称
            if 'schools' in mappings and not school_results.empty:
                school_results['学校名称'] = school_results['school_id'].map(
                    lambda x: mappings['schools'].get(x, "未知")
                )
            
            # 添加学生姓名
            if 'students' in mappings and not student_results.empty:
                student_results['学生姓名'] = student_results['student_id'].map(
                    lambda x: mappings['students'].get(x, "未知")
                )
        
        # 获取学生到班级和学校的映射关系
        student_to_class_school = raw_data[['student_id', 'norm_class_group', 'school_id']].drop_duplicates('student_id')
        
        # 班级增加名称标识
        class_mapping = {}
        if not raw_data.empty:
            class_info = raw_data[['norm_class_group', 'school_id', 'class_name']].drop_duplicates('norm_class_group')
            for _, row in class_info.iterrows():
                class_id = row['norm_class_group']
                school_id = row['school_id']
                class_name = row.get('class_name', f"班级{class_id}")
                class_mapping[class_id] = class_name
        
        # 班级添加具体班级名称
        if not class_results.empty:
            class_results['班级名称'] = class_results['class_id'].map(lambda x: class_mapping.get(x, f"班级{x}"))
        
        # 添加学校班级关联到学生数据
        if not student_results.empty:
            # 关联班级信息
            student_results = student_results.merge(
                student_to_class_school,
                on='student_id',
                how='left'
            )
            
            # 关联班级名称
            student_results['班级名称'] = student_results['norm_class_group'].map(
                lambda x: class_mapping.get(x, f"班级{x}") if pd.notna(x) else "未知"
            )
            
            # 关联学校名称
            if 'schools' in mappings:
                student_results['学校名称'] = student_results['school_id'].map(
                    lambda x: mappings['schools'].get(x, "未知") if pd.notna(x) else "未知"
                )
        
        # 标准化增值分数 - 使用百分位数方法替代固定公式
        for df_name, df in [('schools', school_results), ('classes', class_results), ('students', student_results)]:
            if not df.empty:
                # 计算z分数
                df['z_score'] = (df['value_added'] - df['value_added'].mean()) / df['value_added'].std()
                
                # 计算百分位数
                df['percentile'] = df['value_added'].rank(pct=True) * 100
                
                # 基于百分位数的标准化分数 (0-100)
                df['增值得分'] = df['percentile']
                
                # 更合理的评级分配 - 基于百分位数
                df['增值评级'] = df['percentile'].apply(
                    lambda x: 'A+' if x >= 90 else     # 前10%
                             ('A' if x >= 75 else      # 前25%
                             ('B' if x >= 50 else      # 中间水平
                             ('C' if x >= 25 else      # 后25%
                             ('D' if x >= 10 else 'D-')))) # 后10%
                )
                
                logger.info(f"{df_name}增值评价分布: " + 
                           f"A+={len(df[df['增值评级']=='A+'])}，" +
                           f"A={len(df[df['增值评级']=='A'])}，" +
                           f"B={len(df[df['增值评级']=='B'])}，" +
                           f"C={len(df[df['增值评级']=='C'])}，" +
                           f"D={len(df[df['增值评级']=='D'])}，" +
                           f"D-={len(df[df['增值评级']=='D-'])}")
        
        # 创建Excel写入器
        with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
            # 写入概述页
            self._write_summary_sheet(writer, raw_data, results, subject_name, current_semester)
            
            # 写入学校增值页
            if not school_results.empty:
                cols = ['school_id', '学校名称', '增值得分', '增值评级']
                school_results[cols].rename(columns={'school_id': '学校ID'}).to_excel(
                    writer, sheet_name='学校增值', index=False
                )
                self._format_sheet(writer.sheets['学校增值'])
                self._add_chart(writer, '学校增值', '学校名称', '增值得分', '学校增值效果分析')
            
            # 写入班级增值页
            if not class_results.empty:
                # 添加学校名称到班级数据
                if not school_results.empty and 'schools' in mappings:
                    class_results['学校名称'] = class_results['school_id'].map(
                        lambda x: mappings['schools'].get(x, "未知")
                    )
                else:
                    class_results['学校名称'] = "未知"
                
                cols = ['class_id', '班级名称', '学校名称', '增值得分', '增值评级']
                class_results[cols].rename(columns={'class_id': '班级ID'}).to_excel(
                    writer, sheet_name='班级增值', index=False
                )
                self._format_sheet(writer.sheets['班级增值'])
                self._add_chart(writer, '班级增值', '班级名称', '增值得分', '班级增值分析')
            
            # 写入学生增值页
            if not student_results.empty:
                cols = ['student_id', '学生姓名', '班级名称', '学校名称', '增值得分', '增值评级']
                student_results[cols].rename(columns={'student_id': '学生ID'}).to_excel(
                    writer, sheet_name='学生增值', index=False
                )
                self._format_sheet(writer.sheets['学生增值'])
                
            # 写入技术参数页
            self._write_technical_sheet(writer, raw_data)
            
        return excel_path
    
    def _write_summary_sheet(self, writer, raw_data, results, subject_name, semester):
        """写入概述页"""
        summary_df = pd.DataFrame([
            ['分析报告类型', '教育增值分析(贝叶斯多层线性模型)'],
            ['分析学科', subject_name],
            ['分析学期', f"{semester.year}学年第{semester.term}学期"],
            ['数据规模', f"{len(raw_data)}条成绩记录"],
            ['学生数量', f"{raw_data['student_id'].nunique()}名"],
            ['学校数量', f"{raw_data['school_id'].nunique()}所"],
            ['分析日期', pd.Timestamp.now().strftime('%Y-%m-%d')],
            ['模型类型', '三层贝叶斯层次线性模型(BayesHLM)'],
            ['', ''],
            ['结果摘要', ''],
            ['学校平均增值', f"{results['schools']['value_added'].mean():.4f}"],
            ['班级平均增值', f"{results['classes']['value_added'].mean():.4f}"],
            ['学生平均增值', f"{results['students']['value_added'].mean():.4f}"],
        ])
        
        summary_df.columns = ['指标', '数值']
        summary_df.to_excel(writer, sheet_name='概述', index=False)
        
        # 格式化概述页
        sheet = writer.sheets['概述']
        sheet.column_dimensions['A'].width = 20
        sheet.column_dimensions['B'].width = 50
        
        # 设置标题样式
        title_fill = PatternFill(start_color="DDEBF7", end_color="DDEBF7", fill_type="solid")
        for row in range(1, 12):
            sheet.cell(row=row, column=1).fill = title_fill
            
        # 设置结果摘要样式
        summary_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
        for row in range(12, 16):
            sheet.cell(row=row, column=1).fill = summary_fill
            sheet.cell(row=row, column=2).alignment = Alignment(horizontal='center')
    
    def _write_technical_sheet(self, writer, raw_data):
        """写入技术参数页"""
        tech_df = pd.DataFrame([
            ['参数名称', '参数值', '说明'],
            ['模型类型', 'BayesianHLM', '贝叶斯多层线性模型'],
            ['先验设置', 'Normal(0,10)', '参数先验分布'],
            ['MCMC采样', '5000', 'MCMC采样次数'],
            ['调优步数', '2000', '模型调优步数'],
            ['学生层随机效应', '是', '学生个体差异建模'],
            ['学校层随机效应', '是', '学校环境效应建模'],
            ['分数类型', 'T分数', '标准分(均值500,标准差100)'],
            ['增值计算方法', '时间斜率', '学生成绩随时间变化率'],
            ['归一化方法', 'Z分转50分制', '中心化为50分,分布在0-100']
        ])
        tech_df.columns = tech_df.iloc[0]
        tech_df = tech_df.iloc[1:]
        tech_df.to_excel(writer, sheet_name='技术参数', index=False)
        self._format_sheet(writer.sheets['技术参数'])
        
    def _format_sheet(self, sheet):
        """格式化工作表样式"""
        # 设置列宽
        for i, column in enumerate(sheet.columns):
            col_letter = get_column_letter(i+1)
            if i == 0:  # ID列
                sheet.column_dimensions[col_letter].width = 15
            else:
                sheet.column_dimensions[col_letter].width = 20
        
        # 设置标题行样式
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        for cell in sheet[1]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal='center')
            
        # 设置数据行样式
        for row in sheet.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(horizontal='center')
                
                # 如果是评级列，设置颜色
                if cell.column == 4:  # 评级列
                    if cell.value == 'A+':
                        cell.fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
                    elif cell.value == 'A':
                        cell.fill = PatternFill(start_color="DDEBF7", end_color="DDEBF7", fill_type="solid")
                    elif cell.value == 'D' or cell.value == 'D-':
                        cell.fill = PatternFill(start_color="FCBEB5", end_color="FCBEB5", fill_type="solid")
    
    def _add_chart(self, writer, sheet_name, x_col, y_col, title):
        """添加图表到工作表"""
        sheet = writer.sheets[sheet_name]
        
        # 获取数据范围
        max_row = sheet.max_row
        
        # 创建图表
        chart = BarChart()
        chart.title = title
        chart.style = 10
        chart.x_axis.title = x_col
        chart.y_axis.title = y_col
        
        # 设置数据
        data = Reference(sheet, min_col=3, min_row=1, max_row=max_row, max_col=3)
        cats = Reference(sheet, min_col=2, min_row=2, max_row=max_row)
        chart.add_data(data, titles_from_data=True)
        chart.set_categories(cats)
        
        # 添加到工作表
        sheet.add_chart(chart, "F2") 