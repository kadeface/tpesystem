"""
教育数据获取接口类

提供统一的数据接口，用于获取和处理教育数据，
支持多种分析模型和评估方法使用相同的数据源格式。

功能特点：
1. 统一的数据获取接口
2. 学生成绩数据处理
3. 班级和学校信息规范化
4. 数据质量验证和清洗
# 初始化数据提供器
provider = EducationDataProvider(
    exam_ids=["EXAM2023-1", "EXAM2023-2"],  # 指定考试ID
    subject_id="MATH",  # 指定学科ID
)

# 获取处理后的数据
data = provider.get_data()

# 准备建模数据（添加了索引编码和时间点）
model_data = provider.prepare_for_modeling()

# 分析CDF
analyzer = CDFAnalyzer()
for student_id, student_data in data.groupby('student_id'):
    scores = student_data['standard_score'].tolist()
    cdf = analyzer.calculate_cdf(scores)
    volatility = analyzer.analyze_volatility(cdf)
    print(f"学生{student_id}波动分析: {volatility}")
"""

import numpy as np
import pandas as pd
import logging
from django.conf import settings
from core.models import (
    Score, 
    Exam, 
    Student, 
    Subject,
    StudentHistory, 
    Teacher,
    TeacherHistory,
    School
)

logger = logging.getLogger(__name__)

class EducationDataProvider:
    """教育数据提供器
    
    提供统一接口获取并处理教育数据，为各种分析模型提供标准化数据源
    """
    
    def __init__(self, exam_ids=None, subject_id=None, semester_range=3, student_ids=None):
        """
        初始化数据提供器
        
        Args:
            exam_ids: list 考试ID列表
            subject_id: str 学科ID
            semester_range: int 学期范围
            student_ids: list 学生ID列表
            
        Returns:
            None
        
        Raises:
            ValueError: 参数错误时抛出
        """
        self.exam_ids = exam_ids
        self.subject_id = subject_id
        self.semester_range = semester_range
        self.student_ids = student_ids
        
        # 数据缓存
        self._exams = None
        self._scores_df = None
        self._processed_df = None
        
        # ID映射字典
        self.mappings = {
            'students': {},
            'teachers': {},
            'schools': {},
            'classes': {}
        }
        
        logger.info(f"初始化教育数据提供器: 考试IDs={exam_ids}, 学科ID={subject_id}")
    
    def get_data(self):
        """优化工作流：以考试学生为中心获取班级和成绩数据"""
        logger.info("开始获取数据（考试中心工作流）...")
        
        # 步骤1: 获取考试信息
        exams = self._get_exams()
        exam_ids = [exam.exam_id for exam in exams]
        semester_ids = [exam.semester_id for exam in exams]
        logger.info(f"目标考试: {exam_ids}, 对应学期: {semester_ids}")
        
        # 步骤2: 获取参加这些考试的学生成绩数据
        scores_df = self._get_scores(exams)
        if scores_df.empty:
            raise ValueError("未找到符合条件的成绩记录")
        
        # 获取参加考试的学生ID列表和对应学期
        exam_students = scores_df[['student_id', 'semester_id']].drop_duplicates()
        student_ids = scores_df['student_id'].unique().tolist()
        logger.info(f"参加考试的学生: {len(student_ids)}人")
        
        # 步骤3: 只获取参加考试学生的历史班级记录
        student_history = self._get_student_history_for_exam_students(
            student_ids, semester_ids
        )
        logger.info(f"获取到 {len(student_history)} 条相关学生历史记录")
        
        # 步骤4: 将成绩数据关联到班级历史记录
        data_df = pd.merge(
            student_history,
            scores_df,
            on=['student_id', 'semester_id'],
            how='inner'  # 只保留同时有班级和成绩的记录
        )
        logger.info(f"关联后数据: {len(data_df)} 条记录")
        
        # 步骤5: 只进行数据清洗，不做班级规范化
        data_df = self._clean_data(data_df)
        logger.info(f"数据清洗后剩余 {len(data_df)} 条记录")
        
        # 缓存处理后的数据
        self._processed_df = data_df
        return data_df
    
    def get_raw_data(self):
        """
        获取原始成绩数据（不含学生历史记录）
        
        Returns:
            DataFrame 原始成绩数据
        """
        if self._scores_df is None:
            exams = self._get_exams()
            self._scores_df = self._get_scores(exams)
        
        return self._scores_df
    
    def get_student_details(self, include_info=True):
        """
        获取学生详细信息
        
        Args:
            include_info: bool 是否包含学生基本信息
            
        Returns:
            DataFrame 学生详细信息
        """
        if self._processed_df is None:
            self.get_data()
            
        student_df = self._processed_df.copy()
        
        if include_info and self.student_ids:
            # 获取学生基本信息
            students = Student.objects.filter(student_id__in=self.student_ids)
            student_info = pd.DataFrame(list(students.values()))
            
            if not student_info.empty:
                # 合并学生信息
                student_df = pd.merge(
                    student_df,
                    student_info,
                    on='student_id',
                    how='left'
                )
        
        return student_df
    
    def get_class_summary(self):
        """根据考试获取班级成绩统计"""
        if self._processed_df is None:
            self.get_data()
        
        # 确保数据包含必要字段
        required = ['semester_id', 'class_id', 'student_id', 'standard_score', 'raw_score', 'exam_id']
        missing = [f for f in required if f not in self._processed_df.columns]
        if missing:
            raise ValueError(f"缺失必要字段: {missing}")
        
        # 按考试ID和班级ID分组统计
        class_summary = self._processed_df.groupby(['exam_id', 'class_id']).agg({
            'student_id': 'nunique',  # 每个考试每个班级的参考学生数
            'standard_score': ['mean', 'std', 'min', 'max'],
            'raw_score': ['mean', 'std', 'min', 'max']
        })
        
        # 列名处理
        class_summary.columns = ['student_count', 'mean_score', 'std_score', 'min_score', 'max_score', 'raw_mean', 'raw_std', 'raw_min', 'raw_max']
        return class_summary.reset_index()
    
    def get_school_summary(self):
        """基于考试的学校统计"""
        if self._processed_df is None:
            self.get_data()
            
        # 确保数据包含必要字段
        required = ['school_id', 'exam_id', 'student_id', 'standard_score', 'raw_score']
        missing = [f for f in required if f not in self._processed_df.columns]
        if missing:
            raise ValueError(f"缺失必要字段: {missing}")
        
        # 首先确保有学校名称信息
        df = self._processed_df.copy()
        if 'school_name' not in df.columns or df['school_name'].isna().all():
            try:
                # 尝试从数据库获取学校名称
                school_ids = df['school_id'].unique().tolist()
                schools = {
                    str(school.id): school.school_name 
                    for school in School.objects.filter(id__in=school_ids)
                }
                
                # 用实际学校名称更新DataFrame
                df['school_name'] = df['school_id'].astype(str).map(
                    lambda x: schools.get(x, f"学校{x}")
                )
                logger.info(f"学校摘要: 从数据库获取了{len(schools)}个学校的名称")
            except Exception as e:
                logger.error(f"获取学校名称失败: {str(e)}")
                # 失败时使用学校ID作为名称
                df['school_name'] = df['school_id'].astype(str).map(lambda x: f"学校{x}")
        
        # 获取每个学校ID对应的名称，用于后续合并
        school_names = df.groupby('school_id')['school_name'].first().reset_index()
        
        # 按考试ID和学校ID分组统计
        school_summary = df.groupby(['exam_id', 'school_id']).agg({
            'student_id': 'nunique',  # 每个考试每个学校的参考学生数
            'standard_score': ['mean', 'std', 'min', 'max'],
            'raw_score': ['mean', 'std', 'min', 'max'],
            'class_id': pd.Series.nunique  # 每个学校涉及的班级数
        })
        
        # 列名处理
        school_summary.columns = ['student_count', 'mean_score', 'std_score', 'min_score', 'max_score', 'raw_mean', 'raw_std', 'raw_min', 'raw_max', 'class_count']
        school_summary = school_summary.reset_index()
        
        # 合并学校名称
        school_summary = pd.merge(
            school_summary,
            school_names,
            on='school_id',
            how='left'
        )
        
        # 检查是否所有学校都有名称
        missing_names = school_summary['school_name'].isna().sum()
        if missing_names > 0:
            logger.warning(f"{missing_names}所学校缺少名称")
            # 为缺少名称的学校提供默认名称
            school_summary['school_name'] = school_summary.apply(
                lambda row: row['school_name'] if pd.notna(row['school_name']) else f"学校{row['school_id']}", 
                axis=1
            )
        
        return school_summary
    
    def _get_exams(self):
        """获取目标考试信息"""
        if self._exams is not None:
            return self._exams
            
        # 如果直接指定了考试ID列表
        if self.exam_ids:
            # 添加宽松查询选项
            exam_query = Exam.objects.filter(status='COMPLETE')
            
            # 尝试精确匹配
            exact_match = exam_query.filter(exam_id__in=self.exam_ids)
            if exact_match.exists():
                logger.info(f"找到精确匹配的考试: {list(exact_match.values_list('exam_id', flat=True))}")
                self._exams = list(exact_match.select_related('semester'))
                return self._exams
                
            # 如果精确匹配失败，尝试使用包含匹配
            contains_matches = []
            for exam_id in self.exam_ids:
                partial_matches = exam_query.filter(exam_id__contains=exam_id)
                contains_matches.extend(list(partial_matches))
                
            if contains_matches:
                logger.info(f"未找到精确匹配，使用部分匹配: {[e.exam_id for e in contains_matches]}")
                self._exams = contains_matches
                return self._exams
                
            # 两种方式都失败，提示可用的考试ID
            available_ids = list(exam_query.values_list('exam_id', flat=True)[:10])
            raise ValueError(f"未找到指定的考试ID: {self.exam_ids}\n可用的考试ID示例: {available_ids}")
        
        # 如果没有指定考试ID，则获取最近的考试
        latest_exams = list(Exam.objects.filter(
            status='COMPLETE'
        ).order_by('-start_time')[:self.semester_range])
        
        if not latest_exams:
            raise ValueError("未找到活动考试")
            
        logger.info(f"获取最近{self.semester_range}个考试: {[e.exam_id for e in latest_exams]}")
        self._exams = latest_exams
        return self._exams
    
    def _get_scores(self, exams):
        """获取原始成绩数据"""
        scores = []
        for score in Score.objects.filter(exam__in=exams, subject_id=self.subject_id):
            scores.append({
                'student_id': score.student_id,
                'exam_id': score.exam_id,
                'semester_id': score.exam.semester_id, 
                'subject_id': score.subject_id,
                'standard_score': score.standard_score,
                'raw_score': score.raw_score
            })
        return pd.DataFrame(scores)

    def _get_latest_context(self, df):
        """修正后的上下文获取方法"""
        # 合并后的数据已包含历史记录中的班级信息
        latest_records = df.sort_values('semester_id').groupby('student_id').tail(1)
        return {
            'class': latest_records.set_index('student_id')['current_class'].to_dict(),  
            'school': latest_records.set_index('student_id')['current_school'].to_dict(),
            'semester': latest_records.set_index('student_id')['semester_id'].to_dict()
        }
    
    def _get_student_history_for_exam_students(self, student_ids, semester_ids):
        """获取参加考试的学生在相关学期的历史班级记录"""
        # 获取指定学生、指定学期的历史记录
        records = StudentHistory.objects.filter(
            student_id__in=student_ids,
            semester_id__in=semester_ids,
            status='ACTIVE'
        ).select_related('school', 'class_field').values(
            'student_id', 'semester_id', 'class_field_id', 'grade_id',
            'school_id', 'school__school_name'
        )
        
        # 转换为DataFrame并重命名列
        history_df = pd.DataFrame(list(records))
        if history_df.empty:
            logger.warning(f"未找到参加考试学生的历史记录。检查的学生ID数量: {len(student_ids)}")
            return pd.DataFrame()
        
        # 重命名列以保持一致性
        history_df = history_df.rename(columns={
            'school__school_name': 'school_name'
        })
        
        # 保留班级原始ID
        history_df['class_id'] = history_df['class_field_id']
        
        # 如果school_name列为空，尝试从School模型直接获取学校名称
        if 'school_name' not in history_df.columns or history_df['school_name'].isna().any():
            try:
                # 获取唯一学校ID
                school_ids = history_df['school_id'].unique().tolist()
                
                # 从School模型获取学校名称
                schools = {
                    str(school.id): school.school_name 
                    for school in School.objects.filter(id__in=school_ids)
                }
                
                # 用实际学校名称更新DataFrame
                history_df['school_name'] = history_df['school_id'].astype(str).map(
                    lambda x: schools.get(x, f"学校{x}")
                )
                logger.info(f"从数据库获取了{len(schools)}个学校的名称")
            except Exception as e:
                logger.error(f"获取学校名称失败: {str(e)}")
                # 失败时使用学校ID作为名称
                history_df['school_name'] = history_df['school_id'].astype(str)
        
        return history_df
    
    def _normalize_class_groups(self, data):
        """新版班级规范化方法，基于结构化ID提取稳定班级编号"""
        logger.info("执行班级规范化...")
        
        # 验证必要字段
        required_cols = ['class_field_id', 'grade_id']
        missing_cols = [col for col in required_cols if col not in data.columns]
        if missing_cols:
            logger.error(f"缺失必要字段: {missing_cols}")
            raise ValueError(f"数据缺少必要字段: {missing_cols}")
        
        try:
            # 提取稳定班级编号
            data['stable_class'] = data.apply(
                lambda row: self.extract_class_number(
                    row['class_field_id'], 
                    row['grade_id']
                ), 
                axis=1
            )
            
            # 保留原始班级信息
            data['original_class'] = data['class_id']
            
            # 记录变化
            original_count = data['class_id'].nunique()
            stable_count = data['stable_class'].nunique()
            logger.info(f"班级规范化完成: {original_count} -> {stable_count} 个唯一班级")
            
        except Exception as e:
            logger.error(f"班级规范化失败: {str(e)}")
            sample_data = data[['class_field_id', 'grade_id']].head(3).to_dict('records')
            logger.debug(f"问题数据示例: {sample_data}")
            raise
        
        return data

    def _further_consolidate_classes(self, data):
        """优化后的班级合并方法（可选步骤）"""
        # 按学校和稳定班级分组
        grouped = data.groupby(['school_id', 'stable_class'])
        
        # 生成合并ID（学校+班级）
        data['merged_class'] = (
            data['school_id'].astype(str) + '_' +
            data['stable_class'].astype(str)
        )
        
        # 记录合并效果
        before = data['stable_class'].nunique()
        after = data['merged_class'].nunique()
        logger.info(f"班级合并: {before} -> {after} 个组合班级")
        
        return data
    
    def _clean_data(self, df):
        """数据清洗：移除无效班级和学校"""
        logger.info(f"清洗前数据条数: {len(df)}")
        
        # 过滤条件1: 移除班级人数少于2人的记录
        class_counts = df.groupby(['exam_id', 'class_id'])['student_id'].nunique()
        valid_classes = class_counts[class_counts >= 2].index
        
        # 构建复合索引条件
        valid_mask = df.set_index(['exam_id', 'class_id']).index.isin(valid_classes)
        df_filtered = df[valid_mask].reset_index(drop=True)
        logger.info(f"移除小班级后: {len(df_filtered)} 条记录")
        
        # 过滤条件2: 移除学校班级数小于等于1的记录
        school_class_counts = df_filtered.groupby(['exam_id', 'school_id'])['class_id'].nunique()
        valid_schools = school_class_counts[school_class_counts > 1].index
        
        # 构建复合索引条件
        valid_school_mask = df_filtered.set_index(['exam_id', 'school_id']).index.isin(valid_schools)
        df_final = df_filtered[valid_school_mask].reset_index(drop=True)
        logger.info(f"移除单班学校后: {len(df_final)} 条记录")
        
        # 结果验证
        if len(df_final) < len(df) * 0.5:
            logger.warning(f"清洗移除了超过50%的数据，请检查过滤条件")
        
        if df_final.empty:
            logger.error("清洗后无有效数据剩余")
            raise ValueError("清洗过滤条件过严，导致无有效数据")
        
        return df_final

    def prepare_for_modeling(self, add_indices=True, add_time_points=True):
        """
        为建模准备数据
        
        Args:
            add_indices: bool 是否添加索引编码
            add_time_points: bool 是否添加时间点
            
        Returns:
            DataFrame 准备好的建模数据
        """
        if self._processed_df is None:
            self.get_data()
            
        df = self._processed_df.copy()
        
        # 添加数值编码
        if add_indices:
            if 'student_id' in df.columns:
                df['student_code'] = df['student_id'].astype('category').cat.codes
                
            if 'school_id' in df.columns:
                df['school_code'] = df['school_id'].astype('category').cat.codes
                
            if 'stable_class' in df.columns:
                df['class_code'] = df['stable_class'].astype('category').cat.codes
            elif 'class_id' in df.columns:
                df['class_code'] = df['class_id'].astype('category').cat.codes
        
        # 添加时间点
        if add_time_points:
            # 将最后一次考试标记为后测
            df['is_posttest'] = df.groupby('student_id')['exam_id'].transform(
                lambda x: x == x.iloc[-1]
            )
            # 分离前测特征和后测结果
            df['pretest_features'] = df.groupby('student_id')['standard_score'].shift(1)
        
        return df 

    def extract_class_number(self, class_field_id, grade_id):
        """
        从结构化ID中提取稳定班级编号
        
        Args:
            class_field_id: 班级字段ID (格式示例: C02_73_231)
            grade_id: 年级ID (格式示例: G02_7_231)
            
        Returns:
            str: 稳定班级编号
            
        Raises:
            ValueError: ID格式不匹配时抛出异常
        """
        # 分割ID组成部分
        class_parts = class_field_id.split('_')
        grade_parts = grade_id.split('_')
        
        # 基础格式验证
        if len(class_parts) != 3 or len(grade_parts) != 3:
            raise ValueError("ID格式不正确")
        if class_parts[0][1:] != grade_parts[0][1:]:
            raise ValueError("学校代码不匹配")
        
        # 提取年级班级段
        class_segment = class_parts[1]  # 示例: "73"
        grade_segment = grade_parts[1]  # 示例: "7"
        
        # 动态计算班级编号
        if not class_segment.startswith(grade_segment):
            raise ValueError("年级信息不匹配")
        
        class_number = class_segment[len(grade_segment):]
        
        # 有效性检查
        if not class_number.isdigit():
            raise ValueError("班级编号包含非数字字符")
        
        return class_number.zfill(2)  # 统一为两位数

