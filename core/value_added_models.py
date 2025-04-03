#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
增值分析模型实现模块

提供多种增值模型实现和分析框架组件：

框架组件:
- BaseValueAddedModel - 所有增值模型的基类
- ValueAddedDataProcessor - 数据预处理器
- ValueAddedVisualizer - 可视化工具

模型实现:
1. 贝叶斯多层次模型 - 全贝叶斯推断
2. 频率派多层次模型 - 基于最大似然估计 
3. 固定效应模型 - 传统面板数据模型
4. 随机效应模型 - 随机斜率和截距
5. 动态贝叶斯模型 - 基于状态空间
6. TVAM模型 - 传统增值评估模型

所有模型基于统一的接口和数据格式，保证接口一致性和代码复用。
"""

import numpy as np
import pandas as pd
import logging
import os
from pathlib import Path
import json
import matplotlib.pyplot as plt
from scipy import stats
from abc import ABC, abstractmethod
from django.conf import settings
from datetime import datetime

# 建模库
import pymc as pm
import arviz as az
import statsmodels.api as sm
import statsmodels.formula.api as smf
from statsmodels.regression.mixed_linear_model import MixedLM
from statsmodels.regression.linear_model import OLS
from statsmodels.tsa.statespace.kalman_filter import KalmanFilter

# 配置日志
logger = logging.getLogger(__name__)

# 导入后立即配置matplotlib
import matplotlib as mpl
# 抑制不必要的matplotlib调试输出
mpl.set_loglevel('WARNING')  # 仅显示警告及以上级别的日志

# 导入后配置matplotlib日志级别
import logging
# 将matplotlib相关日志级别设置为WARNING
logging.getLogger('matplotlib').setLevel(logging.WARNING)

#############################################
# 第一部分: 基础数据处理器
#############################################

class ValueAddedDataProcessor:
    """
    增值分析数据处理器
    
    提供数据获取、清洗、转换和准备的基础功能组件
    """
    
    def __init__(self, provider=None):
        """
        初始化数据处理器
        
        Args:
            provider: 数据提供器实例，如果为None则使用默认提供器
        """
        self.provider = provider
        self.mappings = {
            'schools': {},
            'teachers': {},
            'students': {},
            'classes': {},
            'exams': {},
            'subjects': {}
        }
        self.data = None
        self.model_data = None
    
    def load_data(self, **kwargs):
        """
        加载教育数据
        
        Args:
            **kwargs: 传递给数据提供者的参数
                exam_ids: 考试ID列表
                subject_id: 学科ID
                baseline_exam: 指定的基准考试ID
                
        Returns:
            DataFrame: 加载的数据
        """
        # 提取baseline_exam参数，不传递给EducationDataProvider
        self.baseline_exam = kwargs.pop('baseline_exam', None)
        
        # 创建数据提供者
        from core.management.commands.education_data_provider import EducationDataProvider
        self.provider = EducationDataProvider(**kwargs)
        
        # 加载数据
        self.data = self.provider.get_data()
        
        logger.info(f"加载了{len(self.data)}条数据")
        return self.data
    
    def _process_pre_post_tests(self, data, baseline_exam=None):
        """
        处理前测和后测数据
        
        Args:
            data: 输入数据
            baseline_exam: 指定的基准考试ID（可选）
            
        Returns:
            DataFrame: 添加了前测信息的数据
        """
        # 确保数据包含必要字段
        required_fields = ['student_id', 'standard_score', 'exam_id']
        missing_fields = [f for f in required_fields if f not in data.columns]
        if missing_fields:
            raise ValueError(f"数据缺少必要字段: {missing_fields}")
        
        # 按学生ID和考试ID排序
        prep_data = data.sort_values(['student_id', 'exam_id'])
        
        # 如果指定了基准考试，则使用它
        if baseline_exam:
            # 使用指定的基准考试
            prior_scores = prep_data[prep_data['exam_id'] == baseline_exam].copy()
            if prior_scores.empty:
                raise ValueError(f"指定的基准考试 {baseline_exam} 在数据中不存在")
            logger.info(f"使用指定考试作为基准(前测): {baseline_exam}")
        else:
            # 否则为每个学生使用第一次考试
            prep_data['time_point'] = prep_data.groupby('student_id')['exam_id'].rank(method='dense')
            prior_scores = prep_data[prep_data['time_point'] == 1].copy()
            baseline_exams = prior_scores['exam_id'].unique()
            self.baseline_exams = baseline_exams
            logger.info(f"使用以下考试作为基准(前测): {', '.join(baseline_exams)}")
            if len(baseline_exams) > 1:
                logger.warning(f"检测到多个基准考试，这可能导致结果混乱。请考虑使用--baseline参数指定单一基准考试。")
        
        prior_scores = prior_scores[['student_id', 'standard_score']]
        prior_scores.rename(columns={'standard_score': 'prior_score'}, inplace=True)
        
        # 合并前测成绩到所有记录
        prep_data = pd.merge(prep_data, prior_scores, on='student_id', how='left')
        
        return prep_data
    
    def _filter_pretest_data(self, data, baseline_exam=None):
        """
        处理前测相关的数据过滤
        
        包括：
        - 过滤缺少前测成绩的记录
        - 移除前测考试记录
        
        Args:
            data: 数据框，包含前测成绩
            baseline_exam: 基准考试ID，如果为None则使用时间点识别前测
            
        Returns:
            DataFrame: 过滤后的数据框
        """
        model_data = data.copy()
        
        # 处理缺失前测成绩的情况
        missing_prior = model_data['prior_score'].isna().sum()
        if missing_prior > 0:
            logger.warning(f"有{missing_prior}条数据缺少前测成绩，这些记录将被过滤")
            model_data = model_data.dropna(subset=['prior_score'])
            logger.info(f"过滤后剩余{len(model_data)}条有效数据")
        
        # 移除前测考试记录
        if baseline_exam:
            # 如果指定了基准考试，移除该考试的记录
            pre_test_count = model_data[model_data['exam_id'] == baseline_exam].shape[0]
            model_data = model_data[model_data['exam_id'] != baseline_exam]
            logger.info(f"已移除{pre_test_count}条前测考试记录(exam_id={baseline_exam})，剩余{len(model_data)}条记录")
        elif 'time_point' in model_data.columns:
            # 如果使用第一次考试作为前测，移除所有time_point=1的记录
            pre_test_count = model_data[model_data['time_point'] == 1].shape[0]
            model_data = model_data[model_data['time_point'] > 1]
            logger.info(f"已移除{pre_test_count}条前测考试记录(第一次考试)，剩余{len(model_data)}条记录")
            
        return model_data
    
    def _create_numeric_indices(self, data):
        """
        创建分类变量的数值索引
        
        Args:
            data: 输入数据
            
        Returns:
            DataFrame: 添加了索引的数据
        """
        # 复制数据以避免修改原始数据
        indexed_data = data.copy()
        
        # 创建学校索引
        if 'school_id' in indexed_data.columns:
            indexed_data['school_idx'] = indexed_data['school_id'].astype('category').cat.codes
            self.mappings['schools'] = dict(zip(
                indexed_data['school_id'].unique(), 
                indexed_data['school_idx'].unique()
            ))
        
        # 创建班级索引
        if 'class_id' in indexed_data.columns:
            indexed_data['class_idx'] = indexed_data['class_id'].astype('category').cat.codes
            self.mappings['classes'] = dict(zip(
                indexed_data['class_id'].unique(), 
                indexed_data['class_idx'].unique()
            ))
        
        # 创建学生索引
        indexed_data['student_idx'] = indexed_data['student_id'].astype('category').cat.codes
        self.mappings['students'] = dict(zip(
            indexed_data['student_id'].unique(), 
            indexed_data['student_idx'].unique()
        ))
        
        # 创建考试索引
        indexed_data['exam_idx'] = indexed_data['exam_id'].astype('category').cat.codes
        self.mappings['exams'] = dict(zip(
            indexed_data['exam_id'].unique(), 
            indexed_data['exam_idx'].unique()
        ))
        
        # 创建学科索引
        if 'subject_id' in indexed_data.columns:
            indexed_data['subject_idx'] = indexed_data['subject_id'].astype('category').cat.codes
            self.mappings['subjects'] = dict(zip(
                indexed_data['subject_id'].unique(), 
                indexed_data['subject_idx'].unique()
            ))
        
        return indexed_data
    
    def _standardize_scores(self, data):
        """
        标准化分数
        
        Args:
            data: 输入数据
            
        Returns:
            DataFrame: 添加了标准化分数的数据
        """
        std_data = data.copy()
        
        # 标准化前测分数
        if 'prior_score' in std_data.columns:
            mean_prior = std_data['prior_score'].mean()
            std_prior = std_data['prior_score'].std()
            std_data['prior_score_z'] = (std_data['prior_score'] - mean_prior) / std_prior
        
        # 标准化当前分数
        if 'standard_score' in std_data.columns:
            mean_current = std_data['standard_score'].mean()
            std_current = std_data['standard_score'].std()
            std_data['standard_score_z'] = (std_data['standard_score'] - mean_current) / std_current
        
        return std_data
    
    def _ensure_school_names(self, data):
        """
        确保学校名称字段存在且正确
        
        如果school_name与school_id相同，尝试从数据库获取真实学校名称
        
        Args:
            data: 包含学校ID的数据框
            
        Returns:
            DataFrame: 添加或更新了学校名称的数据框
        """
        if 'school_id' not in data.columns:
            logger.warning("数据中缺少school_id字段，无法获取学校名称")
            return data
            
        # 检查是否需要获取学校名称
        need_school_names = (
            'school_name' not in data.columns or 
            data['school_id'].astype(str).equals(data['school_name'].astype(str))
        )
        
        if need_school_names:
            logger.info("尝试从数据库获取学校名称")
            try:
                # 导入School模型
                from django.apps import apps
                School = apps.get_model('core', 'School')
                
                # 获取唯一的学校ID
                school_ids = data['school_id'].unique().tolist()
                logger.info(f"需要查询{len(school_ids)}所学校的名称")
                
                # 创建学校ID到名称的映射
                school_names = {}
                for school in School.objects.filter(school_id__in=school_ids):
                    school_names[str(school.school_id)] = school.school_name
                    
                # 更新数据框中的学校名称
                if school_names:
                    logger.info(f"成功获取{len(school_names)}所学校的名称")
                    data['school_name'] = data['school_id'].astype(str).map(
                        lambda x: school_names.get(x, f"学校{x}")
                    )
                    logger.info(f"更新后的school_name示例: {data['school_name'].head(3).tolist()}")
                else:
                    logger.warning("从数据库未找到任何学校名称")
                    data['school_name'] = data['school_id'].astype(str).map(lambda x: f"学校{x}")
            except Exception as e:
                logger.error(f"从数据库获取学校名称失败: {str(e)}")
                # 如果查询失败，确保school_name字段存在
                data['school_name'] = data['school_id'].astype(str).map(lambda x: f"学校{x}")
        
        return data

    def _generate_display_ids(self, data):
        """
        生成用户友好的显示ID
        
        只包含年级和班级信息，不包含学校代码
        
        Args:
            data: 包含年级和班级信息的数据框
            
        Returns:
            DataFrame: 添加了display_id列的数据框
        """
        # 检查是否有年级和班级信息
        has_grade = 'grade' in data.columns
        has_class_num = 'class_num' in data.columns
        
        if not has_grade and not has_class_num:
            logger.warning("无法生成display_id：缺少年级和班级信息")
            return data
            
        # 生成display_id
        if has_grade and has_class_num:
            data['display_id'] = data.apply(
                lambda x: f"{x['grade']}年{x['class_num']}班", 
                axis=1
            )
        elif has_grade:
            data['display_id'] = data.apply(
                lambda x: f"{x['grade']}年级", 
                axis=1
            )
        elif has_class_num:
            data['display_id'] = data.apply(
                lambda x: f"{x['class_num']}班", 
                axis=1
            )
            
        logger.info(f"已生成display_id，示例: {data['display_id'].head(3).tolist()}")
        return data
            
    def _validate_data(self, data, strict=True):
        """
        验证数据完整性
        
        Args:
            data: 要验证的数据
            strict: 是否严格验证（如对缺失值的处理）
            
        Returns:
            bool: 验证通过则返回True，否则引发异常
        """
        # 检查数据量
        if len(data) < 30:  # 最小样本量要求
            raise ValueError(f"数据量太少({len(data)}条)，无法进行有效分析")
        
        # 检查关键列
        required_cols = ['student_idx', 'standard_score', 'prior_score']
        missing_cols = [col for col in required_cols if col not in data.columns]
        if missing_cols:
            raise ValueError(f"数据缺少必要列: {missing_cols}")
        
        # 检查缺失值
        key_cols = ['student_idx', 'standard_score']  # 不再检查prior_score
        na_counts = data[key_cols].isna().sum()
        if na_counts.sum() > 0:
            if strict:
                raise ValueError(f"数据存在缺失值: {na_counts}")
            else:
                logger.warning(f"数据存在缺失值: {na_counts}")
        
        return True

    def validate_for_models(self, models=None):
        """
        验证处理后的数据是否满足指定模型的需求
        
        Args:
            models: 模型名称列表或模型类列表，None表示验证所有已知模型
            
        Returns:
            bool: 数据是否满足所有指定模型的需求
            
        Raises:
            ValueError: 如果数据不满足需求
        """
        if self.model_data is None or self.model_data.empty:
            raise ValueError("请先准备模型数据")
        
        # 默认验证所有模型
        if models is None:
            from core.value_added_models import MODEL_MAPPING
            models = MODEL_MAPPING.values()
        
        # 收集所有必需字段
        all_required_fields = set()
        for model in models:
            # 基本字段：所有模型都需要
            all_required_fields.update(['prior_score', 'standard_score', 'student_idx'])
            
            # 模型特定字段
            if model in [BayesianValueAddedModel]:
                all_required_fields.update(['class_idx', 'school_idx'])
        
        # 检查缺失字段
        missing_fields = [f for f in all_required_fields if f not in self.model_data.columns]
        if missing_fields:
            raise ValueError(f"处理后的数据缺少以下模型所需字段: {missing_fields}")
        
        return True 

    def _process_class_ids(self, model_data):
        """
        处理班级ID，支持不同学段和双位数年级编号
        
        Args:
            model_data: 包含班级ID的数据框
            
        Returns:
            DataFrame: 添加了班级ID相关列的数据框
        """
        if 'class_id' not in model_data.columns:
            return model_data
            
        # 从exam_id判断学段
        if 'exam_id' in model_data.columns:
            # 创建学段列
            model_data['school_level'] = model_data['exam_id'].apply(
                lambda x: 'PRIMARY' if '-P-' in x else 
                         ('MIDDLE' if '-M-' in x else 
                         ('HIGH' if '-H-' in x else 'UNKNOWN'))
            )
            
            # 根据不同学段设置年级范围
            def extract_grade_class(class_id, school_level):
                try:
                    # 检查班级ID格式
                    parts = class_id.split('_')
                    if len(parts) < 3:
                        logger.warning(f"班级ID格式异常: {class_id}，部分少于3")
                        return "00", "0", "0", "00", "0"  # 返回默认值
                        
                    # 提取学校代码
                    school_code = parts[0].replace('C', '')
                    
                    # 提取年级班级部分
                    grade_class_part = parts[1]
                    
                    # 根据学段使用不同的解析逻辑
                    if school_level == 'HIGH':  # 高中(10-12年级)
                        # 高中年级可能是两位数
                        if len(grade_class_part) == 3:  # 例如101 = 10年级1班
                            grade = grade_class_part[:2]
                            class_num = grade_class_part[2]
                        else:  # 容错处理
                            grade = grade_class_part[0] if grade_class_part else "0"
                            class_num = grade_class_part[1:] if len(grade_class_part) > 1 else "0"
                    else:  # 小学、初中
                        # 一位数年级
                        if grade_class_part:
                            grade = grade_class_part[0]
                            class_num = grade_class_part[1:] if len(grade_class_part) > 1 else "0"
                        else:
                            grade = "0"
                            class_num = "0"
                    
                    # 提取学期信息
                    semester_part = parts[2]
                    if len(semester_part) >= 3:
                        academic_year = semester_part[:2]
                        semester = semester_part[2]
                    elif len(semester_part) == 2:
                        academic_year = semester_part
                        semester = "0"  # 默认学期
                    else:
                        # 其他异常情况
                        logger.warning(f"学期部分格式异常: {semester_part} (来自{class_id})")
                        academic_year = semester_part if semester_part else "00"
                        semester = "0"
                    
                    return school_code, grade, class_num, academic_year, semester
                
                except Exception as e:
                    # 出现任何异常时记录并返回默认值
                    logger.error(f"解析班级ID异常: {class_id}, {str(e)}")
                    return "00", "0", "0", "00", "0"
            
            # 在应用解析函数前检查班级ID格式
            invalid_ids = model_data[model_data['class_id'].apply(lambda x: len(x.split('_')) < 3)]['class_id'].unique()
            if len(invalid_ids) > 0:
                logger.warning(f"发现{len(invalid_ids)}个格式异常的班级ID: {', '.join(invalid_ids[:5])}...")
                
            # 应用解析函数
            extracted = model_data.apply(
                lambda x: extract_grade_class(x['class_id'], x['school_level']), 
                axis=1, 
                result_type='expand'
            )
            extracted.columns = ['school_code', 'grade', 'class_num', 'academic_year', 'semester']
            
            # 将提取的列添加到数据框
            for col in extracted.columns:
                model_data[col] = extracted[col]
            
            # 创建班级基础ID（不含年级和学期）
            model_data['class_base_id'] = model_data.apply(
                lambda x: f"C{x['school_code']}_{x['class_num']}", axis=1
            )
            
            # 创建队列ID
            model_data['cohort_id'] = model_data.apply(
                lambda x: f"C{x['school_code']}_{x['class_num']}_CO{x['academic_year']}", axis=1
            )
            
            # 生成友好的班级名称
            model_data['class_name'] = model_data.apply(
                lambda x: f"{x['grade']}年级{x['class_num']}班", axis=1
            )
            
            # 带学校和学段的完整名称
            if 'school_name' in model_data.columns:
                model_data['full_class_name'] = model_data.apply(
                    lambda x: f"{x['school_name']}-{x['grade']}年级{x['class_num']}班({x['school_level']})", 
                    axis=1
                )
                
            # 记录统计信息
            logger.info(f"处理了{model_data['class_id'].nunique()}个原始班级ID")
            logger.info(f"识别出{model_data['class_base_id'].nunique()}个基础班级")
            logger.info(f"识别出{model_data['cohort_id'].nunique()}个学生队列")
        
        # 只保留学校ID的最后两位数字作为学校代码
        if 'school_id' in model_data.columns:
            # 提取学校ID的最后两位作为学校代码
            model_data['school_short_code'] = model_data['school_id'].astype(str).str[-2:]
            logger.info(f"从学校ID中提取最后两位作为简短代码")
        
        return model_data

    def _ensure_student_names(self, data):
        """
        确保学生姓名字段存在且正确
        
        如果student_name不存在，尝试从多种来源获取学生姓名信息
        
        Args:
            data: 包含学生ID的数据框
            
        Returns:
            DataFrame: 添加或更新了学生姓名的数据框
        """
        if 'student_name' in data.columns:
            return data
            
        model_data = data.copy()
        
        if 'name' in model_data.columns:
            # 如果数据中包含name字段，但没有student_name字段，将name映射为student_name
            model_data['student_name'] = model_data['name']
            logger.info("将name字段映射为student_name")
        elif hasattr(self, 'provider') and self.provider:
            # 如果有provider属性，尝试从provider获取学生信息
            try:
                student_ids = model_data['student_id'].unique().tolist()
                
                # 不传递include_info参数，依赖默认值
                student_details = self.provider._get_student_details(student_ids)
                
                if student_details is not None and not student_details.empty:
                    # 创建ID到姓名的映射
                    name_mapping = dict(zip(
                        student_details['student_id'].astype(str), 
                        student_details['student_name']
                    ))
                    
                    # 添加姓名字段
                    model_data['student_name'] = model_data['student_id'].astype(str).map(
                        name_mapping).fillna("未知学生")
                    logger.info(f"从数据提供者获取了{len(name_mapping)}个学生的姓名信息")
                else:
                    model_data['student_name'] = model_data['student_id'].astype(str)
                    logger.warning("无法从数据提供者获取学生姓名，使用学生ID作为姓名")
            except Exception as e:
                model_data['student_name'] = model_data['student_id'].astype(str)
                logger.warning(f"获取学生姓名时出错: {str(e)}，使用学生ID作为姓名")
        else:
            # 如果没有其他来源，使用student_id作为student_name
            model_data['student_name'] = model_data['student_id'].astype(str)
            logger.warning("数据中缺少学生姓名信息，使用学生ID作为姓名")
            
        return model_data

    # 添加一个数据处理工具集方法
    def get_data_processors(self):
        """
        获取所有数据处理工具函数
        
        Returns:
            dict: 包含所有处理函数的字典
        """
        return {
            'process_pre_post_tests': self._process_pre_post_tests,
            'filter_pretest_data': self._filter_pretest_data,
            'create_numeric_indices': self._create_numeric_indices,
            'standardize_scores': self._standardize_scores,
            'ensure_school_names': self._ensure_school_names,
            'process_class_ids': self._process_class_ids,
            'generate_display_ids': self._generate_display_ids,
            'ensure_student_names': self._ensure_student_names,
            'validate_data': self._validate_data,
            'ensure_class_names': self._ensure_class_names,
            'ensure_grade_field': self._ensure_grade_field
        }

    # 在ValueAddedDataProcessor类中添加以下方法

    def _ensure_class_names(self, df):
        """
        确保数据中包含班级名称
        
        从class_id或stable_class字段提取班级名称，
        并添加class_name字段
        
        Args:
            df: 输入数据框
            
        Returns:
            DataFrame: 添加了class_name字段的数据框
        """
        if 'class_name' not in df.columns or df['class_name'].isnull().all():
            logger.info("正在生成班级名称字段")
            
            if 'class_id' in df.columns:
                # 使用_process_class_ids方法的逻辑提取班级名称
                temp_df = self._process_class_ids(df.copy())
                
                # 如果_process_class_ids成功添加了class_name字段
                if 'class_name' in temp_df.columns:
                    logger.info("从class_id成功生成班级名称")
                    df['class_name'] = temp_df['class_name']
                else:
                    # 简单提取班级编号作为备选方案
                    logger.warning("使用备选方案从class_id提取班级名称")
                    df['class_name'] = df['class_id'].apply(
                        lambda x: f"{x.split('_')[1]}班" if isinstance(x, str) and '_' in x else '未知'
                    )
            elif 'stable_class' in df.columns:
                df['class_name'] = df['stable_class'].apply(
                    lambda x: f"{x}班" if isinstance(x, str) else '未知'
                )
            else:
                logger.warning("找不到班级相关字段，无法生成班级名称")
                df['class_name'] = '未知'
        
        return df

    def _ensure_grade_field(self, df):
        """
        确保数据中包含年级字段
        
        从class_id或grade_id字段提取年级信息
        
        Args:
            df: 输入数据框
            
        Returns:
            DataFrame: 添加了grade字段的数据框
        """
        if 'grade' not in df.columns or df['grade'].isnull().all():
            logger.info("正在生成年级字段")
            
            if 'grade_id' in df.columns:
                df['grade'] = df['grade_id'].apply(
                    lambda x: f"{x.split('_')[1]}年级" if isinstance(x, str) and '_' in x else '未知'
                )
            elif 'class_id' in df.columns:
                # 从班级ID提取年级信息 (假设格式为C01_71_232，其中7表示年级)
                df['grade'] = df['class_id'].apply(
                    lambda x: f"{x.split('_')[1][0]}年级" if isinstance(x, str) and '_' in x 
                              and len(x.split('_')) > 1 and x.split('_')[1] 
                              and x.split('_')[1][0].isdigit() else '未知'
                )
            else:
                logger.warning("找不到年级相关字段，无法生成年级信息")
                df['grade'] = '未知'
        
        return df

#############################################
# 第二部分: 模型基类
#############################################

class BaseValueAddedModel(ABC):
    """
    增值模型基类
    
    为所有增值模型提供通用接口和基础功能
    """
    
    def __init__(self, data=None, data_processor=None):
        """
        初始化模型
        
        Args:
            data: 原始数据DataFrame
            data_processor: 数据处理器实例
        """
        self.raw_data = data
        self.data = None  # 处理后的建模数据
        self.data_processor = data_processor or ValueAddedDataProcessor()
        self.model = None
        self.metrics = {}
        self.result = None
    
    def prepare_data(self, data=None):
        """
        准备模型所需数据
        
        子类应该重写此方法以实现特定的数据处理逻辑
        
        Args:
            data: 输入数据，如果为None则使用初始化时的数据
            
        Returns:
            DataFrame: 准备好的建模数据
        """
        if data is not None:
            self.raw_data = data
            
        if self.raw_data is None:
            raise ValueError("请提供数据")
            
        # 获取数据处理工具
        processors = self.data_processor.get_data_processors()
        
        # 基本数据处理流程 - 子类可重写此方法
        baseline_exam = getattr(self.data_processor, 'baseline_exam', None)
        
        # 前测后测处理
        model_data = processors['process_pre_post_tests'](self.raw_data, baseline_exam)
        
        # 过滤前测数据
        model_data = processors['filter_pretest_data'](model_data, baseline_exam)
        
        # 创建数值索引
        model_data = processors['create_numeric_indices'](model_data)
        
        # 确保学生和学校名称
        model_data = processors['ensure_school_names'](model_data)
        model_data = processors['ensure_student_names'](model_data)
        
        # 处理班级ID
        model_data = processors['process_class_ids'](model_data)
        
        # 生成友好ID
        model_data = processors['generate_display_ids'](model_data)
        
        # 保存处理后的数据
        self.data = model_data
        return model_data
        
    def fit(self, data=None):
        """
        拟合模型
        
        Args:
            data: 原始数据，如果为None则使用初始化时的数据
            
        Returns:
            self: 支持链式调用
        """
        if data is not None:
            self.raw_data = data
        
        # 准备数据
        if self.data is None:
            self.prepare_data()
        
        self._validate_data()
        self._build_model()
        self._fit_model()
        
        return self
    
    def predict(self, new_data=None):
        """
        使用拟合后的模型进行预测
        
        Args:
            new_data: 新数据，如果为None则使用拟合时的数据
            
        Returns:
            ndarray: 预测结果
        """
        if self.result is None:
            raise ValueError("请先拟合模型")
        
        if new_data is None:
            new_data = self.data
            
        predictions = self._predict_impl(new_data)
        return predictions
    
    def calculate_value_added(self):
        """
        计算各层级的增值得分
        
        Returns:
            dict: 包含各层级增值得分的字典
        """
        if self.result is None:
            raise ValueError("请先拟合模型")
            
        value_added = self._calculate_value_added_impl()
        return value_added
    
    def get_metrics(self):
        """
        获取模型评估指标
        
        Returns:
            dict: 评估指标
        """
        return self.metrics
    
    @abstractmethod
    def _validate_data(self):
        """验证模型所需数据"""
        pass
    
    @abstractmethod
    def _build_model(self):
        """构建模型"""
        pass
    
    @abstractmethod
    def _fit_model(self):
        """拟合模型"""
        pass
    
    @abstractmethod
    def _predict_impl(self, new_data):
        """模型预测的具体实现"""
        pass
    
    @abstractmethod
    def _calculate_value_added_impl(self):
        """增值效应计算的具体实现"""
        pass
    
    def save_results(self, output_dir):
        """
        保存模型结果
        
        Args:
            output_dir: 输出目录
            
        Returns:
            dict: 保存的文件路径
        """
        if self.result is None:
            raise ValueError("请先拟合模型")
            
        # 确保目录存在
        os.makedirs(output_dir, exist_ok=True)
        
        # 保存指标
        metrics_path = os.path.join(output_dir, "model_metrics.json")
        with open(metrics_path, 'w') as f:
            json.dump(self.metrics, f, indent=2)
            
        # 子类可扩展此方法保存更多内容
        return {"metrics": metrics_path}        

    
#############################################
# 第三部分: 可视化工具
#############################################

class ValueAddedVisualizer:
    """增值分析结果可视化器"""
    
    def __init__(self, result=None, model_name=None):
        """
        初始化可视化器
        
        Args:
            result: 模型结果字典
            model_name: 模型名称，用于图表标题
        """
        self.result = result
        self.model_name = model_name
    
    def visualize(self, output_dir, result=None):
        """
        生成可视化结果
        
        Args:
            output_dir: 输出目录
            results: 模型结果字典，如果为None则使用初始化时的结果
            
        Returns:
            dict: 保存的文件路径
        """
        if result is not None:
            self.result = result
            
        if self.result is None:
            raise ValueError("请提供模型结果")
            
        # 确保目录存在
        os.makedirs(output_dir, exist_ok=True)
        
        # 保存的文件路径
        saved_paths = {}
        
        # 1. 生成各层级增值效应分布图
        for level in ['schools', 'classes']:
            if level in self.result and not self.result[level].empty:
                fig_path = os.path.join(output_dir, f"{level}_value_added_dist.png")
                self._plot_value_added_distribution(
                    self.result[level], 
                    title=f"{level.capitalize()} Value-Added Distribution",
                    output_path=fig_path
                )
                saved_paths[f"{level}_dist"] = fig_path
        
        # 2. 生成学校-班级关系图
        if 'schools' in self.result and 'classes' in self.result:
            if not self.result['schools'].empty and not self.result['classes'].empty:
                fig_path = os.path.join(output_dir, "school_class_relationship.png")
                self._plot_school_class_relationship(output_path=fig_path)
                saved_paths["school_class_relationship"] = fig_path
        
        # 3. 生成增值效应评级图
        for level in ['schools', 'classes']:
            if level in self.result and not self.result[level].empty:
                fig_path = os.path.join(output_dir, f"{level}_rating.png")
                self._plot_rating_distribution(
                    self.result[level], 
                    title=f"{level.capitalize()} Value-Added Ratings",
                    output_path=fig_path
                )
                saved_paths[f"{level}_rating"] = fig_path
        
        return saved_paths
    
    def _plot_value_added_distribution(self, df, title, output_path):
        """绘制增值效应分布图"""
        plt.figure(figsize=(10, 6))
        plt.hist(df['mean' if 'mean' in df.columns else 'value_added'], bins=20, alpha=0.7)
        plt.axvline(0, color='red', linestyle='--')
        plt.title(title)
        plt.xlabel('Value-Added Score')
        plt.ylabel('Frequency')
        plt.grid(True, linestyle='--', alpha=0.7)
        plt.tight_layout()
        plt.savefig(output_path, dpi=300)
        plt.close()
    
    def _plot_school_class_relationship(self, output_path):
        """绘制学校-班级关系图"""
        # 假设我们有学校和班级的数据
        schools = self.result['schools']
        classes = self.result['classes']
        
   
        
        plt.figure(figsize=(12, 8))

        plt.title('School-Class Value-Added Relationship')
        plt.xlabel('School Value-Added')
        plt.ylabel('Class Value-Added')
        plt.grid(True, linestyle='--', alpha=0.7)
        plt.tight_layout()
        plt.savefig(output_path, dpi=300)
        plt.close()
    
    def _plot_rating_distribution(self, df, title, output_path):
        """绘制增值效应评级分布图"""
        # 添加评级列（如果不存在）
        if 'rating' not in df.columns:
            values = df['mean' if 'mean' in df.columns else 'value_added']
            df['rating'] = pd.cut(
                values,
                bins=[-float('inf'), -1.5, -0.5, 0.5, 1.5, float('inf')],
                labels=['D-', 'D', 'C', 'B', 'A']
            )
        
        # 统计评级分布
        rating_counts = df['rating'].value_counts().sort_index()
        
        # 绘图
        plt.figure(figsize=(10, 6))
        bars = plt.bar(rating_counts.index, rating_counts.values, color=['red', 'orange', 'gray', 'lightblue', 'blue'])
        plt.title(title)
        plt.xlabel('Rating')
        plt.ylabel('Count')
        
        # 添加数量标签
        for bar in bars:
            height = bar.get_height()
            plt.text(bar.get_x() + bar.get_width()/2., height,
                    f'{height}',
                    ha='center', va='bottom')
        
        plt.tight_layout()
        plt.savefig(output_path, dpi=300)
        plt.close()
    
    def export_excel_report(self, output_dir, params=None, metrics=None, model_object=None):
        """生成Excel格式的综合报告"""
        if self.result is None:
            raise ValueError("请提供模型结果")
            
        # 确保目录存在
        os.makedirs(output_dir, exist_ok=True)
        
        # 文件名前缀
        prefix = f"{self.model_name}_" if self.model_name else ""
        
        # 创建综合Excel文件
        excel_path = os.path.join(output_dir, f"{prefix}value_added_report.xlsx")
        
        try:
            # 显式指定引擎和模式
            with pd.ExcelWriter(excel_path, engine='openpyxl', mode='w') as writer:
                # 写入说明表
                description = pd.DataFrame([
                    ["模型名称", self.model_name or "未指定"],
                    ["生成时间", datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
                    ["说明", "本报告包含各实体的增值效应评估结果"]
                ], columns=["项目", "内容"])
                
                description.to_excel(writer, sheet_name="说明", index=False)
                
                # 写入评估指标（如果有）
                if metrics is not None:
                    # 转换成简单的DataFrame格式
                    metrics_df = pd.DataFrame([{k: v for k, v in metrics.items() if isinstance(v, (int, float, str))}])
                    metrics_df.to_excel(writer, sheet_name="模型评估指标")
                
                # 写入参数（如果有）
                if params is not None and hasattr(params, 'index'):
                    params_df = pd.DataFrame({'参数': params.index, '数值': params.values})
                    params_df.to_excel(writer, sheet_name="模型参数", index=False)
                
                # 写入各层级增值效应（包括学校和班级名称）
                for level in ['schools', 'classes']:
                    if level in self.result and not self.result[level].empty:
                        df = self.result[level].copy()
                        
                        # 添加学校/班级名称列（如果有映射数据）
                        try:
                            # 尝试从模型对象获取mappings
                            if hasattr(model_object, 'mappings') and model_object.mappings:
                                entity_map = model_object.mappings.get(level, {})
                                if entity_map:
                                    df['名称'] = df['entity_id'].map(
                                        lambda x: entity_map.get(str(x), str(x))
                                    )
                        except Exception as e:
                            logger.warning(f"无法添加实体名称: {str(e)}")
                        
                        # 设置友好的列名
                        column_rename = {
                            'entity_id': '实体ID',
                            'mean': '增值效应',
                            'std_err': '标准误',
                            'ci_lower': '置信区间下限',
                            'ci_upper': '置信区间上限'
                        }
                        
                        # 只重命名存在的列
                        for old_name, new_name in column_rename.items():
                            if old_name in df.columns:
                                df.rename(columns={old_name: new_name}, inplace=True)
                        
                        # 如果没有名称列，尝试从实体ID创建
                        if '名称' not in df.columns:
                            entity_type = '学校' if level == 'schools' else '班级'
                            df['名称'] = df['实体ID'].apply(lambda x: f"{entity_type}{x}")
                        
                        # 调整列顺序，将ID和名称放在前面
                        cols = df.columns.tolist()
                        for col in ['名称', '实体ID']:
                            if col in cols:
                                cols.remove(col)
                                cols.insert(0, col)
                        df = df[cols]
                        
                        level_name = {'schools': '学校', 'classes': '班级'}.get(level, level)
                        df.to_excel(writer, sheet_name=f"{level_name} 增值效应")
        
        except Exception as e:
            logger.error(f"创建Excel报告失败: {str(e)}")
            # 尝试创建简单的CSV文件作为备份
            csv_path = os.path.join(output_dir, f"{prefix}value_added_report.csv")
            for level in ['schools', 'classes']:
                if level in self.result and not self.result[level].empty:
                    self.result[level].to_csv(csv_path)
                    return csv_path
        
        # 验证生成的Excel文件
        if verify_excel_file(excel_path):
            logger.info(f"成功创建Excel报告: {excel_path}")
        else:
            logger.warning(f"Excel报告可能无法正常打开: {excel_path}")
        
        return excel_path
    
    def save_complete_results(self, output_dir, model_object=None):
        """
        保存完整结果（图表、CSV和Excel格式）
        
        Args:
            output_dir: 输出目录
            model_object: 模型对象，用于获取参数和指标
            
        Returns:
            dict: 所有保存的文件路径
        """
        # 先生成可视化结果
        saved_paths = self.visualize(output_dir)
        
        # 如果有模型对象，获取其参数和指标
        params = getattr(model_object, 'params', None) if model_object else None
        metrics = getattr(model_object, 'metrics', None) if model_object else None
        
        # 生成Excel报告
        excel_report = self.export_excel_report(output_dir, params, metrics, model_object)
        saved_paths['excel_report'] = excel_report
        
        # 保存CSV格式数据
        for level in ['schools', 'classes']:
            if level in self.result and not self.result[level].empty:
                prefix = f"{self.model_name}_" if self.model_name else ""
                csv_path = os.path.join(output_dir, f"{prefix}{level}_value_added.csv")
                self.result[level].to_csv(csv_path, index=False)
                saved_paths[f"{level}_csv"] = csv_path
        
        return saved_paths

    # 在ValueAddedVisualizer类中添加展示非线性潜力评估结果的方法

    def visualize_student_potential(self, evaluator, student_id=None, output_dir=None, show_plots=True):
        """
        可视化学生潜力评估结果
        
        Args:
            evaluator: NonlinearStudentPotentialEvaluator实例
            student_id: 指定学生ID，如果为None则显示总体分布
            output_dir: 输出目录，如果为None则不保存图表
            show_plots: 是否显示图表
            
        Returns:
            dict: 包含图表对象的字典
        """
        import matplotlib.pyplot as plt
        import seaborn as sns
        
        # 确保评估已完成
        if evaluator.potential_scores is None:
            evaluator.evaluate_potential()
        
        if evaluator.growth_patterns is None:
            evaluator.analyze_growth_patterns()
        
        # 创建保存图表的字典
        plots = {}
        
        # 设置图表样式
        plt.style.use('seaborn-whitegrid')
        sns.set_palette('muted')
        
        # 1. 潜力分数分布图
        fig1, ax1 = plt.subplots(figsize=(10, 6))
        sns.histplot(evaluator.potential_scores['potential_score_norm'], 
                    bins=20, kde=True, ax=ax1)
        ax1.set_title('学生潜力分数分布')
        ax1.set_xlabel('潜力分数')
        ax1.set_ylabel('学生数量')
        # 如果指定了学生，在图上标记该学生位置
        if student_id:
            student_score = evaluator.potential_scores[
                evaluator.potential_scores['student_id'] == student_id
            ]['potential_score_norm'].values
            if len(student_score) > 0:
                ax1.axvline(student_score[0], color='red', linestyle='--', 
                           label=f'学生 {student_id}')
                ax1.legend()
        plots['potential_distribution'] = fig1
        
        # 2. 潜力评级分布图
        fig2, ax2 = plt.subplots(figsize=(10, 6))
        rating_counts = evaluator.potential_scores['potential_rating'].value_counts().sort_index()
        sns.barplot(x=rating_counts.index, y=rating_counts.values, ax=ax2)
        ax2.set_title('学生潜力评级分布')
        ax2.set_xlabel('潜力评级')
        ax2.set_ylabel('学生数量')
        # 如果指定了学生，高亮该学生评级
        if student_id:
            student_rating = evaluator.potential_scores[
                evaluator.potential_scores['student_id'] == student_id
            ]['potential_rating'].values
            if len(student_rating) > 0:
                rating_idx = list(rating_counts.index).index(student_rating[0])
                ax2.patches[rating_idx].set_facecolor('red')
                ax2.text(rating_idx, 
                        rating_counts[student_rating[0]] / 2, 
                        f'学生\n{student_id}', 
                        ha='center',
                        color='white',
                        fontweight='bold')
        plots['rating_distribution'] = fig2
        
        # 3. 成长模式分布图
        fig3, ax3 = plt.subplots(figsize=(12, 6))
        pattern_counts = evaluator.growth_patterns['growth_pattern'].value_counts()
        sns.barplot(x=pattern_counts.index, y=pattern_counts.values, ax=ax3)
        ax3.set_title('学习成长模式分布')
        ax3.set_xlabel('成长模式')
        ax3.set_ylabel('学生数量')
        ax3.set_xticklabels(ax3.get_xticklabels(), rotation=45, ha='right')
        # 如果指定了学生，高亮该学生模式
        if student_id:
            student_pattern = evaluator.growth_patterns[
                evaluator.growth_patterns['student_id'] == student_id
            ]['growth_pattern'].values
            if len(student_pattern) > 0:
                pattern_idx = list(pattern_counts.index).index(student_pattern[0])
                ax3.patches[pattern_idx].set_facecolor('red')
                ax3.text(pattern_idx, 
                        pattern_counts[student_pattern[0]] / 2, 
                        f'学生\n{student_id}', 
                        ha='center',
                        color='white', 
                        fontweight='bold')
        plots['pattern_distribution'] = fig3
        
        # 4. 如果指定了学生ID，绘制该学生成绩曲线
        if student_id:
            report = evaluator.get_student_report(student_id)
            if 'error' not in report:
                # 获取成绩历史
                scores_history = np.array(report['scores_history'])
                x = np.arange(len(scores_history))
                
                fig4, ax4 = plt.subplots(figsize=(12, 6))
                ax4.plot(scores_history[:, 0], scores_history[:, 1], 'o-', 
                        label='实际成绩')
                ax4.set_title(f'学生 {student_id} 成绩曲线与成长模式')
                ax4.set_xlabel('考试ID')
                ax4.set_ylabel('标准分数')
                
                # 添加成长模式信息
                if report['best_growth_model'] != '数据不足':
                    model_info = (f"最佳拟合模型: {report['best_growth_model']}\n"
                                 f"成长模式: {report['growth_pattern']}\n"
                                 f"拟合度: {report['model_fit_quality']:.2f}")
                    ax4.text(0.02, 0.05, model_info, 
                            transform=ax4.transAxes,
                            bbox=dict(facecolor='white', alpha=0.7))
                
                # 添加潜力评估信息
                potential_info = (f"潜力评级: {report['potential_rating']}\n"
                                 f"学习阶段: {report['learning_phase']}")
                ax4.text(0.02, 0.85, potential_info, 
                        transform=ax4.transAxes,
                        bbox=dict(facecolor='white', alpha=0.7))
                
                plots['student_curve'] = fig4
        
        # 保存图表
        if output_dir:
            import os
            os.makedirs(output_dir, exist_ok=True)
            
            for name, fig in plots.items():
                filename = f"{name}.png"
                if student_id:
                    filename = f"{student_id}_{name}.png"
                fig.savefig(os.path.join(output_dir, filename), dpi=100, bbox_inches='tight')
        
        # 显示图表
        if show_plots:
            plt.show()
        else:
            plt.close('all')
        
        return plots

    def generate_student_potential_report(self, evaluator, student_id, output_dir=None, include_plots=True):
        """
        生成学生潜力评估报告
        
        Args:
            evaluator: NonlinearStudentPotentialEvaluator实例
            student_id: 学生ID
            output_dir: 输出目录，如果不为None则保存报告
            include_plots: 是否包含可视化图表
            
        Returns:
            str: HTML格式的报告内容
        """
        # 获取学生报告
        report = evaluator.get_student_report(student_id)
        
        if 'error' in report:
            return f"<h2>错误</h2><p>{report['error']}</p>"
        
        # 准备报告模板
        html = f"""
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>学生 {student_id} 潜力评估报告</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 1000px; margin: 0 auto; padding: 20px; }}
                h1, h2, h3 {{ color: #2c3e50; }}
                .card {{ border: 1px solid #ddd; border-radius: 8px; padding: 15px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                .rating {{ font-size: 24px; font-weight: bold; }}
                .rating-A-plus {{ color: #1e88e5; }}
                .rating-A {{ color: #43a047; }}
                .rating-B {{ color: #7cb342; }}
                .rating-C {{ color: #ffb300; }}
                .rating-D {{ color: #e53935; }}
                .rating-E {{ color: #d32f2f; }}
                .info-row {{ display: flex; flex-wrap: wrap; }}
                .info-item {{ flex: 1; min-width: 200px; margin: 5px; }}
                .recommendations {{ background-color: #f5f5f5; padding: 10px; border-radius: 5px; }}
                .plot-container {{ text-align: center; margin: 20px 0; }}
                .plot-container img {{ max-width: 100%; height: auto; border: 1px solid #ddd; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <h1>学生潜力评估报告</h1>
            
            <div class="card">
                <h2>基本信息</h2>
                <div class="info-row">
                    <div class="info-item">
                        <p><strong>学生ID:</strong> {report['student_id']}</p>
                        <p><strong>姓名:</strong> {report['name']}</p>
                    </div>
                    <div class="info-item">
                        <p><strong>学校:</strong> {report['school']}</p>
                        <p><strong>班级:</strong> {report['class']}</p>
                        <p><strong>年级:</strong> {report['grade']}</p>
                    </div>
                    <div class="info-item">
                        <p><strong>考试次数:</strong> {report['exam_count']}</p>
                        <p><strong>起始成绩:</strong> {report['first_score']:.1f}</p>
                        <p><strong>最新成绩:</strong> {report['latest_score']:.1f}</p>
                        <p><strong>总成长:</strong> {report['total_growth']:.1f}</p>
                    </div>
                </div>
            </div>
            
            <div class="card">
                <h2>潜力评估</h2>
                <div class="info-row">
                    <div class="info-item">
                        <p><strong>潜力分数:</strong> {report['potential_score']:.1f}</p>
                        <p><strong>潜力评级:</strong> <span class="rating rating-{report['potential_rating'].replace('+', '-plus')}">{report['potential_rating']}</span></p>
                    </div>
                    <div class="info-item">
                        <p><strong>成长模式:</strong> {report['growth_pattern']}</p>
                        <p><strong>最佳拟合模型:</strong> {report['best_growth_model']}</p>
                        <p><strong>模型拟合度:</strong> {report['model_fit_quality']:.2f if report['model_fit_quality'] is not None else '未知'}</p>
                    </div>
                </div>
            </div>
            
            <div class="card">
                <h2>学习指标</h2>
                <div class="info-row">
                    <div class="info-item">
                        <p><strong>平均成长率:</strong> {report['avg_growth_rate']:.2f if report['avg_growth_rate'] is not None else '未知'}</p>
                        <p><strong>近期势头:</strong> {report['momentum']:.2f if report['momentum'] is not None else '未知'}</p>
                    </div>
                    <div class="info-item">
                        <p><strong>突破次数:</strong> {report['breakthrough_count']}</p>
                        <p><strong>韧性指数:</strong> {report['resilience']:.2f if report['resilience'] is not None else '未知'}</p>
                    </div>
                </div>
            </div>
            
            <div class="card">
                <h2>学习阶段分析</h2>
                <p><strong>当前学习阶段:</strong> {report['learning_phase']}</p>
                <div class="recommendations">
                    <h3>学习建议:</h3>
                    <ul>
                        {''.join(f"<li>{rec}</li>" for rec in report['phase_recommendations'])}
                    </ul>
                </div>
            </div>
        """
        
        # 如果包含图表并且指定了输出目录
        if include_plots and output_dir:
            # 生成并保存图表
            plots = self.visualize_student_potential(evaluator, student_id, output_dir, show_plots=False)
            
            # 添加图表到报告
            html += """
            <div class="card">
                <h2>可视化分析</h2>
            """
            
            # 添加各图表
            if 'student_curve' in plots:
                img_path = f"{student_id}_student_curve.png"
                html += f"""
                <div class="plot-container">
                    <h3>学习曲线分析</h3>
                    <img src="{img_path}" alt="学习曲线">
                </div>
                """
                
            if 'potential_distribution' in plots:
                img_path = f"{student_id}_potential_distribution.png"
                html += f"""
                <div class="plot-container">
                    <h3>潜力分数分布</h3>
                    <img src="{img_path}" alt="潜力分数分布">
                </div>
                """
                
            if 'rating_distribution' in plots:
                img_path = f"{student_id}_rating_distribution.png"
                html += f"""
                <div class="plot-container">
                    <h3>潜力评级分布</h3>
                    <img src="{img_path}" alt="潜力评级分布">
                </div>
                """
                
            html += """
            </div>
            """
        
        # 结束HTML
        html += """
        </body>
        </html>
        """
        
        # 保存报告
        if output_dir:
            import os
            os.makedirs(output_dir, exist_ok=True)
            
            report_path = os.path.join(output_dir, f"{student_id}_potential_report.html")
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(html)
        
        return html

#############################################
# 第四部分: 模型实现
#############################################

class FrequentistValueAddedModel(BaseValueAddedModel):
    """
    频率派多层次增值模型实现
    
    基于statsmodels的混合线性模型，使用最大似然估计方法。
    该模型支持嵌套结构的数据（如学生-班级-学校），通过随机效应捕捉各层级的增值效应。
    
    Args:
        data: 建模数据
        formula: 可选的自定义模型公式
    """
    
    def __init__(self, data=None, formula=None):
        """
        初始化频率派多层次模型
        
        Args:
            data: 建模数据
            formula: 可选的自定义模型公式
        """
        super().__init__(data)
        self.custom_formula = formula
    
    def _validate_data(self):
        """
        验证频率派模型所需数据
        
        Raises:
            ValueError: 如果缺少必要字段
        """
        required_fields = ['prior_score', 'standard_score', 'student_idx']
        missing_fields = [f for f in required_fields if f not in self.data.columns]
        if missing_fields:
            raise ValueError(f"数据缺少频率派模型所需字段: {missing_fields}")
    
    def _build_model(self):
        """
        构建频率派多层次线性模型
        
        根据数据中可用的层级变量构建合适的混合线性模型
        """
        # 准备模型数据
        model_data = self.data.copy()
        
        # 使用自定义公式或构建默认公式
        if self.custom_formula:
            formula = self.custom_formula
        else:
            # 根据数据中的可用变量构建公式
            if 'school_idx' in model_data.columns and 'class_idx' in model_data.columns:
                formula = "standard_score ~ prior_score + (1|school_idx) + (1|class_idx)"
            elif 'class_idx' in model_data.columns:
                formula = "standard_score ~ prior_score + (1|class_idx)"
            else:
                formula = "standard_score ~ prior_score"
        
        # 创建模型
        self.model = smf.mixedlm(formula, model_data, groups=model_data["student_idx"])
    
    def _fit_model(self):
        """
        拟合频率派模型
        
        计算模型参数和评估指标
        """
        self.result = self.model.fit()
        
        # 计算模型评估指标
        self.metrics = {
            'aic': self.result.aic,
            'bic': self.result.bic,
            'r_squared': self.result.rsquared,
            'r_squared_adj': self.result.rsquared_adj,
            'log_likelihood': self.result.llf
        }
        
        logger.info(f"频率派模型拟合完成: R²={self.metrics['r_squared']:.4f}, AIC={self.metrics['aic']:.2f}")
    
    def _predict_impl(self, new_data):
        """
        频率派模型预测实现
        
        Args:
            new_data: 用于预测的数据
            
        Returns:
            ndarray: 预测结果
        """
        return self.result.predict(new_data)
    
    def _calculate_value_added_impl(self):
        """
        计算频率派模型的增值效应
        
        Returns:
            dict: 包含各层级增值效应的字典
        """
        # 提取随机效应
        re_results = self.result.random_effects
        
        # 班级增值效应
        if 'class_idx' in self.data.columns:
            class_effects = pd.DataFrame(columns=['mean', 'std', 'lower', 'upper'])
            for class_id, effect in enumerate(re_results.values()):
                effect_value = effect.get(1, [0])[0]
                class_effects.loc[class_id] = [effect_value, 0, effect_value, effect_value]
                
            # 添加班级ID映射
            if 'norm_class_group' in self.data.columns:
                class_map = self.data.groupby('class_idx')['norm_class_group'].first().to_dict()
                class_effects.index = class_effects.index.map(lambda x: class_map.get(x, x))
        else:
            class_effects = pd.DataFrame()
        
        # 学校增值效应（如果有）
        if 'school_idx' in self.data.columns:
            school_effects = pd.DataFrame(columns=['mean', 'std', 'lower', 'upper'])
            for school_id, effect in enumerate(re_results.values()):
                effect_value = effect.get(2, [0])[0] if len(effect) > 1 else 0
                school_effects.loc[school_id] = [effect_value, 0, effect_value, effect_value]
                
            # 添加学校ID映射
            if 'school_id' in self.data.columns:
                school_map = self.data.groupby('school_idx')['school_id'].first().to_dict()
                school_effects.index = school_effects.index.map(lambda x: school_map.get(x, x))
        else:
            school_effects = pd.DataFrame()
        
        return {
            'schools': school_effects,
            'classes': class_effects,
            'students': pd.DataFrame()  # 此模型未计算学生层面效应
        }
    
    def save_results(self, output_dir, filename_prefix="frequentist_value_added"):
        """
        保存频率派模型结果
        
        Args:
            output_dir: 输出目录
            filename_prefix: 文件名前缀
            
        Returns:
            dict: 保存的文件路径
        """
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        
        # 保存结果
        saved_paths = {}
        
        # 保存模型摘要
        summary_path = os.path.join(output_dir, f"{filename_prefix}_summary.txt")
        with open(summary_path, 'w') as f:
            f.write(str(self.result.summary()))
        saved_paths["summary"] = summary_path
        
        # 保存参数
        params_path = os.path.join(output_dir, f"{filename_prefix}_parameters.csv")
        pd.DataFrame({'parameter': self.result.params.index, 'value': self.result.params.values}).to_csv(params_path, index=False)
        saved_paths["parameters"] = params_path
        
        # 保存增值效应
        value_added = self.calculate_value_added()
        for level, df in value_added.items():
            if not df.empty:
                va_path = os.path.join(output_dir, f"{filename_prefix}_{level}_value_added.csv")
                df.to_csv(va_path)
                saved_paths[f"{level}_value_added"] = va_path
        
        # 保存评估指标
        metrics_path = os.path.join(output_dir, f"{filename_prefix}_metrics.json")
        with open(metrics_path, 'w') as f:
            json.dump(self.metrics, f, indent=4)
        saved_paths["metrics"] = metrics_path
        
        return saved_paths


class BayesianValueAddedModel(BaseValueAddedModel):
    """
    贝叶斯多层次增值模型实现
    
    使用PyMC进行全贝叶斯推断，通过MCMC采样获得参数和效应的后验分布。
    模型捕获了学生、班级、学校各个层级的随机效应，并提供了不确定性估计。
    
    Args:
        data: 建模数据
        mcmc_samples: MCMC采样次数
        tune: MCMC调整步数
        random_seed: 随机种子
    """
    
    def __init__(self, data=None, mcmc_samples=1000, tune=500, random_seed=42):
        """
        初始化贝叶斯多层次模型
        
        Args:
            data: 建模数据
            mcmc_samples: MCMC采样次数
            tune: MCMC调整步数
            random_seed: 随机种子
        """
        super().__init__(data)
        self.mcmc_samples = mcmc_samples
        self.tune = tune
        self.random_seed = random_seed
        self.trace = None
        self.pymc_model = None
    
    def _validate_data(self):
        """
        验证贝叶斯模型所需数据
        
        确保数据符合由ValueAddedDataProcessor预处理后的标准格式
        
        Raises:
            ValueError: 如果缺少必要字段
        """
        # 所有模型共同需要的基础字段
        required_fields = ['prior_score', 'standard_score', 'student_idx']
        
        # 模型特定需要的额外字段
        model_specific_fields = []
        
        # 例如，贝叶斯模型可能还需要
        if isinstance(self, BayesianValueAddedModel):
            model_specific_fields.extend(['class_idx', 'school_idx'])
        
        # TVAM模型需要实体字段
        if isinstance(self, TVAMValueAddedModel):
            model_specific_fields.append(f"{self.entity_type}_idx")
        
        # 合并所有必要字段
        all_required_fields = required_fields + model_specific_fields
        
        # 检查缺失字段
        missing_fields = [f for f in all_required_fields if f not in self.data.columns]
        if missing_fields:
            raise ValueError(f"数据缺少{self.__class__.__name__}所需字段: {missing_fields}")
    
    def _build_model(self):
        """
        构建贝叶斯多层次模型
        
        使用PyMC创建分层贝叶斯模型，包括固定效应和随机效应
        """
        # 准备数据
        model_data = self.data.copy()
        prior_score = model_data['prior_score'].values
        standard_score = model_data['standard_score'].values
        student_idx = model_data['student_idx'].values
        class_idx = model_data['class_idx'].values
        
        # 检查是否有学校层级
        has_school = 'school_idx' in model_data.columns
        if has_school:
            school_idx = model_data['school_idx'].values
        
        # 创建PyMC模型
        with pm.Model() as self.pymc_model:
            # 先验分布
            intercept = pm.Normal('intercept', mu=0, sigma=10)
            beta_prior = pm.Normal('beta_prior', mu=1, sigma=1)
            
            # 随机效应标准差
            sigma_student = pm.HalfCauchy('sigma_student', beta=5)
            sigma_class = pm.HalfCauchy('sigma_class', beta=5)
            
            if has_school:
                sigma_school = pm.HalfCauchy('sigma_school', beta=5)
                # 学校随机效应
                school_effects = pm.Normal('school_effects', mu=0, sigma=sigma_school, shape=len(np.unique(school_idx)))
            
            # 班级随机效应
            class_effects = pm.Normal('class_effects', mu=0, sigma=sigma_class, shape=len(np.unique(class_idx)))
            
            # 学生随机效应
            student_effects = pm.Normal('student_effects', mu=0, sigma=sigma_student, shape=len(np.unique(student_idx)))
            
            # 残差标准差
            sigma_e = pm.HalfCauchy('sigma_e', beta=5)
            
            # 构建线性预测
            mu = intercept + beta_prior * prior_score
            mu = mu + student_effects[student_idx]
            mu = mu + class_effects[class_idx]
            
            if has_school:
                mu = mu + school_effects[school_idx]
            
            # 似然函数
            y = pm.Normal('y', mu=mu, sigma=sigma_e, observed=standard_score)
    
    def _fit_model(self):
        """
        拟合贝叶斯模型
        
        使用MCMC方法进行后验采样
        """
        with self.pymc_model:
            # 使用NUTS采样器
            self.trace = pm.sample(
                draws=self.mcmc_samples, 
                tune=self.tune,
                random_seed=self.random_seed,
                return_inferencedata=True
            )
        
        # 计算模型评估指标
        self.metrics = {
            'loo': float(az.loo(self.trace, scale="deviance").loo),
            'waic': float(az.waic(self.trace, scale="deviance").waic),
            'r_squared': float(self._calculate_r_squared()),
            'student_effects_std': float(np.std(self.trace.posterior.student_effects.mean(dim=("chain", "draw")).values)),
            'class_effects_std': float(np.std(self.trace.posterior.class_effects.mean(dim=("chain", "draw")).values))
        }
        
        if 'school_idx' in self.data.columns:
            self.metrics['school_effects_std'] = float(np.std(self.trace.posterior.school_effects.mean(dim=("chain", "draw")).values))
        
        logger.info(f"贝叶斯模型拟合完成: R²={self.metrics['r_squared']:.4f}, WAIC={self.metrics['waic']:.2f}")
    
    def _calculate_r_squared(self):
        """
        计算贝叶斯R²
        
        Returns:
            float: 贝叶斯R²值
        """
        # 获取参数后验均值
        intercept = float(self.trace.posterior.intercept.mean())
        beta_prior = float(self.trace.posterior.beta_prior.mean())
        
        # 计算固定效应部分预测值
        fixed_pred = intercept + beta_prior * self.data['prior_score'].values
        
        # 计算残差平方和
        residuals = self.data['standard_score'].values - fixed_pred
        rss = np.sum(residuals ** 2)
        
        # 计算总平方和
        total_mean = np.mean(self.data['standard_score'])
        tss = np.sum((self.data['standard_score'].values - total_mean) ** 2)
        
        # 计算R²
        r_squared = 1 - (rss / tss)
        return r_squared
    
    def _predict_impl(self, new_data):
        """
        贝叶斯模型预测实现
        
        Args:
            new_data: 用于预测的数据
            
        Returns:
            ndarray: 预测结果
        """
        # 获取参数后验均值
        intercept = float(self.trace.posterior.intercept.mean())
        beta_prior = float(self.trace.posterior.beta_prior.mean())
        
        # 计算固定效应部分预测值
        predictions = intercept + beta_prior * new_data['prior_score'].values
        
        # 如果新数据包含学生、班级、学校索引，添加随机效应
        if 'student_idx' in new_data.columns:
            student_effects = self.trace.posterior.student_effects.mean(dim=("chain", "draw")).values
            for i, student_idx in enumerate(new_data['student_idx']):
                if student_idx < len(student_effects):
                    predictions[i] += student_effects[student_idx]
        
        if 'class_idx' in new_data.columns:
            class_effects = self.trace.posterior.class_effects.mean(dim=("chain", "draw")).values
            for i, class_idx in enumerate(new_data['class_idx']):
                if class_idx < len(class_effects):
                    predictions[i] += class_effects[class_idx]
        
        if 'school_idx' in new_data.columns and hasattr(self.trace.posterior, 'school_effects'):
            school_effects = self.trace.posterior.school_effects.mean(dim=("chain", "draw")).values
            for i, school_idx in enumerate(new_data['school_idx']):
                if school_idx < len(school_effects):
                    predictions[i] += school_effects[school_idx]
        
        return predictions
    
    def _calculate_value_added_impl(self):
        """
        计算贝叶斯模型的增值效应
        
        Returns:
            dict: 包含各层级增值效应的字典
        """
        # 班级增值效应
        class_value_added = az.summary(self.trace.posterior.class_effects)
        class_value_added = class_value_added.rename(columns={'mean': 'mean', 'sd': 'std', 
                                                     'hdi_3%': 'lower', 'hdi_97%': 'upper'})
        
        # 将索引映射回原始ID
        if 'norm_class_group' in self.data.columns:
            class_map = self.data.groupby('class_idx')['norm_class_group'].first().to_dict()
            class_value_added.index = class_value_added.index.map(lambda x: class_map.get(x, x))
        
        # 学校增值效应
        if 'school_idx' in self.data.columns:
            school_value_added = az.summary(self.trace.posterior.school_effects)
            school_value_added = school_value_added.rename(columns={'mean': 'mean', 'sd': 'std', 
                                                          'hdi_3%': 'lower', 'hdi_97%': 'upper'})
            
            # 将索引映射回原始ID
            if 'school_id' in self.data.columns:
                school_map = self.data.groupby('school_idx')['school_id'].first().to_dict()
                school_value_added.index = school_value_added.index.map(lambda x: school_map.get(x, x))
        else:
            school_value_added = pd.DataFrame()
        
        # 学生增值效应
        student_value_added = az.summary(self.trace.posterior.student_effects)
        student_value_added = student_value_added.rename(columns={'mean': 'mean', 'sd': 'std', 
                                                        'hdi_3%': 'lower', 'hdi_97%': 'upper'})
        
        # 将索引映射回原始ID
        if 'student_id' in self.data.columns:
            student_map = self.data.groupby('student_idx')['student_id'].first().to_dict()
            student_value_added.index = student_value_added.index.map(lambda x: student_map.get(x, x))
        
        return {
            'schools': school_value_added,
            'classes': class_value_added,
            'students': student_value_added
        }
    
    def save_results(self, output_dir, filename_prefix="bayesian_value_added"):
        """
        保存贝叶斯模型结果
        
        Args:
            output_dir: 输出目录
            filename_prefix: 文件名前缀
            
        Returns:
            dict: 保存的文件路径
        """
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        
        # 保存结果
        saved_paths = {}
        
        # 保存模型摘要
        summary_path = os.path.join(output_dir, f"{filename_prefix}_summary.csv")
        az.summary(self.trace).to_csv(summary_path)
        saved_paths["summary"] = summary_path
        
        # 保存模型跟踪
        trace_path = os.path.join(output_dir, f"{filename_prefix}_trace.nc")
        self.trace.to_netcdf(trace_path)
        saved_paths["trace"] = trace_path
        
        # 保存后验分布图
        post_path = os.path.join(output_dir, f"{filename_prefix}_posterior.png")
        az.plot_posterior(self.trace, var_names=['intercept', 'beta_prior'])
        plt.tight_layout()
        plt.savefig(post_path, dpi=300)
        saved_paths["posterior_plot"] = post_path
        
        # 保存增值效应
        value_added = self.calculate_value_added()
        for level, df in value_added.items():
            if not df.empty:
                va_path = os.path.join(output_dir, f"{filename_prefix}_{level}_value_added.csv")
                df.to_csv(va_path)
                saved_paths[f"{level}_value_added"] = va_path
        
        # 保存评估指标
        metrics_path = os.path.join(output_dir, f"{filename_prefix}_metrics.json")
        with open(metrics_path, 'w') as f:
            json.dump(self.metrics, f, indent=4)
        saved_paths["metrics"] = metrics_path
        
        return saved_paths


class FixedEffectsValueAddedModel(BaseValueAddedModel):
    """
    固定效应增值模型实现
    
    使用固定效应来表示不同学校/班级的增值效应，适用于面板数据分析。
    该模型将学校/班级视为固定效应，包含在模型中作为虚拟变量。
    
    Args:
        data: 建模数据
        entity_vars: 实体变量列表，如['school_idx', 'class_idx']
        covariates: 协变量列表
    """
    
    def __init__(self, data=None, entity_vars=None, covariates=None):
        """
        初始化固定效应模型
        
        Args:
            data: 建模数据
            entity_vars: 实体变量列表，例如['school_idx', 'class_idx']
            covariates: 额外控制变量，例如['gender', 'ses']
        """
        super().__init__(data)
        self.entity_vars = entity_vars or ['class_idx']
        self.covariates = covariates or []
    
    def _validate_data(self):
        """
        验证固定效应模型所需数据
        
        Raises:
            ValueError: 如果缺少必要字段
        """
        required_fields = ['prior_score', 'standard_score'] + self.entity_vars
        missing_fields = [f for f in required_fields if f not in self.data.columns]
        if missing_fields:
            raise ValueError(f"数据缺少固定效应模型所需字段: {missing_fields}")
        
        # 验证协变量
        missing_covariates = [f for f in self.covariates if f not in self.data.columns]
        if missing_covariates:
            logger.warning(f"数据缺少指定的协变量: {missing_covariates}")
            # 从协变量列表中移除缺失的字段
            self.covariates = [f for f in self.covariates if f not in missing_covariates]
    
    def _build_model(self):
        """
        构建固定效应模型
        
        为每个实体变量创建虚拟变量，构建包含固定效应的OLS模型
        """
        # 准备建模数据
        model_data = self.data.copy()
        
        # 创建虚拟变量
        for entity in self.entity_vars:
            dummies = pd.get_dummies(model_data[entity], prefix=entity, drop_first=True)
            model_data = pd.concat([model_data, dummies], axis=1)
        
        # 构建公式
        formula_parts = ["standard_score ~ prior_score"]
        
        # 添加协变量
        if self.covariates:
            formula_parts[0] += " + " + " + ".join(self.covariates)
        
        # 添加固定效应
        for entity in self.entity_vars:
            entity_dummies = [col for col in model_data.columns if col.startswith(f"{entity}_")]
            if entity_dummies:
                formula_parts.append(" + ".join(entity_dummies))
        
        formula = " + ".join(formula_parts)
        
        # 使用statsmodels的OLS
        self.X = model_data[formula.split("~")[1].strip().split(" + ")]
        self.y = model_data['standard_score']
        
        # 创建模型
        self.model = sm.OLS(self.y, sm.add_constant(self.X))
    
    def _fit_model(self):
        """
        拟合固定效应模型
        
        使用OLS方法估计参数，计算模型评估指标
        """
        self.results = self.model.fit()
        
        # 计算评估指标
        self.metrics = {
            'r_squared': self.results.rsquared,
            'r_squared_adj': self.results.rsquared_adj,
            'aic': self.results.aic,
            'bic': self.results.bic,
            'f_statistic': self.results.fvalue,
            'f_pvalue': self.results.f_pvalue,
            'num_obs': self.results.nobs
        }
        
        logger.info(f"固定效应模型拟合完成: R²={self.metrics['r_squared']:.4f}, 调整R²={self.metrics['r_squared_adj']:.4f}")
    
    def _predict_impl(self, new_data):
        """
        固定效应模型预测实现
        
        Args:
            new_data: 用于预测的数据
            
        Returns:
            ndarray: 预测结果
        """
        # 准备预测数据
        pred_data = new_data.copy()
        
        # 创建虚拟变量
        for entity in self.entity_vars:
            dummies = pd.get_dummies(pred_data[entity], prefix=entity, drop_first=True)
            pred_data = pd.concat([pred_data, dummies], axis=1)
        
        # 提取所需的预测变量
        X_pred = pred_data[[col for col in self.X.columns]]
        
        # 处理新数据中可能缺少的列
        missing_cols = set(self.X.columns) - set(X_pred.columns)
        for col in missing_cols:
            X_pred[col] = 0
        
        X_pred = X_pred[self.X.columns]  # 确保列顺序一致
        
        # 预测
        return self.results.predict(sm.add_constant(X_pred))
    
    def _calculate_value_added_impl(self):
        """
        计算固定效应模型的增值效应
        
        Returns:
            dict: 包含各层级增值效应的字典
        """
        # 提取固定效应系数
        params = self.results.params.copy()
        
        # 分层级提取固定效应
        level_effects = {}
        
        for entity in self.entity_vars:
            entity_cols = [col for col in params.index if col.startswith(f"{entity}_")]
            
            if entity_cols:
                # 基准类别的效应设为0
                effects = pd.DataFrame(columns=['mean', 'std', 'lower', 'upper'])
                effects.loc[0] = [0, 0, 0, 0]  # 基准类别
                
                # 提取其他类别的系数
                for col in entity_cols:
                    idx = int(col.split('_')[1])
                    coef = params[col]
                    std_err = self.results.bse[col]
                    ci = self.results.conf_int().loc[col]
                    effects.loc[idx] = [coef, std_err, ci[0], ci[1]]
                
                # 添加实体ID映射
                if entity == 'class_idx' and 'norm_class_group' in self.data.columns:
                    class_map = self.data.groupby(entity)['norm_class_group'].first().to_dict()
                    effects.index = effects.index.map(lambda x: class_map.get(x, x))
                    level_effects['classes'] = effects
                
                elif entity == 'school_idx' and 'school_id' in self.data.columns:
                    school_map = self.data.groupby(entity)['school_id'].first().to_dict()
                    effects.index = effects.index.map(lambda x: school_map.get(x, x))
                    level_effects['schools'] = effects
                
                else:
                    entity_name = entity.replace('_idx', 's')
                    level_effects[entity_name] = effects
        
        # 确保返回值包含所有必需的键
        result = {
            'schools': level_effects.get('schools', pd.DataFrame()),
            'classes': level_effects.get('classes', pd.DataFrame()),
            'students': pd.DataFrame()  # 固定效应模型通常不计算学生层面效应
        }
        
        return result
    
    def save_results(self, output_dir, filename_prefix="fixed_effects_value_added"):
        """
        保存固定效应模型结果
        
        Args:
            output_dir: 输出目录
            filename_prefix: 文件名前缀
            
        Returns:
            dict: 保存的文件路径
        """
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        
        # 保存结果
        saved_paths = {}
        
        # 保存模型摘要
        summary_path = os.path.join(output_dir, f"{filename_prefix}_summary.txt")
        with open(summary_path, 'w') as f:
            f.write(str(self.results.summary()))
        saved_paths["summary"] = summary_path
        
        # 保存参数
        params_path = os.path.join(output_dir, f"{filename_prefix}_parameters.csv")
        params_df = pd.DataFrame({
            'parameter': self.results.params.index,
            'estimate': self.results.params.values,
            'std_err': self.results.bse.values,
            'p_value': self.results.pvalues.values
        })
        params_df.to_csv(params_path, index=False)
        saved_paths["parameters"] = params_path
        
        # 保存增值效应
        value_added = self.calculate_value_added()
        for level, df in value_added.items():
            if not df.empty:
                va_path = os.path.join(output_dir, f"{filename_prefix}_{level}_value_added.csv")
                df.to_csv(va_path)
                saved_paths[f"{level}_value_added"] = va_path
        
        # 保存评估指标
        metrics_path = os.path.join(output_dir, f"{filename_prefix}_metrics.json")
        with open(metrics_path, 'w') as f:
            json.dump(self.metrics, f, indent=4)
        saved_paths["metrics"] = metrics_path
        
        return saved_paths


class RandomEffectsValueAddedModel(BaseValueAddedModel):
    """
    随机效应增值模型实现
    
    使用随机效应来表示不同学校/班级的增值效应，允许不仅截距而且斜率随机变化。
    该模型假设实体（学校/班级）来自一个更大的总体，效应服从正态分布。
    
    Args:
        data: 建模数据
        random_slope: 是否允许斜率随机
        re_formula: 随机效应公式
        covariates: 协变量列表
    """
    
    def __init__(self, data=None, random_slope=False, re_formula=None, covariates=None):
        """
        初始化随机效应模型
        
        Args:
            data: 建模数据
            random_slope: 是否允许斜率随机变化
            re_formula: 自定义随机效应公式
            covariates: 额外控制变量，例如['gender', 'ses']
        """
        super().__init__(data)
        self.random_slope = random_slope
        self.re_formula = re_formula
        self.covariates = covariates or []
    
    def _validate_data(self):
        """
        验证随机效应模型所需数据
        
        Raises:
            ValueError: 如果缺少必要字段
        """
        required_fields = ['prior_score', 'standard_score', 'student_idx', 'class_idx']
        missing_fields = [f for f in required_fields if f not in self.data.columns]
        if missing_fields:
            raise ValueError(f"数据缺少随机效应模型所需字段: {missing_fields}")
        
        # 验证协变量
        missing_covariates = [f for f in self.covariates if f not in self.data.columns]
        if missing_covariates:
            logger.warning(f"数据缺少指定的协变量: {missing_covariates}")
            # 从协变量列表中移除缺失的字段
            self.covariates = [f for f in self.covariates if f not in missing_covariates]
    
    def _build_model(self):
        """
        构建随机效应模型
        
        创建包含随机截距和可选随机斜率的混合线性模型
        """
        # 准备建模数据
        model_data = self.data.copy()
        
        # 构建固定效应公式部分
        fe_formula = "standard_score ~ prior_score"
        if self.covariates:
            fe_formula += " + " + " + ".join(self.covariates)
        
        # 构建随机效应公式
        if self.re_formula:
            re_formula = self.re_formula
        else:
            # 根据可用的层级变量构建随机效应
            re_parts = []
            
            # 班级随机效应
            if 'class_idx' in model_data.columns:
                if self.random_slope:
                    re_parts.append("prior_score")  # 允许斜率随机
                re_parts.append("1")  # 随机截距
                
                re_formula = " + ".join(re_parts)
                re_formula = f"({re_formula}|class_idx)"
            
            # 学校随机效应（如果有）
            if 'school_idx' in model_data.columns:
                school_re = "(1|school_idx)"  # 学校层级只有随机截距
                re_formula = f"{re_formula} + {school_re}" if re_parts else school_re
        
        # 完整的公式
        formula = f"{fe_formula} + {re_formula}"
        
        # 构建混合线性模型
        self.model = smf.mixedlm(formula, model_data)
        self.formula = formula
        
        logger.info(f"已构建随机效应模型: {formula}")
    
    def fit(self):
        """
        拟合随机效应模型
        
        使用REML方法估计参数
        
        Returns:
            self: 支持链式调用
        """
        logger.info("开始拟合随机效应模型...")
        
        try:
            self.result = self.model.fit(reml=True)
            
            # 保存系数和统计量
            self.params = dict(self.result.params)
            self.random_effects = self.result.random_effects
            self.metrics = {
                'aic': self.result.aic,
                'bic': self.result.bic,
                'log_likelihood': self.result.llf,
                'df_resid': self.result.df_resid
            }
            
            logger.info(f"随机效应模型拟合完成，AIC: {self.metrics['aic']:.2f}")
            return self
            
        except Exception as e:
            logger.error(f"随机效应模型拟合失败: {str(e)}")
            raise
    
    def calculate_value_added(self):
        """
        计算随机效应模型的增值效应
        
        提取随机效应作为增值效应指标
        
        Returns:
            dict: 包含各级别增值效应的字典
        """
        if not hasattr(self, 'result'):
            raise ValueError("模型尚未拟合，请先调用fit()方法")
        
        value_added = {}
        
        # 提取随机效应
        re_dict = self.result.random_effects
        
        # 收集班级随机效应
        if 'class_idx' in self.data.columns:
            class_effects = self._extract_entity_effects(re_dict, 'class_idx')
            if not class_effects.empty:
                value_added['classes'] = class_effects
        
        # 收集学校随机效应
        if 'school_idx' in self.data.columns:
            school_effects = self._extract_entity_effects(re_dict, 'school_idx')
            if not school_effects.empty:
                value_added['schools'] = school_effects
        
        return value_added
    
    def _extract_entity_effects(self, re_dict, entity_type):
        """
        提取实体随机效应
        
        Args:
            re_dict: 随机效应字典
            entity_type: 实体类型，'class_idx'或'school_idx'
        
        Returns:
            pd.DataFrame: 实体效应数据框
        """
        # 获取实体映射
        entity_map = self.mappings.get(entity_type.replace('_idx', 's'), {})
        
        # 创建实体效应数据框
        entity_effects = pd.DataFrame()
        
        # 提取相关的随机效应
        for entity_code, effects in re_dict.items():
            # 检查这个随机效应是否属于我们要提取的类型
            if isinstance(entity_code, tuple) and str(entity_code[1]) == entity_type:
                entity_idx = entity_code[0]
                
                # 随机截距是第一个元素
                if isinstance(effects, dict):  # 多个随机效应
                    effect = effects.get('Group', effects.get('Intercept', 0))
                else:  # 单个随机效应
                    effect = effects
                
                # 获取标准误差和置信区间
                std_err = 0.1  # 简化处理，使用固定值
                ci_lower = effect - 1.96 * std_err
                ci_upper = effect + 1.96 * std_err
                
                # 映射实体ID
                entity_id = entity_map.get(entity_idx, entity_idx)
                
                # 添加到数据框
                entity_effects = entity_effects.append({
                    'entity_id': entity_id,
                    'mean': effect,
                    'std_err': std_err,
                    'ci_lower': ci_lower,
                    'ci_upper': ci_upper
                }, ignore_index=True)
        
        # 确保display_id包含有意义的值
        if 'display_id' not in entity_effects.columns and 'grade' in entity_effects.columns and 'class_num' in entity_effects.columns:
            entity_effects['display_id'] = entity_effects.apply(
                lambda x: f"{x['grade']}年{x['class_num']}班", axis=1
            )
        elif 'display_id' not in entity_effects.columns:
            logger.warning("缺少display_id列，将使用entity_id代替")
            entity_effects['display_id'] = entity_effects['entity_id']
        
        return entity_effects
    
class TVAMValueAddedModel(BaseValueAddedModel):
    """传统增值评估模型(TVAM)实现"""
    
    def prepare_data(self, data=None):
        """
        准备TVAM模型特定的数据
        
        处理包括:
        - 计算前测成绩
        - 创建分类索引
        - 标准化分数
        - 验证数据完整性
        
        Args:
            data: 输入数据，如果为None则使用初始化时的数据
            
        Returns:
            DataFrame: 准备好的建模数据
        """
        # 首先调用基类的prepare_data获取基础处理后的数据
        # 这已经包含了前测后测处理、过滤前测数据、创建数值索引等通用步骤
        model_data = super().prepare_data(data)
        
        # 获取数据处理工具
        processors = self.data_processor.get_data_processors()
        
        # 显示处理前的数据信息
        logger.info(f"TVAM模型准备数据，接收的数据字段: {sorted(model_data.columns.tolist())}")
        logger.info(f"数据样本（前3行）:\n{model_data.head(3)}")
        

        
        # 检查真实班级数量（TVAM特别关注）
        if 'class_idx' in model_data.columns:
            num_classes = model_data['class_idx'].nunique() 
            logger.info(f"TVAM模型数据包含{num_classes}个班级")
        
        # TVAM特定的其他处理
        # 例如，计算班级平均成绩作为协变量
        if 'class_idx' in model_data.columns and 'prior_score' in model_data.columns:
            class_means = model_data.groupby('class_idx')['prior_score'].mean().reset_index()
            class_means.columns = ['class_idx', 'class_mean_prior']
            model_data = pd.merge(model_data, class_means, on='class_idx', how='left')
            logger.info("已添加班级平均前测成绩作为协变量")
        
        # 在方法结束前记录日志
        logger.info(f"TVAM模型准备完成，数据字段: {sorted(model_data.columns.tolist())}")
        
        # 保存处理后的数据
        self.data = model_data
        return model_data
    
    def _validate_data(self):
        """
        验证TVAM模型所需数据
        
        Raises:
            ValueError: 如果缺少必要字段
        """
        required_fields = ['prior_score', 'standard_score', 'student_idx']
        required_fields.append(f"{self.entity_type}_idx")
        
        missing_fields = [f for f in required_fields if f not in self.data.columns]
        if missing_fields:
            raise ValueError(f"数据缺少TVAM模型所需字段: {missing_fields}")
        
        # 验证协变量
        missing_covariates = [f for f in self.covariates if f not in self.data.columns]
        if missing_covariates:
            logger.warning(f"数据缺少指定的协变量: {missing_covariates}")
            # 从协变量列表中移除缺失的字段
            self.covariates = [f for f in self.covariates if f not in missing_covariates]

    def _build_model(self):
        """
        构建TVAM模型
        
        使用OLS回归模型预测学生表现
        """
        model_data = self.data.copy()
        
        # 构建预测公式
        formula = "standard_score ~ prior_score"
        if self.covariates:
            formula += " + " + " + ".join(self.covariates)
        
        # 使用statsmodels的OLS
        self.model = smf.ols(formula, data=model_data)
        self.formula = formula
        
        logger.info(f"已构建TVAM模型: {formula}")
    
    def _fit_model(self):
        """
        拟合TVAM模型
        
        计算学生实际成绩与预期成绩的差异
        
        Returns:
            self: 支持链式调用
        """
        logger.info("开始拟合TVAM模型...")
        
        try:
            # 拟合模型
            self.result = self.model.fit()
            
            
            # 计算残差(实际成绩 - 预期成绩)
            self.data['predicted_score'] = self.result.predict()
            self.data['residual'] = self.data['standard_score'] - self.data['predicted_score']
            
            # 保存系数和统计量
            self.params = dict(self.result.params)
            self.metrics = {
                'r_squared': self.result.rsquared,
                'adj_r_squared': self.result.rsquared_adj,
                'aic': self.result.aic,
                'bic': self.result.bic,
                'fvalue': self.result.fvalue,
                'df_model': self.result.df_model,
                'df_resid': self.result.df_resid
            }
            
            logger.info(f"TVAM模型拟合完成，R²: {self.metrics['r_squared']:.4f}")
            return self
            
        except Exception as e:
            logger.error(f"TVAM模型拟合失败: {str(e)}")
            raise
    
    def _calculate_value_added_impl(self):
        """计算TVAM模型的增值效应"""
        
        # 打印数据列名，帮助调试
        logger.info(f"数据包含以下列: {list(self.data.columns)}")
        
        # 显示前几行数据中的school_id和school_name（如果存在）
        if 'school_id' in self.data.columns:
            logger.info(f"school_id示例: {self.data['school_id'].head(3).tolist()}")
        if 'school_name' in self.data.columns:
            logger.info(f"school_name示例: {self.data['school_name'].head(3).tolist()}")
                
        # 确定实体列名 - 增加队列分析选项
        use_cohort = getattr(self, 'use_cohort', False)  # 是否使用队列分析
        
        if self.entity_type == 'class':
            if use_cohort and 'cohort_id' in self.data.columns:
                # 使用学生队列ID（跨年级）
                entity_col = 'cohort_id'
                entity_name_col = 'cohort_id'  # 临时使用ID作为名称
                logger.info("使用学生队列进行增值分析（跨年级）")
            elif 'class_base_id' in self.data.columns:
                # 使用基础班级ID（不含年级和学期）
                entity_col = 'class_base_id'
                entity_name_col = 'class_name'
                logger.info("使用基础班级ID进行增值分析")
            else:
                # 回退到标准ID
                entity_col = 'class_idx'
                entity_name_col = 'class_name'
        else:
            entity_col = f"{self.entity_type}_idx"
            entity_name_col = f"{self.entity_type}_name"
        
        logger.info(f"使用的实体列: {entity_col}, 名称列: {entity_name_col}")
        
        # 按实体聚合残差计算增值效应
        grouped = self.data.groupby(entity_col)
        
        # 计算每个实体的平均残差和标准误
        entity_effects = grouped['residual'].agg(['mean', 'std', 'count']).reset_index()
        
        # 先获取每个实体的元数据
        entity_metadata = self.data.groupby(entity_col)[['school_name', 'display_id', 'class_name', 
                                                        'school_code', 'grade', 'class_num']].first().reset_index()
        
        # 合并元数据到结果中 - 使用正确的连接键
        entity_effects = pd.merge(
            entity_effects, 
            entity_metadata,
            on=entity_col,
            how='left'
        )
        
        # 计算标准误差和置信区间
        entity_effects['std_err'] = entity_effects['std'] / np.sqrt(entity_effects['count'])
        entity_effects['ci_lower'] = entity_effects['mean'] - 1.96 * entity_effects['std_err']
        entity_effects['ci_upper'] = entity_effects['mean'] + 1.96 * entity_effects['std_err']
        
        # 添加评级列
        def assign_rating(value):
            if value < -24: return 'D-'  
            elif value < -18: return 'D'   
            elif value < -9: return 'C-'  
            elif value < 0: return 'C'   
            elif value < 9: return 'B'   
            elif value < 18: return 'A'   
            else: return 'A+'  
        
        entity_effects['rating'] = entity_effects['mean'].apply(assign_rating)
        
        # 在返回结果前，确保所有必需的列都存在
        required_columns = ['entity_id', 'mean', 'std_err', 'ci_lower', 'ci_upper', 'rating']
        for col in required_columns:
            if col not in entity_effects.columns:
                logger.warning(f"缺少必需列: {col}，将添加默认值")
                entity_effects[col] = None if col != 'rating' else 'C'
        
        # 添加可选列（如果不存在）
        if 'school_name' not in entity_effects.columns:
            logger.warning("缺少school_name列，将使用默认值")
            entity_effects['school_name'] = "未知学校"
            
        if 'display_id' not in entity_effects.columns:
            logger.warning("缺少display_id列，将使用entity_id代替")
            entity_effects['display_id'] = entity_effects['entity_id']
        
        # 选择最终返回的列，确保所有列都存在
        result_columns = [col for col in ['school_name', 'entity_id', 'display_id', 
                         'mean', 'std_err', 'ci_lower', 'ci_upper', 'rating'] 
                         if col in entity_effects.columns]
        
        value_added = {}
        if entity_name_col in self.data.columns:
            entity_effects['entity_id'] = entity_effects[entity_col]  # 使用数字ID作为entity_id
            entity_effects['entity_name'] = entity_effects[entity_name_col]  # 保留原始名称
            value_added['classes'] = entity_effects[result_columns]
        else:
            # 映射实体ID（仅在没有原始名称时）
            entity_map = self.mappings.get(f"{self.entity_type}s", {})
            entity_effects['entity_id'] = entity_effects[entity_col].map(lambda x: entity_map.get(x, x))
            value_added['classes'] = entity_effects[result_columns]
        
        logger.info(f"计算了{len(entity_effects)}个{self.entity_type}的增值效应")
        return value_added
    
    def _predict_impl(self, new_data):
        """
        使用随机效应模型预测
        
        Args:
            new_data: 新的数据框
            
        Returns:
            Series: 预测值
        """
        if not hasattr(self, 'result'):
            raise ValueError("模型尚未拟合，请先调用fit()方法")
        
        # 如果新数据与训练数据不同，确保它有相同的列
        pred_data = new_data.copy()
        
        # 返回预测值
        return self.result.predict(pred_data)    
    

    def evaluate(self):
        """
        评估随机效应模型性能
        
        Returns:
            dict: 包含各种模型评估指标的字典
        """
        if not hasattr(self, 'result'):
            raise ValueError("模型尚未拟合，请先调用fit()方法")
        
        # 基本统计量
        metrics = {
            'r_squared': self.result.rsquared,
            'adj_r_squared': self.result.rsquared_adj,
            'mse': np.mean(self.result.resid ** 2),
            'rmse': np.sqrt(np.mean(self.result.resid ** 2)),
            'mae': np.mean(np.abs(self.result.resid)),
            'median_residual': np.median(self.result.resid)
        }
        
        # 分位数统计
        residual_quantiles = np.percentile(self.result.resid, [25, 50, 75])
        metrics['residual_q1'] = residual_quantiles[0]
        metrics['residual_median'] = residual_quantiles[1]
        metrics['residual_q3'] = residual_quantiles[2]
        
        # 残差正态性检验
        _, p_value = stats.shapiro(self.result.resid)
        metrics['residual_normality_p'] = p_value
        
        return metrics

def verify_excel_file(file_path):
    """
    验证Excel文件是否可以被正确读取
    
    Args:
        file_path: Excel文件路径
        
    Returns:
        bool: 文件是否可读
    """
    try:
        pd.read_excel(file_path, sheet_name=None)
        return True
    except Exception as e:
        logger.error(f"Excel文件验证失败: {str(e)}")
        return False

class NonlinearStudentPotentialEvaluator(BaseValueAddedModel):
    """
    非线性学习潜力评估器
    
    通过识别学生的非线性学习曲线特征评估其学习潜力
    
    Args:
        data: 包含学生成绩数据的DataFrame
        baseline_exam: 基准考试ID(可选)
    """
    
    def __init__(self, data=None, data_processor=None, baseline_exam=None):
        """初始化非线性潜力评估器"""
        super().__init__(data, data_processor)
        self.baseline_exam = baseline_exam
        self.potential_scores = None
        self.growth_patterns = None
    
    def prepare_data(self, data=None):
        """
        准备非线性潜力分析所需的数据
        
        Args:
            data: 输入数据，如果为None则使用初始化时的数据
            
        Returns:
            DataFrame: 处理后的数据
        
        Raises:
            ValueError: 当数据不符合要求或无法处理时
        """
        # 修复数据处理逻辑
        if data is not None:
            self.data = data.copy()  # 使用提供的数据
        elif self.data is None:
            # 如果self.data为None，尝试从数据处理器获取
            if hasattr(self, 'data_processor') and self.data_processor is not None:
                logger.info("从数据处理器获取数据")
                self.data = self.data_processor.data.copy()
                
        # 现在进行数据验证
        if self.data is None or len(self.data) == 0:
            logger.error("NonlinearStudentPotentialEvaluator没有可用数据")
            raise ValueError("没有可用数据进行潜力评估")
        
        # 获取数据处理器功能 - 添加此行
        processors = self.data_processor.get_data_processors()
        
        # 记录数据状态  
        logger.info(f"准备非线性潜力评估数据: {len(self.data)}条记录，字段: {sorted(self.data.columns.tolist())}")
            
        # 确保所需字段存在
        required_fields = ['student_id', 'exam_id', 'standard_score']
        missing_fields = [f for f in required_fields if f not in self.data.columns]
        if missing_fields:
            error_msg = f"数据缺少必要字段: {missing_fields}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        

        
        # 3. 检查数据完整性 - 添加警告
        all_exam_ids = sorted(self.data['exam_id'].unique())
        logger.info(f"数据中包含以下考试: {all_exam_ids}")
        
        # 检查每个学生的考试记录完整性
        student_exam_counts = self.data.groupby('student_id')['exam_id'].nunique()
        complete_students = student_exam_counts[student_exam_counts == len(all_exam_ids)].index
        incomplete_students = student_exam_counts[student_exam_counts < len(all_exam_ids)].index
        
        if len(incomplete_students) > 0:
            logger.warning(f"发现{len(incomplete_students)}名学生的考试记录不完整，可能影响分析结果的准确性")
            
            # 统计不同考试次数的学生人数
            count_distribution = student_exam_counts.value_counts().sort_index()
            for count, num_students in count_distribution.items():
                logger.info(f"参加了{count}次考试的学生数: {num_students}")
        
        # 4. 非线性评估特有的处理：仅保留参加全部考试的学生
        all_exams = sorted(self.data['exam_id'].unique())
        total_exams = len(all_exams)
        logger.info(f"数据中包含 {total_exams} 次考试: {all_exams}")

        # 计算每个学生参加的考试次数
        student_exam_counts = self.data.groupby('student_id')['exam_id'].nunique()

        # 只保留参加全部考试的学生
        complete_students = student_exam_counts[student_exam_counts == total_exams].index
        incomplete_students = student_exam_counts[student_exam_counts < total_exams].index

        # 记录统计信息
        logger.info(f"参加全部 {total_exams} 次考试的学生: {len(complete_students)}人")
        logger.info(f"未参加全部考试的学生: {len(incomplete_students)}人 (这些学生将被排除在分析之外)")

        # 筛选数据
        self.data = self.data[self.data['student_id'].isin(complete_students)]

        if len(self.data) == 0:
            raise ValueError(f"没有学生参加了全部 {total_exams} 次考试，无法进行非线性潜力评估")

        # 确保总考试次数至少为3
        if total_exams < 3:
            raise ValueError(f"总考试次数({total_exams})少于3次，无法进行非线性潜力评估")
        
        # 5. 确保考试时间序列的一致性
        if 'exam_date' in self.data.columns:
            # 按日期排序考试
            exam_dates = self.data.groupby('exam_id')['exam_date'].first().sort_values()
            exam_order = {exam: i for i, exam in enumerate(exam_dates.index)}
            self.data['exam_order'] = self.data['exam_id'].map(exam_order)
        else:
            # 如果没有日期，假设考试ID已经按时间顺序编号
            exam_ids = sorted(self.data['exam_id'].unique())
            exam_order = {exam: i for i, exam in enumerate(exam_ids)}
            self.data['exam_order'] = self.data['exam_id'].map(exam_order)
        
        # 按学生ID和考试顺序排序
        self.data = self.data.sort_values(['student_id', 'exam_order'])
        
        # 6. 确保必要的名称字段（使用处理器功能）
        self.data = processors['ensure_student_names'](self.data)
        self.data = processors['ensure_school_names'](self.data)
        self.data = processors['ensure_class_names'](self.data)
        self.data = processors['ensure_grade_field'](self.data)
        
        # 7. 提取非线性特征
        self._extract_nonlinear_features()
        
        return self.data
    
    def _extract_nonlinear_features(self):
        """提取非线性学习特征"""
        # 按学生ID分组
        for student_id, group in self.data.groupby('student_id'):
            if len(group) < 3:
                continue
                
            # 确保按考试顺序排序
            group_sorted = group.sort_values('exam_id')
            scores = group_sorted['standard_score'].values
            
            # 处理学生缺失的考试
            total_exams = self.data['exam_order'].nunique()
            actual_exams = group_sorted['exam_order'].nunique()
            
            if actual_exams < total_exams:
                # 记录学生实际参加的考试
                exams_taken = group_sorted['exam_id'].values
                logger.debug(f"学生{student_id}只参加了{actual_exams}次考试: {exams_taken}")
            
            # 1. 计算二阶差分(加速度)
            first_diffs = np.diff(scores)
            self.data.loc[self.data['student_id'] == student_id, 'learning_velocity'] = \
                np.pad(first_diffs, (0, 1), 'constant')
                
            # 处理缺测影响
            if len(first_diffs) >= 2:
                second_diffs = np.diff(first_diffs)
                self.data.loc[self.data['student_id'] == student_id, 'learning_acceleration'] = \
                    np.pad(second_diffs, (0, 2), 'constant')
            else:
                # 如果差分数据不足，填充0
                self.data.loc[self.data['student_id'] == student_id, 'learning_acceleration'] = 0
                
            # 2. 识别平台期(连续两次考试变化小于阈值)
            is_plateau = np.abs(first_diffs) < 2.0
            plateau_periods = np.pad(is_plateau, (0, 1), 'constant')
            self.data.loc[self.data['student_id'] == student_id, 'in_plateau'] = plateau_periods
            
            # 3. 识别突破期(大幅提升)
            is_breakthrough = first_diffs > 5.0
            breakthrough_periods = np.pad(is_breakthrough, (0, 1), 'constant')
            self.data.loc[self.data['student_id'] == student_id, 'breakthrough'] = breakthrough_periods
            
            # 4. 计算近期势头(最近3次考试的趋势)
            if len(scores) >= 3:
                recent_trend = np.polyfit(range(3), scores[-3:], 1)[0]
                self.data.loc[self.data['student_id'] == student_id, 'recent_momentum'] = recent_trend
            else:
                # 如果不足3次考试，使用所有可用数据
                recent_trend = np.polyfit(range(len(scores)), scores, 1)[0] if len(scores) > 1 else 0
                self.data.loc[self.data['student_id'] == student_id, 'recent_momentum'] = recent_trend
    
    # 覆盖基类方法，整合新架构
    def fit(self, data=None):
        """拟合模型"""
        if data is not None:
            self.prepare_data(data)
        elif self.data is None and hasattr(self, 'raw_data') and self.raw_data is not None:
            self.prepare_data(self.raw_data)
            
        # 执行非线性评估
        self.evaluate_potential()
        self.analyze_growth_patterns()
        
        return self
    
    # 覆盖基类方法，适配新架构
    def _build_model(self):
        """适配BaseValueAddedModel接口"""
        # 非线性评估不需要传统模型构建
        pass
    
    # 覆盖基类方法，适配新架构
    def _fit_model(self):
        """适配BaseValueAddedModel接口"""
        # 执行非线性评估
        self.evaluate_potential()
        self.analyze_growth_patterns()
    
    # 覆盖基类方法，适配新架构
    def get_results(self):
        """获取评估结果"""
        if self.potential_scores is None:
            self.evaluate_potential()
            
        if self.growth_patterns is None:
            self.analyze_growth_patterns()
            
        return {
            'potential_scores': self.potential_scores,
            'growth_patterns': self.growth_patterns
        }
    
    # 保留所有原始方法，不做任何修改
    def evaluate_potential(self):
        """
        评估学生的非线性潜力
        
        此方法实现完整的非线性潜力评估逻辑，包括突破识别和长期优势学生识别
        
        Returns:
            DataFrame: 包含潜力评估结果的数据框
        """
        if self.data is None:
            self.prepare_data()
            
        # 1. 获取所有学生ID
        student_ids = self.data['student_id'].unique()
        
        # 2. 初始化结果列表
        potential_scores = []
        
        # 3. 对每个学生计算潜力分数
        for student_id in student_ids:
            result = self._calculate_student_potential(student_id)
            potential_scores.append(result)
            
        # 4. 将结果转换为DataFrame
        self.potential_scores = pd.DataFrame(potential_scores)
        
        # 5. 添加学生的基本信息
        student_info = self.data.drop_duplicates('student_id')[['student_id', 'student_name', 'school_name']]
        if 'class_name' in self.data.columns:
            student_info = self.data.drop_duplicates('student_id')[['student_id', 'student_name', 'school_name', 'class_name']]
        if 'grade' in self.data.columns:
            student_info = self.data.drop_duplicates('student_id')[['student_id', 'student_name', 'school_name', 'class_name', 'grade']]
            
        self.potential_scores = pd.merge(
            self.potential_scores,
            student_info,
            on='student_id',
            how='left'
        )
        
        # 6. 【新增】识别长期保持学科优势的学生
        consistent_performers = self._identify_consistent_performers()
        logger.info(f"长期保持优势的学生识别完成，结果包含 {len(consistent_performers)} 条记录")
        
        # 7. 【新增】合并长期优势学生结果
        self.potential_scores = pd.merge(
            self.potential_scores,
            consistent_performers,
            on='student_id',
            how='left'
        )
        
        # 8. 【新增】添加学生表现类型标签
        self.potential_scores['performance_type'] = '未分类'
        
        # 长期优势型
        mask = self.potential_scores['consistent_performer'] == True
        self.potential_scores.loc[mask, 'performance_type'] = '长期优势型'
        
        # 突破成长型（高潜力但不是长期优势）
        breakthrough_mask = (~self.potential_scores['consistent_performer']) & (self.potential_scores['potential_score'] > 75)
        self.potential_scores.loc[breakthrough_mask, 'performance_type'] = '突破成长型'
        
        # 稳定型（中等潜力，非长期优势）
        stable_mask = (~self.potential_scores['consistent_performer']) & (self.potential_scores['potential_score'].between(50, 75))
        self.potential_scores.loc[stable_mask, 'performance_type'] = '稳定发展型'
        
        # 待发展型（低潜力）
        developing_mask = (~self.potential_scores['consistent_performer']) & (self.potential_scores['potential_score'] < 50)
        self.potential_scores.loc[developing_mask, 'performance_type'] = '待发展型'
        
        # 9. 修复第一行prepare_data中的方法名称错误
        # self.data = processors['ensure_grade_names'](self.data) 应该改为：
        # self.data = processors['ensure_grade_field'](self.data)
        
        logger.info(f"非线性潜力评估完成，结果包含 {len(self.potential_scores)} 条记录")
        
        # 规范化分数(添加到第5步末尾)
        if not self.potential_scores.empty:
            min_score = self.potential_scores['potential_score'].min()
            max_score = self.potential_scores['potential_score'].max()
            
            # 避免除以零
            score_range = max_score - min_score
            if score_range > 0:
                self.potential_scores['potential_score_norm'] = 100 * (self.potential_scores['potential_score'] - min_score) / score_range
            else:
                self.potential_scores['potential_score_norm'] = 50  # 如果所有分数相同
                
            # 评级
            def assign_potential_rating(score):
                if score >= 85: return 'A+'  # 优秀潜力
                elif score >= 70: return 'A'  # 高潜力
                elif score >= 55: return 'B'  # 良好潜力
                elif score >= 40: return 'C'  # 中等潜力
                elif score >= 25: return 'D'  # 需要关注
                else: return 'E'  # 需要特别帮助
                
            self.potential_scores['potential_rating'] = self.potential_scores['potential_score_norm'].apply(assign_potential_rating)
        
        return self.potential_scores
    
    def analyze_growth_patterns(self):
        """
        使用非线性方法分析成长模式
        
        通过对学生成绩曲线拟合多种模型，确定最佳成长模式
        
        Returns:
            DataFrame: 包含每个学生成长模式分析结果的数据框
        """
        growth_patterns = []  
        
        # 提前定义常量
        MODEL_NAMES = ["线性成长", "加速/减速成长", "S型成长"]
        PLATEAU_THRESHOLD = 2.0
        BREAKTHROUGH_THRESHOLD = 5.0
        
        for student_id, group in self.data.groupby('student_id'):
            if len(group) < 3:
                continue
                
            # 提取学生基本信息
            student_info = self._extract_student_info(group)
            
            # 提取并排序成绩
            scores = group.sort_values('exam_id')['standard_score'].values
            x = np.arange(len(scores))
            
            # 拟合多种模型并计算拟合度
            model_results = self._fit_growth_models(x, scores)
            
            # 确定最佳拟合模型
            best_model_idx = np.argmax([r['r2'] for r in model_results])
            best_model = MODEL_NAMES[best_model_idx]
            best_r2 = model_results[best_model_idx]['r2']
            
            # 分析波动模式
            diffs = np.diff(scores)
            volatility = np.std(diffs)
            
            # 识别平台和突破
            has_plateau = np.any(np.abs(diffs) < PLATEAU_THRESHOLD)
            has_breakthrough = np.any(diffs > BREAKTHROUGH_THRESHOLD)
            
            # 确定总体趋势方向
            trend = "上升" if np.mean(diffs) > 0 else "下降" if np.mean(diffs) < 0 else "持平"
            
            # 确定成长模式类型
            pattern = self._determine_growth_pattern(
                best_model, 
                volatility, 
                has_plateau, 
                has_breakthrough, 
                trend,
                model_results[1]['params'] if len(model_results) > 1 else None  # 二次模型参数
            )
            
            # 添加到结果列表
            growth_patterns.append({
                **student_info,
                'student_id': student_id,
                'best_model': best_model,
                'r_squared': best_r2,
                'volatility': volatility,
                'growth_pattern': pattern,
                'has_plateau': has_plateau,
                'has_breakthrough': has_breakthrough
            })
                
        self.growth_patterns = pd.DataFrame(growth_patterns)
        return self.growth_patterns
    
    def _extract_student_info(self, group):
        """提取学生基本信息"""
        return {
            'student_name': group['student_name'].iloc[0] if 'student_name' in group.columns else "未知",
            'school_name': group['school_name'].iloc[0] if 'school_name' in group.columns else "未知",
            'class_name': group['class_name'].iloc[0] if 'class_name' in group.columns else "未知",
            'grade': group['grade'].iloc[0] if 'grade' in group.columns else "未知"
        }
    
    def _fit_growth_models(self, x, scores):
        """拟合多种成长模型"""
        results = []
        
        # 线性模型
        linear_params = np.polyfit(x, scores, 1)
        linear_r2 = self._r_squared(x, scores, np.poly1d(linear_params))
        results.append({'type': 'linear', 'r2': linear_r2, 'params': linear_params})
        
        # 二次模型(抛物线)
        quadratic_params = np.polyfit(x, scores, 2)
        quadratic_r2 = self._r_squared(x, scores, np.poly1d(quadratic_params))
        results.append({'type': 'quadratic', 'r2': quadratic_r2, 'params': quadratic_params})
        
        # 尝试拟合S曲线(Logistic)
        logistic_r2 = self._fit_logistic_model(x, scores)
        results.append({'type': 'logistic', 'r2': logistic_r2, 'params': None})
        
        return results
    
    def _fit_logistic_model(self, x, scores):
        """尝试拟合逻辑斯蒂模型，返回R²值"""
        try:
            from scipy.optimize import curve_fit
            
            def logistic(x, a, b, c, d):
                return self.safe_logistic(x, a, b, c, d)
            
            # 标准化x以帮助拟合
            x_norm = (x - np.min(x)) / (np.max(x) - np.min(x)) if np.max(x) > np.min(x) else x
            
            # 参数估计和约束
            p0 = [
                np.max(scores) - np.min(scores),  # 范围
                1.0,  # 增长率
                0.5,  # 中点位置
                np.min(scores)  # 最小值
            ]
            
            bounds = (
                [0, 0, 0, np.min(scores)*0.9],  # 下界
                [np.inf, 10, 1, np.max(scores)]  # 上界
            )
            
            try:
                popt, _ = curve_fit(logistic, x_norm, scores, p0=p0, bounds=bounds, maxfev=2000)
                logistic_r2 = self._r_squared(x_norm, scores, lambda x: logistic(x, *popt))
            except:
                logistic_r2 = 0
        except:
            logistic_r2 = 0
            
        return logistic_r2
    
    def _determine_growth_pattern(self, best_model, volatility, has_plateau, has_breakthrough, trend, quadratic_params=None):
        """确定成长模式类型"""
        if best_model == "线性成长":
            if volatility < 3:
                return f"稳定{trend}"
            else:
                return f"波动{trend}"
        elif best_model == "加速/减速成长" and quadratic_params is not None:
            if quadratic_params[0] > 0:
                return "加速成长"
            else:
                return "减速成长"
        else:  # S型成长
            if has_plateau and has_breakthrough:
                return "突破型成长"
            elif has_plateau:
                return "平台后成长"
            else:
                return "渐进成长"
    
    def _r_squared(self, x, y, model):
        """计算R²值"""
        y_pred = model(x)
        ss_total = np.sum((y - np.mean(y))**2)
        ss_residual = np.sum((y - y_pred)**2)
        return 1 - (ss_residual / ss_total) if ss_total != 0 else 0
        
    def get_student_report(self, student_id):
        """
        生成基于非线性模型的学生报告
        
        Args:
            student_id: 学生ID
            
        Returns:
            dict: 包含学生详细分析的字典
        """
        if self.potential_scores is None:
            self.evaluate_potential()
            
        if self.growth_patterns is None:
            self.analyze_growth_patterns()
            
        # 获取学生数据
        student_data = self.data[self.data['student_id'] == student_id].sort_values('exam_id')
        potential = self.potential_scores[self.potential_scores['student_id'] == student_id]
        growth = self.growth_patterns[self.growth_patterns['student_id'] == student_id]
        
        if student_data.empty:
            return {"error": f"未找到学生 {student_id} 的数据"}
            
        # 生成报告
        report = {
            'student_id': student_id,
            'name': student_data['student_name'].iloc[0] if 'student_name' in student_data.columns 
                   else (student_data['name'].iloc[0] if 'name' in student_data.columns else "未知"),
            'class': student_data['class_name'].iloc[0] if 'class_name' in student_data.columns else "未知",
            'school': student_data['school_name'].iloc[0] if 'school_name' in student_data.columns else "未知",
            'grade': student_data['grade'].iloc[0] if 'grade' in student_data.columns else "未知",
            'exam_count': len(student_data),
            'latest_score': student_data['standard_score'].iloc[-1],
            'first_score': student_data['standard_score'].iloc[0],
            'total_growth': student_data['standard_score'].iloc[-1] - student_data['standard_score'].iloc[0],
            
            # 潜力评价指标
            'avg_growth_rate': potential['base_growth'].iloc[0] if not potential.empty else None,
            'momentum': potential['momentum'].iloc[0] if not potential.empty else None,
            'breakthrough_count': potential['breakthrough_count'].iloc[0] if not potential.empty else 0,
            'resilience': potential['resilience'].iloc[0] if not potential.empty else None,
            
            # 非线性成长评估
            'potential_score': potential['potential_score_norm'].iloc[0] if not potential.empty else None,
            'potential_rating': potential['potential_rating'].iloc[0] if not potential.empty else None,
            'best_growth_model': growth['best_model'].iloc[0] if not growth.empty else "数据不足",
            'growth_pattern': growth['growth_pattern'].iloc[0] if not growth.empty else "数据不足",
            'model_fit_quality': growth['r_squared'].iloc[0] if not growth.empty else None,
            
            # 历史数据
            'scores_history': student_data[['exam_id', 'standard_score']].values.tolist(),
            'velocity_history': student_data[['exam_id', 'learning_velocity']].values.tolist() if 'learning_velocity' in student_data.columns else [],
            
            # 学习阶段和建议
            'learning_phase': self._identify_learning_phase(student_id),
        }
        
        # 添加阶段建议
        report['phase_recommendations'] = self._get_phase_recommendations(report['learning_phase'])
        
        return report
    
    def _identify_learning_phase(self, student_id):
        """识别学生当前的学习阶段"""
        student_data = self.data[self.data['student_id'] == student_id].sort_values('exam_id')
        
        if len(student_data) < 3:
            return "数据不足"
            
        # 获取最近的学习速度和加速度
        recent_velocity = student_data['learning_velocity'].iloc[-1]
        recent_acceleration = student_data['learning_acceleration'].iloc[-1]
        in_plateau = student_data['in_plateau'].iloc[-1]
        
        # 判断学习阶段
        if in_plateau:
            return "平台期"
        elif recent_acceleration > 0 and recent_velocity > 0:
            return "加速成长期"
        elif recent_acceleration < 0 and recent_velocity > 0:
            return "减速成长期"
        elif recent_velocity < 0:
            return "调整期"
        else:
            return "稳定成长期"
    
    def _get_phase_recommendations(self, phase):
        """基于学习阶段生成建议"""
        recommendations = []
        
        if phase == "平台期":
            recommendations.append("当前处于学习平台期，可能遇到了知识瓶颈")
            recommendations.append("建议尝试不同的学习方法打破思维定势")
            recommendations.append("适当增加练习难度，挑战自我")
        elif phase == "加速成长期":
            recommendations.append("当前正处于快速进步阶段，学习效率高")
            recommendations.append("建议保持当前学习状态和方法")
            recommendations.append("可以尝试扩展学习内容的广度")
        elif phase == "减速成长期":
            recommendations.append("进步速度正在放缓，可能接近当前知识模块的掌握上限")
            recommendations.append("建议深入巩固已学内容，确保知识结构完整")
            recommendations.append("准备迎接下一阶段的学习挑战")
        elif phase == "调整期":
            recommendations.append("成绩出现暂时回落，属于学习过程中的正常调整")
            recommendations.append("建议回顾基础知识，查漏补缺")
            recommendations.append("调整学习节奏，避免焦虑情绪影响学习")
        else:
            recommendations.append("当前学习状态稳定，进步速度均衡")
            recommendations.append("建议保持当前学习习惯，适当提高自我要求")
            
        return recommendations

    @staticmethod
    def safe_logistic(x, a, b, c, d):
        """安全的逻辑斯蒂函数，防止溢出"""
        # 限制指数函数的输入范围
        exp_term = np.clip(-b * (x - c), -100, 100)  # 限制在合理范围内
        return a / (1 + np.exp(exp_term)) + d

    # 在NonlinearStudentPotentialEvaluator类中添加以下方法实现

    def _validate_data(self):
        """
        验证数据有效性
        
        这是对抽象方法的实现。非线性潜力评估器有自己特定的数据验证逻辑。
        
        Returns:
            bool: 数据是否有效
        """
        # 非线性潜力评估有自己的验证逻辑，已在prepare_data方法中处理
        # 这里只需返回True表示验证通过
        return True

    def _calculate_value_added_impl(self):
        """
        计算增值分值的具体实现
        
        非线性潜力评估器不使用传统增值计算方法，而是使用evaluate_potential。
        提供此方法只是为了满足抽象类的要求。
        
        Returns:
            DataFrame: 空数据框
        """
        # 非线性潜力评估使用evaluate_potential方法，不使用此方法
        logger.info("NonlinearStudentPotentialEvaluator使用evaluate_potential而不是_calculate_value_added_impl")
        return pd.DataFrame()

    def _predict_impl(self, new_data=None):
        """
        预测新数据的实现
        
        非线性潜力评估器有自己的预测逻辑，不使用此方法。
        提供此方法只是为了满足抽象类的要求。
        
        Args:
            new_data: 新数据
            
        Returns:
            DataFrame: 空数据框
        """
        # 非线性潜力评估使用其他方法进行预测
        logger.info("NonlinearStudentPotentialEvaluator使用特定的预测方法而不是_predict_impl")
        return pd.DataFrame()

    def _identify_consistent_performers(self):
        """
        识别长期保持学科优势的学生
        
        这个方法计算几个关键指标来识别始终表现优秀的学生，而不仅是那些
        有突破性成长的学生。
        
        Returns:
            DataFrame: 包含一致性表现指标的数据框
        """
        # 准备结果数据框
        student_ids = self.data['student_id'].unique()
        consistent_metrics = {
            'student_id': [],
            'percentile_stability': [],  # 百分位稳定性
            'top_quartile_ratio': [],    # 位于前25%的考试比例
            'relative_advantage': [],    # 相对优势维持度
            'consistent_performer': []   # 综合判断结果
        }
        
        # 计算每次考试的全体分数分布
        exam_percentiles = {}
        for exam_id in self.data['exam_id'].unique():
            exam_scores = self.data[self.data['exam_id'] == exam_id]['standard_score']
            exam_percentiles[exam_id] = {score: stats.percentileofscore(exam_scores, score) 
                                        for score in exam_scores}
        
        # 为每个学生计算指标
        for student_id in student_ids:
            student_data = self.data[self.data['student_id'] == student_id].sort_values('exam_id')
            
            # 1. 百分位稳定性 - 学生百分位排名的稳定性
            percentiles = [exam_percentiles[row['exam_id']][row['standard_score']] 
                          for _, row in student_data.iterrows()]
            percentile_stability = 100 - np.std(percentiles)  # 标准差越小越稳定
            
            # 2. 前25%比例 - 学生成绩位于前25%的考试比例
            top_quartile_count = sum(1 for p in percentiles if p >= 75)
            top_quartile_ratio = top_quartile_count / len(percentiles) * 100
            
            # 3. 相对优势 - 学生与平均分差距的变化趋势
            advantages = []
            for _, row in student_data.iterrows():
                exam_mean = self.data[self.data['exam_id'] == row['exam_id']]['standard_score'].mean()
                advantage = row['standard_score'] - exam_mean
                advantages.append(advantage)
            
            # 计算相对优势的趋势（正值表示优势在扩大）
            if len(advantages) >= 2:
                advantage_trend = np.polyfit(range(len(advantages)), advantages, 1)[0]
            else:
                advantage_trend = 0
                
            relative_advantage = np.mean(advantages) + advantage_trend * 10  # 均值+趋势加权
            
            # 添加到结果中
            consistent_metrics['student_id'].append(student_id)
            consistent_metrics['percentile_stability'].append(percentile_stability)
            consistent_metrics['top_quartile_ratio'].append(top_quartile_ratio)
            consistent_metrics['relative_advantage'].append(relative_advantage)
            
            # 综合判断 - 稳定在前25%且百分位稳定
            is_consistent = (top_quartile_ratio >= 75 and percentile_stability > 80)
            consistent_metrics['consistent_performer'].append(is_consistent)
        
        # 创建DataFrame并与潜力评估结果合并
        consistent_df = pd.DataFrame(consistent_metrics)
        
        # 记录日志
        consistent_count = consistent_df['consistent_performer'].sum()
        logger.info(f"识别出{consistent_count}名长期保持学科优势的学生")
        
        return consistent_df

    def _calculate_student_potential(self, student_id):
        """
        计算单个学生的非线性潜力指标
        
        Args:
            student_id: 要计算潜力的学生ID
            
        Returns:
            dict: 包含学生潜力评估结果的字典
        """
        # 获取该学生的数据并按考试顺序排序
        student_data = self.data[self.data['student_id'] == student_id].sort_values('exam_id')
        
        if len(student_data) < 3:
            # 考试记录太少，无法可靠计算潜力
            return {
                'student_id': student_id,
                'potential_score': 0,
                'base_growth': 0,
                'momentum': 0,
                'breakthrough_count': 0,
                'resilience': 0,
                'potential_score_norm': 0,
                'potential_rating': 'E'
            }
        
        # 1. 基础成长率 - 使用平均学习速度
        base_growth = student_data['learning_velocity'].mean()
        
        # 2. 近期势头 - 最近几次考试的学习速度加权平均
        # 如果记录足够多，取最近3次；否则取所有记录
        recent_count = min(3, len(student_data))
        recent_data = student_data.iloc[-recent_count:]
        momentum = recent_data['learning_velocity'].mean()
        
        # 3. 突破能力 - 统计突破次数
        breakthrough_count = student_data['breakthrough'].sum()
        
        # 4. 韧性指数 - 平台期后的恢复能力
        resilience = 0
        if len(student_data) >= 3:
            post_plateau_growth = []
            for i in range(len(student_data) - 1):
                if student_data.iloc[i]['in_plateau'] and i < len(student_data) - 1:
                    post_plateau_growth.append(student_data.iloc[i+1]['learning_velocity'])
        
            resilience = np.mean(post_plateau_growth) if post_plateau_growth else 0
        
        # 5. 综合潜力分数计算
        # 应用非线性加权
        potential_score = (
            base_growth * 0.3 + 
            momentum * 0.3 +
            np.log1p(float(breakthrough_count)) * 10 * 0.2 +
            resilience * 0.2
        )
        
        # 转换为0-100的标准分数（在完成所有计算后规范化）
        # 这里只返回原始分数，规范化在收集所有学生后进行
        
        return {
            'student_id': student_id,
            'potential_score': potential_score,
            'base_growth': base_growth,
            'momentum': momentum,
            'breakthrough_count': breakthrough_count,
            'resilience': resilience
        }

