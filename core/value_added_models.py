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
from core.management.commands.education_data_provider import EducationDataProvider  # 数据提供器

# 配置日志
logger = logging.getLogger(__name__)

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

        self.provider = EducationDataProvider(**kwargs)
        
        # 加载数据
        self.data = self.provider.get_data()
        
        logger.info(f"加载了{len(self.data)}条数据")
        logger.info(f"DataProvider提供的数据字段: {self.data.columns.tolist()}")
        return self.data
    
    def _process_pre_post_tests(self, data, baseline_exam=None):
        """
        处理前测后测数据
        
        为增值模型创建前测和后测成绩字段
        
        Args:
            data: 数据框
            baseline_exam: 基准考试ID（可选）
            
        Returns:
            DataFrame: 处理后的数据框
        """
        # 检查考试ID列是否存在
        if 'exam_id' not in data.columns:
            logger.error("数据中缺少exam_id列")
            raise ValueError("数据格式错误：缺少exam_id列")
        
        # 获取所有不同的考试ID
        all_exams = data['exam_id'].unique().tolist()
        
        # 检查基准考试是否存在
        if baseline_exam is not None and baseline_exam not in all_exams:
            logger.warning(f"指定的基准考试 {baseline_exam} 不在数据集中")
            logger.info(f"可用的考试ID: {', '.join(all_exams)}")
            logger.info("将使用默认的第一次考试作为基准")
            baseline_exam = None
        
        # 如果未指定基准考试，使用第一个考试ID
        if baseline_exam is None:
            # 根据考试时间排序（如果有）或使用第一个考试
            if 'exam_date' in data.columns:
                sorted_exams = data.sort_values('exam_date')['exam_id'].unique()
                baseline_exam = sorted_exams[0]
            else:
                baseline_exam = all_exams[0]
            logger.info(f"使用 {baseline_exam} 作为基准考试")
        
        # 复制数据以避免修改原始数据
        result_data = data.copy()
        
        # 创建前测和后测标记
        result_data['is_baseline'] = result_data['exam_id'] == baseline_exam
        
        # 提取基准考试数据
        baseline_data = result_data[result_data['is_baseline']].copy()
        
        # 如果数据中有学生ID列
        if 'student_id' in data.columns:
            # 创建学生ID到基准分数的映射
            prior_scores = dict(zip(baseline_data['student_id'], baseline_data['standard_score']))
            
            # 创建前测分数列
            result_data['prior_score'] = result_data['student_id'].map(prior_scores)
            
            # 检查是否所有学生都有前测分数
            missing_prior = result_data['prior_score'].isna().sum()
            if missing_prior > 0:
                logger.warning(f"{missing_prior}名学生缺少基准考试分数，将使用平均分填充")
                # 使用平均分填充缺失值
                mean_prior = baseline_data['standard_score'].mean()
                result_data['prior_score'].fillna(mean_prior, inplace=True)
        
        # 如果使用数值索引代替ID
        elif 'student_idx' in data.columns:
            # 创建学生索引到基准分数的映射
            prior_scores = dict(zip(baseline_data['student_idx'], baseline_data['standard_score']))
            
            # 创建前测分数列
            result_data['prior_score'] = result_data['student_idx'].map(prior_scores)
            
            # 检查是否所有学生都有前测分数
            missing_prior = result_data['prior_score'].isna().sum()
            if missing_prior > 0:
                logger.warning(f"{missing_prior}名学生缺少基准考试分数，将使用平均分填充")
                # 使用平均分填充缺失值
                mean_prior = baseline_data['standard_score'].mean()
                result_data['prior_score'].fillna(mean_prior, inplace=True)
        else:
            raise ValueError("数据中缺少student_id或student_idx字段")
        
        # 返回处理后的数据
        return result_data
    
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
            logger.warning("数据中缺少class_id字段，无法处理班级ID")
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

    def _clean_data(self, data, **kwargs):
        """减少过滤条件，保留更多学生数据"""
        cleaned_data = data.copy()
        
        # 减小最小班级人数要求
        min_class_size = kwargs.get('min_class_size', 5)  # 原为10
        
        # 按班级统计学生数
        class_sizes = cleaned_data.groupby('class_id')['student_id'].nunique()
        valid_classes = class_sizes[class_sizes >= min_class_size].index
        
        # 保留有效班级的数据
        cleaned_data = cleaned_data[cleaned_data['class_id'].isin(valid_classes)]
        
        return cleaned_data

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
        self.data_processor = data_processor
        self.model = None
        self.metrics = {}
        self.result = None
    

    
    # 辅助方法 - 供子类调用的数据处理工具函数
    def _process_pre_post_tests(self, data, baseline_exam=None):
        """处理前测后测数据"""
        processors = self.data_processor.get_data_processors()
        return processors['process_pre_post_tests'](data, baseline_exam)
    
    def _filter_pretest_data(self, data, baseline_exam=None):
        """过滤前测数据"""
        processors = self.data_processor.get_data_processors()
        return processors['filter_pretest_data'](data, baseline_exam)
    
    def _create_numeric_indices(self, data):
        """创建数值索引"""
        processors = self.data_processor.get_data_processors()
        return processors['create_numeric_indices'](data)
    
    def _ensure_names_and_ids(self, data):
        """确保学生、学校、班级名称和ID字段"""
        processors = self.data_processor.get_data_processors()
        data = processors['ensure_school_names'](data)
        data = processors['ensure_student_names'](data)
        data = processors['process_class_ids'](data)
        data = processors['generate_display_ids'](data)
        return data
    
    def fit(self, data=None, skip_data_prep=False):  # 添加参数
        """
        拟合模型
        
        Args:
            data: 原始数据，如果为None则使用初始化时的数据
            skip_data_prep: 是否跳过数据准备（如果已在外部处理）
            
        Returns:
            self: 支持链式调用
        """
        if data is not None:
            self.raw_data = data
        
        # 准备数据，如果未跳过
        if self.data is None and not skip_data_prep:
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
    def get_export_field_mapping(self):
        """
        获取字段映射关系，用于Excel导出
        
        Returns:
            dict: 包含字段映射的字典，格式为 {level: {原字段: 目标字段}}
        """
        return {}  # 默认为空，由子类实现    
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

    @abstractmethod
    def prepare_data(self, data=None):
        """
        准备模型所需数据 - 抽象方法，子类必须实现
        
        Args:
            data: 输入数据，如果为None则使用初始化时的数据
            
        Returns:
            DataFrame: 准备好的建模数据
        """
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
        if df.empty:
            logger.warning(f"没有增值效应数据，跳过绘图")
            return
        
        plt.figure(figsize=(10, 6))
        
        # 查找效应列名 - 适应不同版本的输出格式
        effect_col = None
        for possible_col in ['effect', 'mean', 'value_added']:
            if possible_col in df.columns:
                effect_col = possible_col
                break
        
        if effect_col is None:
            logger.error(f"无法找到效应列，可用列：{df.columns.tolist()}")
            return
        
        # 使用找到的列名绘图
        plt.hist(df[effect_col], bins=20, alpha=0.7)
        plt.title(title)
        plt.xlabel('增值效应值')
        plt.ylabel('频率')
        plt.grid(True, linestyle='--', alpha=0.7)
        
        # 添加垂直线表示均值
        mean_effect = df[effect_col].mean()
        plt.axvline(mean_effect, color='r', linestyle='--', 
                    label=f'均值: {mean_effect:.4f}')
        
        plt.legend()
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
                
                # 从模型对象获取字段映射（如果有）
                field_mapping = {}
                if model_object and hasattr(model_object, 'get_export_field_mapping'):
                    field_mapping = model_object.get_export_field_mapping()
                
                # 写入各层级增值效应
                for level in ['schools', 'classes', 'students']:
                    if level in self.result and not self.result[level].empty:
                        df = self.result[level].copy()
                        
                        # 使用模型提供的映射（优先）
                        level_mapping = field_mapping.get(level, {})
                        common_mapping = field_mapping.get('common', {})
                        
                        # 合并通用映射和层级特定映射
                        column_rename = {**common_mapping, **level_mapping}
                        
                        # 回退到内置映射（如果模型没有提供）
                        if not column_rename:
                            column_rename = self._get_default_field_mapping(level)
                        
                        # 应用字段映射
                        for old_name, new_name in column_rename.items():
                            if old_name in df.columns:
                                df.rename(columns={old_name: new_name}, inplace=True)
                        
                        # 如果没有名称列，尝试从实体ID创建
                        if '名称' not in df.columns:
                            entity_type = '学校' if level == 'schools' else '班级'
                            df['名称'] = df['entity_id'].apply(lambda x: f"{entity_type}{x}")
                        
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
    贝叶斯多层次增值模型
    
    使用完全贝叶斯推断方法估计各层级效应
    """
    
    def __init__(self, data=None, data_processor=None, baseline_exam=None, mcmc_samples=1000, tune=500, random_seed=42):
        """
        初始化贝叶斯多层次模型
        
        Args:
            data: 建模数据
            data_processor: 数据处理器
            baseline_exam: 基准考试ID（可选）
            mcmc_samples: MCMC采样次数
            tune: MCMC调整步数
            random_seed: 随机数种子
        """
        # 调用父类的初始化方法（不传递baseline_exam）
        super().__init__(data, data_processor)
        
        # 存储基准考试ID
        self.baseline_exam = baseline_exam
        
        # 贝叶斯特有参数
        self.mcmc_samples = mcmc_samples
        self.tune = tune
        self.random_seed = random_seed
        self.trace = None
        self.pymc_model = None
    
    def prepare_data(self, data=None):
        """
        准备贝叶斯增值模型的数据
        
        重要设计说明:
        1. 将基准考试(前测)成绩提取为prior_score
        2. 从建模数据中移除基准考试记录
        3. 只使用后测记录进行实际建模
        
        这是增值模型的标准设计 - 我们感兴趣的是学生在基准考试后的进步
        """
        # 首先调用基类的prepare_data获取基础处理后的数据
        model_data = super().prepare_data(data)
        
        # 获取数据处理工具
        processors = self.data_processor.get_data_processors()
        
        # 显示处理前的数据信息
        logger.info(f"贝叶斯模型准备数据，接收的数据字段: {sorted(model_data.columns.tolist())}")
        logger.info(f"数据样本量: {len(model_data)}行")

        # 创建数值索引
        self.data_processor._create_numeric_indices(model_data)

        # 处理前测后测成绩 - 增加错误处理
        try:
            # 检查指定的基准考试是否存在
            if self.baseline_exam is None:
                logger.warning(f"指定的基准考试 {self.baseline_exam} 不存在，将使用默认的第一次考试作为基准")
                self.baseline_exam = None  # 置为None以使用默认逻辑
                
            # 调用处理方法
            model_data = self.data_processor._process_pre_post_tests(model_data, self.baseline_exam)
        except Exception as e:
            logger.error(f"处理前测后测数据时出错: {str(e)}")
            raise ValueError(f"处理前测后测数据失败: {str(e)}")
        
        # 贝叶斯模型特定处理
        # 1. 确保所有必需字段存在
        required_fields = ['student_idx', 'class_idx', 'prior_score', 'standard_score','school_idx']
        missing_fields = [f for f in required_fields if f not in model_data.columns]
        if missing_fields:
            raise ValueError(f"贝叶斯模型缺少必要字段: {missing_fields}")
            
        # 2. 处理异常值和缺失值
        model_data = self._handle_outliers_and_missing(model_data)
        
        # 3. 添加学校层级平均分（如果有学校信息）
        
        school_means = model_data.groupby('school_idx')['prior_score'].mean().reset_index()
        school_means.columns = ['school_idx', 'school_mean_prior']
        model_data = pd.merge(model_data, school_means, on='school_idx', how='left')
        logger.info("已添加学校平均前测成绩作为协变量")


        # 4. 添加班级平均分
        class_means = model_data.groupby('class_idx')['prior_score'].mean().reset_index()
        class_means.columns = ['class_idx', 'class_mean_prior']
        model_data = pd.merge(model_data, class_means, on='class_idx', how='left')
        logger.info("已添加班级平均前测成绩作为协变量")


        # 5. 创建中心化变量（对贝叶斯模型采样很有用）
        model_data['prior_score_centered'] = model_data['prior_score'] - model_data['prior_score'].mean()
        logger.info("已创建中心化前测分数变量")
        
        # 记录数据处理后的统计信息
        logger.info(f"贝叶斯模型数据准备完成，包含{model_data['student_idx'].nunique()}名学生，" + 
                   f"{model_data['class_idx'].nunique()}个班级")
        if 'school_idx' in model_data.columns:
            logger.info(f"包含{model_data['school_idx'].nunique()}所学校")
                # 6. 确保必要的名称字段（使用处理器功能）
        self.data = processors['ensure_student_names'](self.data)
        self.data = processors['ensure_school_names'](self.data)
        self.data = processors['ensure_class_names'](self.data)
        self.data = processors['ensure_grade_field'](self.data)
        # 保存处理后的数据
        self.data = model_data
        
        # 添加调试日志
        logger.info(f"数据列: {self.data.columns.tolist()}")
        

        
        # 创建详细的班级和学校映射表
        self.class_mapping = (
            self.data[['class_idx', 'class_id', 'class_name', 'school_id', 'school_name', 'display_id']]
            .drop_duplicates()
            .set_index('class_idx')
        )
        
        self.school_mapping = (
            self.data[['school_idx', 'school_id', 'school_name']]
            .drop_duplicates()
            .set_index('school_idx')
        )
        
        logger.info(f"创建了{len(self.class_mapping)}个班级的映射信息")
        logger.info(f"创建了{len(self.school_mapping)}个学校的映射信息")
        
        # 在prepare_data末尾
        logger.info(f"数据准备后的字段: {list(self.data.columns)}")
        logger.info(f"样本班级名称: {self.data['class_name'].unique()[:5]}")
        logger.info(f"样本学校名称: {self.data['school_name'].unique()[:5]}")
        
        return self.data
        
    def _handle_outliers_and_missing(self, data):
        """
        处理异常值和缺失值
        
        Args:
            data: 输入数据框
            
        Returns:
            DataFrame: 处理后的数据框
        """
        # 复制数据避免修改原始数据
        df = data.copy()
        
        # 处理缺失值
        for field in ['prior_score', 'standard_score']:
            if df[field].isna().any():
                logger.warning(f"检测到{field}存在缺失值，将使用均值填充")
                df[field].fillna(df[field].mean(), inplace=True)
        
        # 处理异常值（使用3倍标准差法）
        for field in ['prior_score', 'standard_score']:
            mean, std = df[field].mean(), df[field].std()
            lower_bound, upper_bound = mean - 3*std, mean + 3*std
            outliers = df[(df[field] < lower_bound) | (df[field] > upper_bound)]
            
            if not outliers.empty:
                logger.warning(f"检测到{len(outliers)}个{field}异常值，将进行处理")
                # 将异常值设为边界值
                df.loc[df[field] < lower_bound, field] = lower_bound
                df.loc[df[field] > upper_bound, field] = upper_bound
        
        return df
        
    def _build_model(self):
        """构建贝叶斯多层次模型（优化版）"""
        import pymc as pm
        import numpy as np
        
        # 数据提取保持不变
        prior_score = self.data['prior_score'].values
        standard_score = self.data['standard_score'].values
        student_idx = self.data['student_idx'].values
        class_idx = self.data['class_idx'].values
        school_idx = self.data['school_idx'].values
        
        # 计算唯一实体数量
        n_students = len(np.unique(student_idx))
        n_classes = len(np.unique(class_idx))
        n_schools = len(np.unique(school_idx))
        
        # 标准化输入数据以提高数值稳定性
        prior_score_std = (prior_score - np.mean(prior_score)) / np.std(prior_score)
        standard_score_std = (standard_score - np.mean(standard_score)) / np.std(standard_score)
        
        logger.info(f"构建贝叶斯模型: {n_students}名学生, {n_classes}个班级, {n_schools}所学校")
        
        # 创建PyMC模型
        with pm.Model() as model:
            # 更合适的先验分布
            intercept = pm.Normal('intercept', mu=0, sigma=10)  # 减小方差
            beta_prior = pm.Normal('beta_prior', mu=0.8, sigma=0.5)  # 更合理的预期和范围
            
            # 使用更稳定的先验
            sigma_student = pm.HalfNormal('sigma_student', sigma=2)  # 替换HalfCauchy
            sigma_class = pm.HalfNormal('sigma_class', sigma=2)     # 替换HalfCauchy
            sigma_school = pm.HalfNormal('sigma_school', sigma=2)   # 替换HalfCauchy
            
            # 使用非中心参数化减少相关性
            student_raw = pm.Normal('student_raw', mu=0, sigma=1, shape=n_students)
            class_raw = pm.Normal('class_raw', mu=0, sigma=1, shape=n_classes)  
            school_raw = pm.Normal('school_raw', mu=0, sigma=1, shape=n_schools)
            
            # 将原始变量转换为实际效应
            student_effects = pm.Deterministic('student_effects', student_raw * sigma_student)
            class_effects = pm.Deterministic('class_effects', class_raw * sigma_class)
            school_effects = pm.Deterministic('school_effects', school_raw * sigma_school)
            
            # 残差标准差
            sigma_e = pm.HalfNormal('sigma_e', sigma=2)  # 替换HalfCauchy
            
            # 线性预测
            mu = (intercept + 
                beta_prior * prior_score_std + 
                school_effects[school_idx] + 
                class_effects[class_idx] + 
                student_effects[student_idx])
            
            # 似然函数
            Y = pm.Normal('Y', mu=mu, sigma=sigma_e, observed=standard_score_std)
        
        return model
    
    def _fit_model(self):
        """
        拟合贝叶斯多层次模型
        
        使用PyMC执行MCMC采样
        """
        import pymc as pm
        import arviz as az
        
        if self.data is None:
            raise ValueError("请先调用prepare_data准备数据")
        
        # 创建模型
        self.pymc_model = self._build_model()
        
        # 执行MCMC采样
        try:
            # 先尝试找到最大后验估计作为起点
            with self.pymc_model:
                try:
                    # 寻找MAP估计作为初始值
                    logger.info("寻找MAP估计以优化初始值...")
                    self.map_estimate = pm.find_MAP()
                except Exception as e:
                    logger.warning(f"寻找MAP估计失败: {str(e)}，将使用默认初始值")
                    start = None
            
            # MCMC采样参数优化
            with self.pymc_model:
                self.trace = pm.sample(
                    draws=self.mcmc_samples,
                    tune=self.tune,  # 增加调优步数
                    chains=2,
                    cores=4,
                    random_seed=self.random_seed,
                    step=pm.NUTS(target_accept=0.9),
                    compute_convergence_checks=True,  # 恢复收敛检查
                    progressbar=True,
                    return_inferencedata=True
                )
            
            # 计算基础评估指标
            with self.pymc_model:
                # 计算指标时捕获异常，避免因一个指标失败而终止整个过程
                try:
                    # 计算基本统计量
                    summary = az.summary(self.trace)
                    self.metrics['r_hat_max'] = float(summary['r_hat'].max())
                    self.metrics['r_hat_min'] = float(summary['r_hat'].min())
                    self.metrics['ess_min'] = float(summary['ess_bulk'].min())
                    self.metrics['divergences'] = int(np.sum(self.trace.sample_stats.diverging.values))
                except Exception as e:
                    logger.warning(f"计算基本统计量时出错: {str(e)}")
                    
                # 尝试计算LOO指标，使用新版API处理log_likelihood
                try:
                    # 先检查log_likelihood是否存在
                    if hasattr(self.trace, 'log_likelihood') or (
                        hasattr(self.trace, 'sample_stats') and 
                        hasattr(self.trace.sample_stats, 'log_likelihood')):
                        
                        # 使用新版ArviZ API：ELPDData对象
                        loo_data = az.loo(self.trace, scale="deviance")
                        # 直接访问elpd_loo属性而不是.loo
                        self.metrics['loo'] = float(loo_data.elpd_loo)
                        # 访问se属性
                        self.metrics['loo_se'] = float(loo_data.se)
                        # 保存更多LOO相关统计量
                        if hasattr(loo_data, 'p_loo'):
                            self.metrics['p_loo'] = float(loo_data.p_loo)
                    else:
                        # 如果没有log_likelihood，计算后验预测样本
                        posterior_pred = pm.sample_posterior_predictive(self.trace, 
                                                                  model=self.pymc_model)
                        self.metrics['loo'] = None  # 无法计算LOO
                        self.metrics['mse'] = float(((posterior_pred.posterior_predictive['Y'].mean(dim=('chain', 'draw')).values - 
                                           self.data['standard_score'].values) ** 2).mean())
                except Exception as e:
                    logger.warning(f"计算评估指标时出错: {str(e)}")
                    self.metrics['loo'] = None
                    self.metrics['loo_se'] = None
                    
                # 计算或估计其他基本指标
                try:
                    # R^2计算
                    self.metrics['r_squared'] = self._calculate_r_squared()
                except Exception as e:
                    logger.warning(f"计算R²时出错: {str(e)}")
            
            # 标记模型已拟合
            self.is_fitted = True
            # 移除此处的日志记录
            # logger.info(f"贝叶斯模型拟合完成")  <-- 注释掉这行
            
            # 返回self便于链式调用
            return self
            
        except Exception as e:
            logger.exception(f"MCMC采样失败: {str(e)}")
            raise ValueError(f"贝叶斯模型拟合失败: {str(e)}")
    
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
    
    def _validate_data(self):
        """
        验证贝叶斯模型所需数据
        
        确保数据符合贝叶斯模型的要求，检查必要字段是否存在。
        
        Returns:
            bool: 验证通过返回True
            
        Raises:
            ValueError: 如果数据不符合要求
        """
        # 检查基础必要字段
        required_fields = ['student_idx', 'standard_score', 'prior_score']
        
        # 贝叶斯模型特有字段
        model_specific_fields = ['class_idx', 'school_idx']
        
        # 合并所有必要字段
        all_required_fields = required_fields + model_specific_fields
        
        # 检查数据是否为空
        if self.data is None or len(self.data) == 0:
            raise ValueError("数据为空，无法进行贝叶斯模型分析")
        
        # 检查字段是否存在
        missing_fields = [f for f in all_required_fields if f not in self.data.columns]
        if missing_fields:
            logger.warning(f"数据缺少贝叶斯模型必要字段: {missing_fields}")
            return False
        
        # 检查数据量是否足够
        if len(self.data) < 100:  # 贝叶斯模型通常需要足够的样本量
            logger.warning(f"数据量可能不足({len(self.data)}条)，贝叶斯模型可能不稳定")
        
        # 检查数据类型
        numeric_fields = ['standard_score', 'prior_score']
        for field in numeric_fields:
            if field in self.data.columns and not pd.api.types.is_numeric_dtype(self.data[field]):
                raise ValueError(f"字段 {field} 必须是数值类型")
        
        return True

    def _calculate_value_added_impl(self):
        """
        计算贝叶斯模型的增值效应
        
        从贝叶斯模型的MCMC采样结果中提取随机效应，计算各层级的增值分数
        
        Returns:
            dict: 包含各层级增值效应的字典
        """
        import arviz as az
        import pandas as pd
        import numpy as np
        
        # 获取原始分数的标准差，用于还原效应尺度
        score_std = np.std(self.data['standard_score'])
        
        # 提取班级效应并计算概要统计
        class_value_added = az.summary(self.trace.posterior.class_effects)
        class_value_added = class_value_added.rename(columns={'mean': 'effect', 'sd': 'std_dev',
                                            'hdi_3%': 'lower', 'hdi_97%': 'upper'})
        
        # 调整效应尺度
        class_value_added['effect'] = class_value_added['effect'] * score_std
        class_value_added['std_dev'] = class_value_added['std_dev'] * score_std
        class_value_added['lower'] = class_value_added['lower'] * score_std
        class_value_added['upper'] = class_value_added['upper'] * score_std
        
        # 添加班级索引列
        class_value_added['class_idx'] = class_value_added.index
        
        # 使用新创建的映射表添加班级详细信息
        if hasattr(self, 'class_mapping') and not self.class_mapping.empty:
            logger.info(f"使用class_mapping表添加班级详细信息，包含字段: {self.class_mapping.columns.tolist()}")
            
            # 将class_mapping的内容合并到结果中
            class_mapping_df = self.class_mapping.reset_index()
            
            # 打印调试信息
            logger.info(f"class_value_added['class_idx']类型: {class_value_added['class_idx'].dtype}")
            logger.info(f"class_mapping_df['class_idx']类型: {class_mapping_df['class_idx'].dtype}")
            
            # 从字符串索引中提取数值索引
            # 例如从'class_effects[0]'提取出0
            if class_value_added['class_idx'].dtype == 'object':
                try:
                    # 尝试从字符串中提取索引数字
                    class_value_added['numeric_idx'] = class_value_added['class_idx'].str.extract(r'\[(\d+)\]').astype(int)
                    logger.info(f"从字符串索引中提取了数值索引")
                    
                    # 用提取的数值索引进行合并
                    class_value_added = class_value_added.merge(
                        class_mapping_df, 
                        left_on='numeric_idx',  # 使用提取的数值索引
                        right_on='class_idx',   # 映射表中的数值索引
                        how='left'
                    )
                    
                    # 删除冗余列
                    if 'class_idx_y' in class_value_added.columns:
                        class_value_added = class_value_added.rename(columns={'class_idx_x': 'class_idx'})
                        class_value_added = class_value_added.drop(columns=['class_idx_y'])
                        
                    logger.info(f"使用提取的数值索引完成合并")
                except Exception as e:
                    logger.warning(f"提取数值索引失败: {str(e)}")
                    # 转换失败时，采用常规合并
                    class_mapping_df['class_idx'] = class_mapping_df['class_idx'].astype(str)
                    class_value_added = class_value_added.merge(
                        class_mapping_df, 
                        on='class_idx', 
                        how='left'
                    )
            else:
                # 常规类型转换和合并
                class_mapping_df['class_idx'] = class_mapping_df['class_idx'].astype(class_value_added['class_idx'].dtype)
                class_value_added = class_value_added.merge(
                    class_mapping_df, 
                    on='class_idx', 
                    how='left'
                )
        
        # 检查合并后的结果是否包含班级和学校名称
        if class_value_added['class_name'].isna().any() or class_value_added['school_name'].isna().any():
            missing_class = class_value_added['class_name'].isna().sum()
            missing_school = class_value_added['school_name'].isna().sum()
            logger.warning(f"合并后有{missing_class}个班级缺少名称，{missing_school}个班级缺少学校名称")
            
            # 记录一些示例来帮助调试
            missing_examples = class_value_added[class_value_added['class_name'].isna()]['class_idx'].tolist()[:3]
            logger.warning(f"缺少名称的班级索引示例: {missing_examples}")
            
            # 检查这些班级索引是否在映射表中
            if missing_examples:
                for idx in missing_examples:
                    logger.warning(f"班级索引{idx}在映射表中: {idx in self.class_mapping.index}")
        else:
            # 回退到现有的逻辑
            logger.warning("未找到班级映射表，尝试使用备用方法添加班级信息")
            
            # ...保留现有的备用逻辑...
            if hasattr(self, 'class_info') and isinstance(self.class_info, pd.DataFrame):
                logger.info(f"使用存储的班级映射信息添加详细数据")
                # 使用存储的映射信息
                for col in self.class_info.columns:
                    if col != 'class_idx':  # 避免重复添加class_idx
                        class_value_added[col] = class_value_added['class_idx'].map(
                            self.class_info[col]
                        )
                logger.info(f"从存储的映射添加了列: {self.class_info.columns.tolist()}")
        
        # 排序和添加排名
        class_value_added = class_value_added.sort_values('effect', ascending=False)
        class_value_added['rank'] = np.arange(1, len(class_value_added) + 1)
        
        # 记录效应统计信息
        logger.info(f"班级增值效应范围: {class_value_added['effect'].min():.4f} 到 {class_value_added['effect'].max():.4f}")
        logger.info(f"班级效应表最终字段: {class_value_added.columns.tolist()}")
        
        # 学校增值效应 - 使用新的映射表
        if hasattr(self.trace.posterior, 'school_effects'):
            school_value_added = az.summary(self.trace.posterior.school_effects)
            school_value_added = school_value_added.rename(columns={'mean': 'effect', 'sd': 'std_dev',
                                                       'hdi_3%': 'lower', 'hdi_97%': 'upper'})
            
            # 调整效应尺度
            school_value_added['effect'] = school_value_added['effect'] * score_std
            school_value_added['std_dev'] = school_value_added['std_dev'] * score_std
            school_value_added['lower'] = school_value_added['lower'] * score_std
            school_value_added['upper'] = school_value_added['upper'] * score_std
            
            # 添加学校索引列
            school_value_added['school_idx'] = school_value_added.index
            
            # 使用新创建的学校映射表
            if hasattr(self, 'school_mapping') and not self.school_mapping.empty:
                logger.info(f"使用school_mapping表添加学校详细信息，包含字段: {self.school_mapping.columns.tolist()}")
                
                # 将school_mapping的内容合并到结果中
                school_mapping_df = self.school_mapping.reset_index()
                
                # 从字符串索引中提取数值索引
                if school_value_added['school_idx'].dtype == 'object':
                    try:
                        # 提取索引数字
                        school_value_added['numeric_idx'] = school_value_added['school_idx'].str.extract(r'\[(\d+)\]').astype(int)
                        
                        # 用提取的数值索引进行合并
                        school_value_added = school_value_added.merge(
                            school_mapping_df, 
                            left_on='numeric_idx',
                            right_on='school_idx',
                            how='left'
                        )
                        
                        # 删除冗余列
                        if 'school_idx_y' in school_value_added.columns:
                            school_value_added = school_value_added.rename(columns={'school_idx_x': 'school_idx'})
                            school_value_added = school_value_added.drop(columns=['school_idx_y'])
                    except Exception as e:
                        logger.warning(f"提取学校数值索引失败: {str(e)}")
                        school_mapping_df['school_idx'] = school_mapping_df['school_idx'].astype(str)
                        school_value_added = school_value_added.merge(
                            school_mapping_df, 
                            on='school_idx', 
                            how='left'
                        )
                else:
                    # 常规类型转换和合并
                    school_mapping_df['school_idx'] = school_mapping_df['school_idx'].astype(school_value_added['school_idx'].dtype)
                    school_value_added = school_value_added.merge(
                        school_mapping_df, 
                        on='school_idx', 
                        how='left'
                    )
            else:
                # 回退到现有逻辑
                logger.warning("未找到学校映射表，尝试使用备用方法添加学校信息")
                # ...保留现有的备用逻辑...
            
            # 排序和添加排名
            school_value_added = school_value_added.sort_values('effect', ascending=False)
            school_value_added['rank'] = np.arange(1, len(school_value_added) + 1)
            
            if len(school_value_added) > 0:
                logger.info(f"学校增值效应范围: {school_value_added['effect'].min():.4f} 到 {school_value_added['effect'].max():.4f}")
        else:
            logger.warning("模型中没有学校效应")
            school_value_added = pd.DataFrame()
        
        # 学生增值效应 - 使用同样的映射逻辑
        if hasattr(self.trace.posterior, 'student_effects'):
            student_value_added = az.summary(self.trace.posterior.student_effects)
            student_value_added = student_value_added.rename(columns={'mean': 'effect', 'sd': 'std_dev',
                                                        'hdi_3%': 'lower', 'hdi_97%': 'upper'})
            
            # 调整效应尺度
            student_value_added['effect'] = student_value_added['effect'] * score_std
            student_value_added['std_dev'] = student_value_added['std_dev'] * score_std
            student_value_added['lower'] = student_value_added['lower'] * score_std
            student_value_added['upper'] = student_value_added['upper'] * score_std
            
            # 添加学生索引列
            student_value_added['student_idx'] = student_value_added.index
            
            # 添加学生信息
            if 'student_idx' in self.data.columns:
                student_id_map = self.data.drop_duplicates('student_idx').set_index('student_idx')
                for col in ['student_id', 'student_name', 'class_id', 'school_id', 'class_idx', 'school_idx']:
                    if col in student_id_map.columns:
                        student_value_added[col] = student_value_added['student_idx'].map(
                            student_id_map[col]
                        )
            
            # 排序和添加排名
            student_value_added = student_value_added.sort_values('effect', ascending=False)
            student_value_added['rank'] = np.arange(1, len(student_value_added) + 1)
            
            # 如果缺少学生ID，创建简单标识符
            if 'student_id' not in student_value_added.columns:
                logger.warning("未找到学生ID映射，将使用索引作为学生ID")
                student_value_added['student_id'] = [f"学生{i+1}" for i in range(len(student_value_added))]
                student_value_added['student_name'] = student_value_added['student_id']
            
            if len(student_value_added) > 0:
                logger.info(f"学生增值效应范围: {student_value_added['effect'].min():.4f} 到 {student_value_added['effect'].max():.4f}")
        else:
            logger.warning("模型中没有学生效应")
            student_value_added = pd.DataFrame()
        
        return {
            'schools': school_value_added,
            'classes': class_value_added,
            'students': student_value_added if 'student_value_added' in locals() else pd.DataFrame()
        }

    def _predict_impl(self, new_data=None):
        """
        使用拟合后的贝叶斯模型进行预测
        
        Args:
            new_data: 新数据，如果为None则使用拟合时的数据
            
        Returns:
            DataFrame: 包含预测结果的数据框
        """
        if self.trace is None:
            raise ValueError("模型尚未拟合，请先调用fit()方法")
        
        # 使用原始数据还是新数据
        predict_data = new_data if new_data is not None else self.data
        
        # 获取模型参数后验均值
        intercept = float(self.trace.posterior['intercept'].mean(dim=['chain', 'draw']).values)
        beta_prior = float(self.trace.posterior['beta_prior'].mean(dim=['chain', 'draw']).values)
        
        # 基础预测（仅使用固定效应）
        predictions = intercept + beta_prior * predict_data['prior_score']
        
        # 如果是原始数据，添加随机效应
        if new_data is None:
            # 学生效应
            if 'student_effects' in self.trace.posterior and 'student_idx' in predict_data.columns:
                student_effects = self.trace.posterior['student_effects'].mean(dim=['chain', 'draw']).values
                predictions += student_effects[predict_data['student_idx'].values]
            
            # 班级效应
            if 'class_effects' in self.trace.posterior and 'class_idx' in predict_data.columns:
                class_effects = self.trace.posterior['class_effects'].mean(dim=['chain', 'draw']).values
                predictions += class_effects[predict_data['class_idx'].values]
            
            # 学校效应
            if 'school_effects' in self.trace.posterior and 'school_idx' in predict_data.columns:
                school_effects = self.trace.posterior['school_effects'].mean(dim=['chain', 'draw']).values
                predictions += school_effects[predict_data['school_idx'].values]
        
        # 创建结果数据框
        results = predict_data.copy()
        results['predicted_score'] = predictions
        
        # 计算残差
        if 'standard_score' in results.columns:
            results['residual'] = results['standard_score'] - results['predicted_score']
        
        return results

    def get_posterior_summary(self):
        """
        获取模型参数后验分布的统计概要
        
        Returns:
            DataFrame: 包含参数后验分布统计量的数据框
        """
        if self.trace is None:
            raise ValueError("模型尚未拟合，请先调用fit()方法")
        
        # 使用Arviz提取后验统计量
        summary = az.summary(self.trace)
        
        # 添加参数类型标签
        param_types = []
        for param in summary.index:
            if param.startswith('intercept') or param.startswith('beta'):
                param_types.append('固定效应')
            elif param.startswith('sigma'):
                param_types.append('方差组件')
            elif 'effects' in param:
                if 'school' in param:
                    param_types.append('学校随机效应')
                elif 'class' in param:
                    param_types.append('班级随机效应')
                elif 'student' in param:
                    param_types.append('学生随机效应')
                else:
                    param_types.append('随机效应')
            else:
                param_types.append('其他参数')
        
        # 添加参数类型列
        summary['param_type'] = param_types
        
        return summary

    def save_results(self, output_dir, filename_prefix="bayesian_value_added", value_added=None):
        """
        保存贝叶斯模型结果
        
        Args:
            output_dir: 输出目录路径
            filename_prefix: 文件名前缀
            value_added: 预先计算的增值效应，如果提供则不会重新计算
            
        Returns:
            dict: 包含已保存文件路径的字典
        """
        # 确保目录存在
        os.makedirs(output_dir, exist_ok=True)
        
        # 保存文件路径字典
        saved_paths = {}
        
        # 1. 保存模型参数
        try:
            # 获取后验分布摘要
            posterior_summary = self.get_posterior_summary()
            summary_path = os.path.join(output_dir, f"{filename_prefix}_posterior_summary.csv")
            posterior_summary.to_csv(summary_path)
            saved_paths['posterior_summary'] = summary_path
            
            # 保存参数后验图
            if self.trace is not None:
                # 保存trace图
                try:
                    import arviz as az
                    
                    # 增加rcParams设置，处理大量变量
                    plt.rcParams['plot.max_subplots'] = 100  # 增加子图数量限制
                    
                    # 只选择关键参数进行可视化，避免太多变量
                    key_params = []
                    if 'intercept' in self.trace.posterior:
                        key_params.append('intercept')
                    if 'beta_prior' in self.trace.posterior:
                        key_params.append('beta_prior')
                    if 'sigma_student' in self.trace.posterior:
                        key_params.append('sigma_student')
                    if 'sigma_class' in self.trace.posterior:
                        key_params.append('sigma_class')
                    if 'sigma_school' in self.trace.posterior:
                        key_params.append('sigma_school')
                    if 'sigma_e' in self.trace.posterior:
                        key_params.append('sigma_e')
                    
                    # 保存后验密度图（只包含关键参数）
                    posterior_plot_path = os.path.join(output_dir, f"{filename_prefix}_posterior_plot.png")
                    az.plot_posterior(self.trace, var_names=key_params)
                    plt.savefig(posterior_plot_path, dpi=300, bbox_inches='tight')
                    plt.close()
                    saved_paths['posterior_plot'] = posterior_plot_path
                    
                    # 保存轨迹图（只包含关键参数）
                    trace_plot_path = os.path.join(output_dir, f"{filename_prefix}_trace_plot.png")
                    az.plot_trace(self.trace, var_names=key_params)
                    plt.savefig(trace_plot_path, dpi=300, bbox_inches='tight')
                    plt.close()
                    saved_paths['trace_plot'] = trace_plot_path
                    
                    # 保存forest图（只包含关键参数）
                    forest_plot_path = os.path.join(output_dir, f"{filename_prefix}_forest_plot.png")
                    az.plot_forest(self.trace, var_names=key_params)
                    plt.savefig(forest_plot_path, dpi=300, bbox_inches='tight')
                    plt.close()
                    saved_paths['forest_plot'] = forest_plot_path
                    
                    logger.info(f"已保存后验分布图: {posterior_plot_path}")
                except Exception as e:
                    logger.warning(f"保存后验分布图时出错: {str(e)}")
        except Exception as e:
            logger.warning(f"保存模型参数时出错: {str(e)}")
        
        # 2. 保存增值效应
        try:
            # 使用传入的值或重新计算
            if value_added is None:
                logger.info("没有提供预计算的增值效应，开始计算...")
                value_added = self.calculate_value_added()
            else:
                logger.info("使用预先计算的增值效应，跳过重复计算")
            
            for level, df in value_added.items():
                if not df.empty:
                    va_path = os.path.join(output_dir, f"{filename_prefix}_{level}_effects.csv")
                    df.to_csv(va_path, index=False)
                    saved_paths[f"{level}_effects"] = va_path
                    logger.info(f"已保存{level}增值效应: {va_path}")
        except Exception as e:
            logger.warning(f"保存增值效应时出错: {str(e)}")
        
        # 3. 安全地保存预测结果
        try:
            # 只有在模型已拟合且有predict方法时尝试
            if hasattr(self, 'result') and self.result is not None and hasattr(self, 'predict'):
                predictions = self.predict()
                pred_path = os.path.join(output_dir, f"{filename_prefix}_predictions.csv")
                
                # 只保存关键列，以节省空间
                pred_columns = ['student_id', 'student_name', 'class_id', 'standard_score', 
                               'prior_score', 'predicted_score', 'residual']
                pred_columns = [col for col in pred_columns if col in predictions.columns]
                
                predictions[pred_columns].to_csv(pred_path, index=False)
                saved_paths['predictions'] = pred_path
                logger.info(f"已保存预测结果: {pred_path}")
            else:
                logger.info("跳过预测结果保存：模型未完全拟合或缺少predict方法")
        except Exception as e:
            logger.warning(f"保存预测结果时出错: {str(e)}")
        
        # 4. 安全地保存模型评估指标
        try:
            # 先检查evaluate_model方法是否存在
            if hasattr(self, 'evaluate_model'):
                metrics = self.evaluate_model()
                metrics_path = os.path.join(output_dir, f"{filename_prefix}_metrics.json")
                with open(metrics_path, 'w') as f:
                    json.dump(metrics, f, indent=4)
                saved_paths['metrics'] = metrics_path
                logger.info(f"已保存评估指标: {metrics_path}")
            elif hasattr(self, 'get_metrics') and callable(self.get_metrics):
                # 尝试使用备用方法
                metrics = self.get_metrics()
                if metrics:
                    metrics_path = os.path.join(output_dir, f"{filename_prefix}_metrics.json")
                    with open(metrics_path, 'w') as f:
                        json.dump(metrics, f, indent=4)
                    saved_paths['metrics'] = metrics_path
                    logger.info(f"已保存评估指标(来自get_metrics): {metrics_path}")
            else:
                logger.info("跳过评估指标保存：模型没有evaluate_model或get_metrics方法")
        except Exception as e:
            logger.warning(f"保存评估指标时出错: {str(e)}")
        
        # 5. 保存模型配置
        try:
            config = {
                'mcmc_samples': self.mcmc_samples,
                'tune': self.tune,
                'random_seed': self.random_seed,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'data_shape': self.data.shape if self.data is not None else None,
                'model_type': 'BayesianValueAddedModel'
            }
            
            config_path = os.path.join(output_dir, f"{filename_prefix}_config.json")
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=4)
            saved_paths['config'] = config_path
            logger.info(f"已保存模型配置: {config_path}")
        except Exception as e:
            logger.warning(f"保存模型配置时出错: {str(e)}")
        
        return saved_paths

    def calculate_value_added(self):
        """
        计算贝叶斯模型的增值效应
        
        Returns:
            dict: 包含各层级增值效应的字典
        """
        # 如果已经拟合模型，调用实现方法
        if hasattr(self, 'trace') and self.trace is not None:
            return self._calculate_value_added_impl()
        else:
            logger.warning("模型尚未拟合，无法计算增值效应")
            return {
                'schools': pd.DataFrame(),
                'classes': pd.DataFrame(),
                'students': pd.DataFrame()
            }

    def diagnose_sampling(self):
        """诊断MCMC采样质量并提供建议"""
        import arviz as az
        import numpy as np
        
        if not hasattr(self, 'trace') or self.trace is None:
            return {"error": "尚未进行MCMC采样"}
        
        # 获取诊断信息
        divergences = int(np.sum(self.trace.sample_stats.diverging.values))
        accept = float(self.trace.sample_stats.accept.mean())
        try:
            rhat_values = az.rhat(self.trace)
            max_rhat = float(rhat_values.max())
            problem_params = rhat_values[rhat_values > 1.05].index.tolist()
        except:
            max_rhat = float('nan')
            problem_params = []
        
        # 生成诊断报告
        diagnosis = {
            "divergences": divergences,
            "acceptance_rate": accept,
            "max_rhat": max_rhat,
            "problem_parameters": problem_params
        }
        
        # 添加警告和建议
        warnings = []
        if divergences > 0:
            warnings.append(f"存在{divergences}个发散样本，可能影响参数估计")
        if max_rhat > 1.05:
            warnings.append(f"最大Rhat值为{max_rhat:.4f}，超过1.05，链可能未收敛")
        if problem_params:
            warnings.append(f"以下参数可能存在问题: {', '.join(problem_params[:5])}")
        
        diagnosis["warnings"] = warnings
        diagnosis["sampling_ok"] = (divergences == 0 and max_rhat <= 1.05)
        
        return diagnosis

    def get_export_field_mapping(self):
        """
        获取贝叶斯模型导出字段映射
        
        Returns:
            dict: 包含字段映射的字典
        """
        return {
            'common': {  # 所有层级通用映射
                'effect': '增值效应',
                'std_dev': '标准误',
                'lower': '置信区间下限',
                'upper': '置信区间上限',
                'rank': '排名'
            },
            'classes': {  # 班级特定映射
                'class_id': '班级ID',
                'class_name': '班级名称',
                'school_name': '所属学校',
                # 其他班级特有字段
            },
            'schools': {
                'school_id': '学校ID',
                'school_name': '学校名称',
                # 其他学校特有字段
            },
            'students': {
                'student_id': '学生ID',
                'student_name': '学生姓名',
                # 其他学生特有字段
            }
        }

    def evaluate_model(self):
        """
        评估贝叶斯模型性能
        
        Returns:
            dict: 包含评估指标的字典
        """
        if self.metrics:
            return self.metrics
        
        # 如果没有缓存的指标，执行评估
        metrics = {}
        
        if hasattr(self, 'result') and self.result is not None:
            try:
                # 使用后验预测检查
                import arviz as az
                
                # 获取一些拟合质量指标
                if hasattr(self.trace, 'sample_stats'):
                    metrics['mean_log_likelihood'] = float(self.trace.sample_stats.lp.mean().item())
                    
                # 包括预测性能指标
                if hasattr(self, 'predict'):
                    try:
                        predictions = self.predict()
                        if 'residual' in predictions.columns:
                            metrics['rmse'] = np.sqrt(np.mean(predictions['residual']**2))
                            metrics['mae'] = np.mean(np.abs(predictions['residual']))
                    except Exception:
                        pass  # 预测失败不影响其他评估
                    
                # Arviz提供的收敛诊断
                if hasattr(self.trace, 'posterior'):
                    try:
                        ess_bulk = az.ess(self.trace, var_names=['class_effects']).to_dataframe().mean().item()
                        r_hat = az.rhat(self.trace, var_names=['class_effects']).to_dataframe().mean().item()
                        
                        metrics['ess_bulk_mean'] = float(ess_bulk)
                        metrics['r_hat_mean'] = float(r_hat)
                        metrics['convergence_good'] = bool(r_hat < 1.05)
                    except Exception:
                        pass  # 诊断失败不影响其他指标
            except Exception as e:
                logger.warning(f"评估模型时出错: {str(e)}")
        
        # 缓存结果
        self.metrics = metrics
        return metrics


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
        """准备TVAM模型数据"""
        if data is not None:
            self.raw_data = data
        
        if self.raw_data is None:
            raise ValueError("请提供数据")
        
        # 获取基线考试ID
        baseline_exam = getattr(self.data_processor, 'baseline_exam', None)
        
        # 复制原始数据
        model_data = self.raw_data.copy()
        
        # 前测后测处理
        model_data = self._process_pre_post_tests(model_data, baseline_exam)
        
        # 显示处理前的数据信息
        logger.info(f"TVAM模型准备数据，接收的数据字段: {sorted(model_data.columns.tolist())}")
        logger.info(f"数据样本（前3行）:\n{model_data.head(3)}")
        
        # 创建数值索引和名称
        model_data = self._create_numeric_indices(model_data)
        model_data = self._ensure_names_and_ids(model_data)
        
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

class TimeSeriesBayesianValueAddedModel(BaseValueAddedModel):
    """
    基于连续多次考试的贝叶斯增值评价模型。
    
    使用多次考试作为基线，采用贝叶斯多层线性模型估计增值效应。
    支持两种指定基线的方式：
    1. 按数量模式：自动使用最近的N次考试作为基线
    2. 按考试ID模式：明确指定哪些考试作为基线
    
    Args:
        baseline_exams_count: 用作基线的考试次数(数量模式)
        decay_factor: 时间衰减因子(0-1之间)，控制较早考试的权重
        use_exam_ids: 是否使用考试ID模式
        baseline_exam_ids: 用作基线的考试ID列表(考试ID模式)
        target_exam_id: 目标考试ID(考试ID模式)
        
    Returns:
        贝叶斯估计的增值效应及其可信区间
        
    Raises:
        ValueError: 当数据不足或参数错误时
    """
    
    def __init__(self, baseline_exams_count=4, decay_factor=0.85, 
                 use_exam_ids=False, baseline_exam_ids=None, target_exam_id=None, **kwargs):
        super().__init__(**kwargs)
        self.baseline_exams_count = baseline_exams_count
        self.decay_factor = decay_factor
        self.use_exam_ids = use_exam_ids
        self.baseline_exam_ids = baseline_exam_ids
        self.target_exam_id = target_exam_id
        self.trace = None
        self.model = None
        self.processed_data = None
    
    # 实现BaseValueAddedModel要求的抽象方法
    def _validate_data(self, data):
        """
        验证输入数据
        
        Args:
            data: 输入数据
            
        Returns:
            bool: 数据是否有效
        """
        # 验证必要的列
        required_cols = ['student_id', 'class_id', 'school_id', 'exam_id', 'standard_score']
        for col in required_cols:
            if col not in data.columns:
                logger.error(f"数据中缺少必要的列: {col}")
                return False
                
        # 验证考试ID
        if self.use_exam_ids:
            # 确保所有指定的考试ID存在
            all_exam_ids = data['exam_id'].unique()
            missing_exams = []
            
            all_required_exams = self.baseline_exam_ids + [self.target_exam_id] if self.baseline_exam_ids else []
            for exam_id in all_required_exams:
                if exam_id and exam_id not in all_exam_ids:
                    missing_exams.append(exam_id)
            
            if missing_exams:
                logger.error(f"以下考试ID不存在于数据中: {', '.join(missing_exams)}")
                return False
                
        return True
    
    def _build_model(self, data):
        """
        构建贝叶斯多层次模型
        
        Args:
            data: 处理后的数据
            
        Returns:
            构建的模型
        """
        # 处理数据
        self.processed_data = self.prepare_data(data)
        
        # 使用现有的build_model方法
        self.model = self.build_model(self.processed_data)
        return self.model
    
    def _fit_model(self, data, **kwargs):
        """
        拟合模型
        
        Args:
            data: 输入数据
            **kwargs: 其他参数
            
        Returns:
            拟合结果
        """
        import pymc as pm
        import arviz as az
        
        # 如果模型未创建，先创建模型
        if self.model is None:
            self._build_model(data)
        
        # 设置MCMC采样参数
        sample_kwargs = {
            'draws': 2000,
            'tune': 1000,
            'chains': 4,
            'cores': 4,
            'return_inferencedata': True,
            'random_seed': 42
        }
        # 更新用户参数
        sample_kwargs.update(kwargs)
        
        # 执行采样
        with self.model:
            self.trace = pm.sample(**sample_kwargs)
        
        return self.trace
    
    def _calculate_value_added_impl(self, **kwargs):
        """
        计算增值效应
        
        Args:
            **kwargs: 其他参数
            
        Returns:
            增值效应结果
        """
        # 确保已经有拟合结果
        if self.trace is None or self.processed_data is None:
            raise ValueError("必须先拟合模型才能计算增值效应")
            
        # 使用现有的_calculate_value_added方法
        return self._calculate_value_added(self.trace, self.processed_data)
    
    def _predict_impl(self, data, **kwargs):
        """
        预测新数据的结果
        
        Args:
            data: 新数据
            **kwargs: 其他参数
            
        Returns:
            预测结果
        """
        import pymc as pm
        import arviz as az
        
        # 确保已经拟合过模型
        if self.trace is None or self.model is None:
            raise ValueError("必须先拟合模型才能进行预测")
            
        # 准备预测数据
        pred_data = self.prepare_data(data)
        
        # 提取后验分布的参数均值
        posterior_means = az.summary(self.trace).loc[:, 'mean']
        
        # 获取索引映射
        school_idx = pd.Categorical(pred_data['school_id']).codes
        class_idx = pd.Categorical(pred_data['class_id']).codes
        
        # 提取模型系数
        beta_0 = posterior_means['beta_0']
        beta_1 = posterior_means['beta_1']
        beta_trend = posterior_means['beta_trend']
        
        # 计算趋势特征
        trend_features = []
        for i in range(len(pred_data)):
            scores = pred_data['baseline_scores'].iloc[i]
            trend = (scores[-1] - scores[0]) / len(scores)
            trend_features.append(trend)
        
        trend_features = np.array(trend_features)
        
        # 获取学校和班级效应
        school_effects = np.array([posterior_means[f'school_effects[{i}]'] 
                                 for i in range(len(set(school_idx)))])
        class_effects = np.array([posterior_means[f'class_effects[{i}]'] 
                                for i in range(len(set(class_idx)))])
        
        # 计算预测值
        predictions = (beta_0 + 
                      beta_1 * pred_data['weighted_baseline'].values + 
                      beta_trend * trend_features +
                      school_effects[school_idx] + 
                      class_effects[class_idx])
        
        return predictions
    
    # 保留原有方法
    def prepare_data(self, data):
        """
        准备多时间点基线的增值分析数据。
        
        Args:
            data: 原始成绩数据DataFrame
            
        Returns:
            处理后的数据
        """
        if self.use_exam_ids:
            return self._prepare_data_by_exam_ids(data)
        else:
            return self._prepare_data_by_count(data)
    
    def _prepare_data_by_count(self, data):
        """按最近N次考试准备数据"""
        # 验证每个学生有足够的历史成绩
        student_counts = data.groupby('student_id').size()
        valid_students = student_counts[student_counts >= self.baseline_exams_count + 1].index
        
        if len(valid_students) == 0:
            raise ValueError(f"没有学生同时具有{self.baseline_exams_count}次基线考试和目标考试的成绩")
        
        filtered_data = data[data['student_id'].isin(valid_students)].copy()
        
        # 按学生和考试日期排序
        filtered_data.sort_values(['student_id', 'exam_date'], inplace=True)
        
        # 为每个学生构建基线数据
        baseline_data = []
        
        for student_id, student_data in filtered_data.groupby('student_id'):
            # 确保至少有基线次数+1条记录
            if len(student_data) < self.baseline_exams_count + 1:
                continue
                
            # 提取基线考试和目标考试
            baseline_scores = student_data.iloc[:self.baseline_exams_count]['standard_score'].values
            target_score = student_data.iloc[self.baseline_exams_count]['standard_score']
            
            # 记录学生信息
            student_info = {
                'student_id': student_id,
                'class_id': student_data['class_id'].iloc[0],
                'school_id': student_data['school_id'].iloc[0],
                'baseline_scores': baseline_scores,
                'weighted_baseline': self._calculate_weighted_baseline(baseline_scores),
                'target_score': target_score
            }
            
            baseline_data.append(student_info)
            
        processed_data = pd.DataFrame(baseline_data)
        return processed_data
    
    def _prepare_data_by_exam_ids(self, data):
        """按指定考试ID准备数据"""
        # 验证必要参数
        if not self.baseline_exam_ids or not self.target_exam_id:
            raise ValueError("使用考试ID模式时必须指定baseline_exam_ids和target_exam_id")
            
        # 确保目标考试不在基线考试中
        if self.target_exam_id in self.baseline_exam_ids:
            raise ValueError(f"目标考试({self.target_exam_id})不能在基线考试中")
            
        # 验证所有考试ID都存在于数据中
        all_exam_ids = data['exam_id'].unique()
        missing_exams = []
        
        for exam_id in self.baseline_exam_ids + [self.target_exam_id]:
            if exam_id not in all_exam_ids:
                missing_exams.append(exam_id)
        
        if missing_exams:
            raise ValueError(f"以下考试ID不存在于数据中: {', '.join(missing_exams)}")
            
        # 过滤出目标考试和基线考试的数据
        relevant_exams = self.baseline_exam_ids + [self.target_exam_id]
        filtered_data = data[data['exam_id'].isin(relevant_exams)].copy()
        
        # 查找同时参加了所有相关考试的学生
        student_exam_counts = filtered_data.groupby('student_id')['exam_id'].nunique()
        valid_students = student_exam_counts[student_exam_counts == len(relevant_exams)].index
        
        if len(valid_students) == 0:
            raise ValueError(f"没有学生同时参加了所有指定的考试")
            
        filtered_data = filtered_data[filtered_data['student_id'].isin(valid_students)]
        
        # 为每个学生构建基线数据
        baseline_data = []
        
        for student_id, student_data in filtered_data.groupby('student_id'):
            # 获取基线考试成绩
            baseline_scores = []
            for exam_id in self.baseline_exam_ids:
                score = student_data[student_data['exam_id'] == exam_id]['standard_score'].values[0]
                baseline_scores.append(score)
                
            # 获取目标考试成绩
            target_score = student_data[student_data['exam_id'] == self.target_exam_id]['standard_score'].values[0]
            
            # 记录学生信息
            student_info = {
                'student_id': student_id,
                'class_id': student_data['class_id'].iloc[0],
                'school_id': student_data['school_id'].iloc[0],
                'baseline_scores': np.array(baseline_scores),
                'weighted_baseline': self._calculate_weighted_baseline(np.array(baseline_scores)),
                'target_score': target_score
            }
            
            baseline_data.append(student_info)
            
        processed_data = pd.DataFrame(baseline_data)
        return processed_data
    
    def _calculate_weighted_baseline(self, scores):
        """
        计算基线分数的加权平均值，较近的考试权重更高。
        
        Args:
            scores: 基线考试分数列表
            
        Returns:
            加权平均分数
        """
        weights = np.array([self.decay_factor ** (len(scores) - i - 1) 
                           for i in range(len(scores))])
        weights = weights / weights.sum()  # 归一化权重
        
        return np.sum(scores * weights)
    
    def build_model(self, data):
        """
        构建基于多时间点基线的贝叶斯多层次模型。
        
        Args:
            data: 处理后的数据
            
        Returns:
            PyMC模型
        """
        import pymc as pm
        
        with pm.Model() as model:
            # 获取索引
            school_idx = pd.Categorical(data['school_id']).codes
            class_idx = pd.Categorical(data['class_id']).codes
            
            # 先验分布
            sigma_school = pm.HalfCauchy('sigma_school', beta=3)  
            sigma_class = pm.HalfCauchy('sigma_class', beta=3)    
            sigma = pm.HalfCauchy('sigma', beta=3)                
            
            # 随机效应
            school_effects = pm.Normal('school_effects', mu=0, sigma=sigma_school, 
                                      shape=len(set(school_idx)))
            class_effects = pm.Normal('class_effects', mu=0, sigma=sigma_class, 
                                     shape=len(set(class_idx)))
            
            # 固定效应 - 基线成绩系数
            beta_0 = pm.Normal('beta_0', mu=0, sigma=10)  # 截距
            beta_1 = pm.Normal('beta_1', mu=1, sigma=1)  # 基线成绩系数
            
            # 额外系数 - 基线趋势
            beta_trend = pm.Normal('beta_trend', mu=0, sigma=1)
            
            # 计算趋势特征 (最后一次减第一次)/总次数
            trend_feature = []
            for i in range(len(data)):
                scores = data['baseline_scores'].iloc[i]
                trend = (scores[-1] - scores[0]) / len(scores)
                trend_feature.append(trend)
            
            trend_feature = np.array(trend_feature)
            
            # 模型预测
            mu = (beta_0 + 
                  beta_1 * data['weighted_baseline'].values + 
                  beta_trend * trend_feature +
                  school_effects[school_idx] + 
                  class_effects[class_idx])
            
            # 似然函数
            y = pm.Normal('y', mu=mu, sigma=sigma, observed=data['target_score'].values)
        
        return model
    
    def fit(self, data, **kwargs):
        """
        拟合贝叶斯模型并计算增值效应。
        
        Args:
            data: 处理后的数据
            **kwargs: 传递给pm.sample的参数
            
        Returns:
            拟合结果
        """
        # 验证数据
        if not self._validate_data(data):
            raise ValueError("数据验证失败")
            
        # 拟合模型
        self.trace = self._fit_model(data, **kwargs)
        
        # 计算增值效应
        self.results = self._calculate_value_added_impl()
        return self.results
    
    def _calculate_value_added(self, trace, data):
        """
        计算增值效应及其不确定性。
        
        Args:
            trace: MCMC采样痕迹
            data: 处理后的数据
            
        Returns:
            增值效应结果字典
        """
        import arviz as az
        
        # 提取后验分布
        school_effects = az.extract(trace, var_names=["school_effects"])
        class_effects = az.extract(trace, var_names=["class_effects"])
        
        # 计算学校和班级的增值效应
        school_ids = data['school_id'].unique()
        school_indices = {school_id: i for i, school_id in 
                         enumerate(pd.Categorical(data['school_id']).categories)}
        
        class_ids = data['class_id'].unique()
        class_indices = {class_id: i for i, class_id in 
                        enumerate(pd.Categorical(data['class_id']).categories)}
        
        # 学校增值效应
        school_value_added = {}
        for school_id in school_ids:
            idx = school_indices[school_id]
            effect = school_effects[:, idx].mean()
            ci_lower = np.percentile(school_effects[:, idx], 2.5)
            ci_upper = np.percentile(school_effects[:, idx], 97.5)
            
            school_value_added[school_id] = {
                'effect': effect,
                'ci_lower': ci_lower,
                'ci_upper': ci_upper,
                'significant': (ci_lower > 0) or (ci_upper < 0)
            }
        
        # 班级增值效应
        class_value_added = {}
        for class_id in class_ids:
            idx = class_indices[class_id]
            effect = class_effects[:, idx].mean()
            ci_lower = np.percentile(class_effects[:, idx], 2.5)
            ci_upper = np.percentile(class_effects[:, idx], 97.5)
            
            class_value_added[class_id] = {
                'effect': effect,
                'ci_lower': ci_lower,
                'ci_upper': ci_upper,
                'significant': (ci_lower > 0) or (ci_upper < 0)
            }
        
        return {
            'school_effects': school_value_added,
            'class_effects': class_value_added,
            'trace': trace,
            'model_summary': az.summary(trace)
        }

class StudentProgressClusterAnalyzer(BaseValueAddedModel):
    """
    基于K-means聚类的学生进步模式分群分析模型
    
    通过分析学生在多次考试中的成绩变化模式，识别不同类型的学习轨迹。
    
    Args:
        data: 包含学生考试成绩的数据框
        data_processor: 数据处理器实例
        n_clusters: 聚类数量，默认为4
        min_exams: 模型所需的最少考试次数，默认为3
        random_state: 随机种子，用于K-means算法
        
    Returns:
        带有聚类标签和特征的分析结果
    
    Raises:
        ValueError: 当数据不满足基本要求时抛出
    """
    
    def __init__(self, data=None, data_processor=None, n_clusters=4, min_exams=3, random_state=42):
        """
        初始化学生进步模式聚类分析模型
        
        Args:
            data: 原始数据DataFrame
            data_processor: 数据处理器实例
            n_clusters: 聚类数量，默认为4
            min_exams: 模型所需的最少考试次数，默认为3
            random_state: 随机种子，用于K-means算法
        """
        # 明确指定不需要前后测分离
        super().__init__(data, data_processor)
        self.n_clusters = n_clusters
        self.min_exams = min_exams
        self.random_state = random_state
        self.cluster_model = None
        self.features_df = None
        self.cluster_profiles = None

    def _extract_clustering_features(self):
        """
        从学生考试序列中提取用于聚类的特征
        
        提取的特征包括：
        - 平均增长率：整体成绩变化的斜率
        - 波动性：成绩的标准差
        - 加速度：成绩变化速率的变化
        - 最大进步：单次最大提升幅度
        - 最大退步：单次最大下降幅度
        - 起点水平：第一次考试的成绩
        - 终点水平：最后一次考试的成绩
        - 相对排名变化：排名的改变幅度
        
        Returns:
            DataFrame: 包含学生ID和提取特征的数据框
        """
        # 初始化特征数据框
        feature_data = []
        
        # 按学生分组处理数据
        for student_id, group in self.data.groupby('student_id'):
            # 按考试顺序排序
            group = group.sort_values('exam_order')
            
            # 提取分数序列
            scores = group['standard_score'].values
            exams = np.arange(len(scores))
            
            # 计算特征
            # 1. 平均增长率（线性回归斜率）
            slope, intercept = np.polyfit(exams, scores, 1)
            
            # 2. 波动性（标准差）
            volatility = np.std(scores)
            
            # 3. 加速度（二次拟合的二阶系数）
            if len(scores) >= 3:
                quad_coef = np.polyfit(exams, scores, 2)[0]
            else:
                quad_coef = 0
                
            # 4. 最大进步和退步
            score_diffs = np.diff(scores)
            max_improvement = np.max(score_diffs) if len(score_diffs) > 0 else 0
            max_decline = np.min(score_diffs) if len(score_diffs) > 0 else 0
            
            # 5. 起点和终点水平
            start_level = scores[0]
            end_level = scores[-1]
            
            # 6. 总体提升幅度
            total_improvement = end_level - start_level
            
            # 7. 计算相对于同考试的排名变化
            if 'rank_in_exam' in group.columns:
                start_rank = group['rank_in_exam'].iloc[0]
                end_rank = group['rank_in_exam'].iloc[-1]
                rank_change = start_rank - end_rank  # 排名提升为正
            else:
                rank_change = 0
                
            # 收集学生信息
            student_info = self._extract_student_info(group)
            
            # 添加到特征列表
            feature_data.append({
                'student_id': student_id,
                'student_name': student_info['student_name'],
                'class_name': student_info['class_name'],
                'school_name': student_info['school_name'],
                'grade': student_info['grade'],
                'growth_rate': slope,
                'volatility': volatility,
                'acceleration': quad_coef,
                'max_improvement': max_improvement,
                'max_decline': max_decline,
                'start_level': start_level,
                'end_level': end_level,
                'total_improvement': total_improvement,
                'rank_change': rank_change
            })
        
        # 创建特征数据框
        features_df = pd.DataFrame(feature_data)
        
        # 标准化数值特征用于聚类
        numeric_features = ['growth_rate', 'volatility', 'acceleration', 
                            'max_improvement', 'max_decline', 'start_level', 
                            'end_level', 'total_improvement', 'rank_change']
        
        features_df_numeric = features_df[numeric_features].copy()
        
        # 使用StandardScaler进行特征标准化
        from sklearn.preprocessing import StandardScaler
        scaler = StandardScaler()
        features_df_scaled = scaler.fit_transform(features_df_numeric)
        
        # 将标准化后的特征添加回数据框
        features_df_scaled = pd.DataFrame(
            features_df_scaled, 
            columns=[f"{col}_scaled" for col in numeric_features],
            index=features_df.index
        )
        
        # 合并原始特征和标准化特征
        self.features_df = pd.concat([features_df, features_df_scaled], axis=1)
        
        return self.features_df

    def _interpret_clusters(self):
        """
        解释聚类结果，为每个聚类提供描述性标签和特征分析
        
        Returns:
            dict: 聚类解释结果
        """
        # 获取每个聚类的均值特征
        cluster_means = self.features_df.groupby('cluster').mean()
        
        # 定义聚类标签和解释
        cluster_labels = {}
        
        for cluster_id in range(self.n_clusters):
            # 获取该聚类的特征均值
            cluster_profile = cluster_means.loc[cluster_id]
            
            # 根据特征分析确定标签和描述
            if cluster_profile['growth_rate'] > 0.5:
                if cluster_profile['volatility'] < 0:
                    label = "稳定提升型"
                    description = "该类学生展现出稳定持续的进步，波动小，成长稳健"
                else:
                    label = "突破成长型"
                    description = "该类学生有显著的成绩提升，可能伴随一定波动"
            elif cluster_profile['growth_rate'] > 0:
                if cluster_profile['acceleration'] > 0:
                    label = "后劲发力型"
                    description = "该类学生前期进步较慢，后期展现加速上升趋势"
                else:
                    label = "平稳发展型"
                    description = "该类学生进步幅度适中，较为平稳"
            elif cluster_profile['max_improvement'] > 0.5:
                label = "波动起伏型"
                description = "该类学生成绩有明显波动，有显著进步也有退步"
            elif cluster_profile['start_level'] > 0.5:
                label = "高分稳定型"
                description = "该类学生起点较高，保持相对稳定的高水平表现"
            else:
                label = "待突破型"
                description = "该类学生尚未展现明显进步，需要额外关注和帮助"
            
            # 保存聚类标签和描述
            cluster_labels[cluster_id] = {
                'label': label,
                'description': description,
                'profile': cluster_profile.to_dict()
            }
        
        self.cluster_profiles = cluster_labels
        return cluster_labels

    def prepare_data(self, data=None):
        """
        准备聚类分析所需的数据
        
        Args:
            data: 输入数据，如果为None则使用初始化时的数据
            
        Returns:
            DataFrame: 准备好的建模数据
        
        Raises:
            ValueError: 当数据不满足基本要求时抛出
        """
        # 调用基类的prepare_data获取基础处理后的数据
        model_data = super().prepare_data(data)
        
        # 获取数据处理工具
        processors = self.data_processor.get_data_processors()
        
        # 确保考试数量足够
        exam_ids = model_data['exam_id'].unique()
        total_exams = len(exam_ids)
        
        if total_exams < self.min_exams:
            raise ValueError(f"聚类分析需要至少{self.min_exams}次考试，当前只有{total_exams}次")
        
        # 确保有标准化分数
        if 'standard_score' not in model_data.columns:
            if 'score' in model_data.columns:
                # 按考试ID分组标准化分数
                model_data['standard_score'] = model_data.groupby('exam_id')['score'].transform(
                    lambda x: (x - x.mean()) / x.std() if x.std() != 0 else 0
                )
                logger.info("已创建标准化分数字段")
            else:
                raise ValueError("数据中缺少'score'或'standard_score'字段")
        
        # 检查每个学生的考试次数
        student_exam_counts = model_data.groupby('student_id')['exam_id'].nunique()
        complete_students = student_exam_counts[student_exam_counts >= self.min_exams].index
        
        # 记录统计信息
        logger.info(f"参加至少{self.min_exams}次考试的学生: {len(complete_students)}人")
        
        # 筛选数据
        model_data = model_data[model_data['student_id'].isin(complete_students)]
        
        if len(model_data) == 0:
            raise ValueError(f"没有学生参加了至少{self.min_exams}次考试，无法进行聚类分析")
        
        # 确保考试时间序列的一致性
        if 'exam_date' in model_data.columns:
            # 按日期排序考试
            exam_dates = model_data.groupby('exam_id')['exam_date'].first().sort_values()
            exam_order = {exam: i for i, exam in enumerate(exam_dates.index)}
            model_data['exam_order'] = model_data['exam_id'].map(exam_order)
        else:
            # 如果没有日期，假设考试ID已经按时间顺序编号
            exam_ids = sorted(model_data['exam_id'].unique())
            exam_order = {exam: i for i, exam in enumerate(exam_ids)}
            model_data['exam_order'] = model_data['exam_id'].map(exam_order)
        
        # 按学生ID和考试顺序排序
        model_data = model_data.sort_values(['student_id', 'exam_order'])
        
        # 确保必要的名称字段
        model_data = processors['ensure_student_names'](model_data)
        model_data = processors['ensure_school_names'](model_data)
        model_data = processors['ensure_class_names'](model_data)
        model_data = processors['ensure_grade_field'](model_data)
        
        # 保存处理后的数据
        self.data = model_data
        
        return model_data

    def _build_model(self):
        """
        构建K-means聚类模型
        
        Returns:
            sklearn.cluster.KMeans: 构建的K-means模型
        """
        from sklearn.cluster import KMeans
        self.cluster_model = KMeans(
            n_clusters=self.n_clusters,
            random_state=self.random_state,
            n_init=10
        )
        return self.cluster_model
        
    def _validate_data(self, data):
        """
        验证数据是否满足聚类分析的要求
        
        Args:
            data: 待验证的数据
            
        Returns:
            bool: 数据是否有效
        """
        # 检查是否存在必要字段
        required_fields = ['student_id', 'exam_id']
        for field in required_fields:
            if field not in data.columns:
                logger.error(f"数据缺少必要字段: {field}")
                return False
                
        # 检查考试次数
        if data['exam_id'].nunique() < self.min_exams:
            logger.error(f"考试次数不足，需要至少{self.min_exams}次考试")
            return False
            
        return True
        
    def _fit_model(self, data=None, **kwargs):
        """
        拟合聚类模型
        
        Args:
            data: 输入数据，如果为None则使用类中已有的数据
            **kwargs: 额外参数
            
        Returns:
            dict: 拟合结果
        """
        if data is not None:
            self.data = data
            
        # 更新参数(如果提供)
        if 'clusters' in kwargs:
            self.n_clusters = kwargs['clusters']
        
        if 'min_exams' in kwargs:
            self.min_exams = kwargs['min_exams']
            
        # 提取特征
        features = self._extract_clustering_features()
        
        # 选择用于聚类的特征列
        clustering_features = [col for col in features.columns if col.endswith('_scaled')]
        
        # 构建并拟合模型
        model = self._build_model()
        features['cluster'] = model.fit_predict(features[clustering_features])
        
        # 保存结果
        self.features_df = features
        
        # 解释聚类
        self.cluster_profiles = self._interpret_clusters()
        
        # 返回聚类结果
        return {
            'features_df': features,
            'cluster_profiles': self.cluster_profiles,
            'cluster_model': model,
            'cluster_results': features[['student_id', 'student_name', 'class_name', 'school_name', 'grade', 'cluster']]
        }
        
    def _calculate_value_added_impl(self):
        """
        计算增值效应 - 对于聚类模型，返回聚类结果
        
        Returns:
            dict: 聚类结果
        """
        if self.features_df is None or self.cluster_profiles is None:
            raise ValueError("模型尚未拟合，请先调用fit方法")
            
        # 计算每个聚类的统计信息
        cluster_stats = {}
        for cluster_id in range(self.n_clusters):
            if cluster_id not in self.cluster_profiles:
                continue
                
            cluster_data = self.features_df[self.features_df['cluster'] == cluster_id]
            if len(cluster_data) == 0:
                continue
                
            profile = self.cluster_profiles[cluster_id]
            cluster_stats[cluster_id] = {
                'label': profile['label'],
                'description': profile['description'],
                'count': len(cluster_data),
                'percentage': len(cluster_data) / len(self.features_df) * 100
            }
            
        return {
            'cluster_assignments': self.features_df[['student_id', 'cluster']].copy(),
            'cluster_profiles': self.cluster_profiles,
            'cluster_stats': cluster_stats
        }
        
    def _predict_impl(self, data):
        """
        对新数据进行聚类预测
        
        Args:
            data: 新数据
            
        Returns:
            DataFrame: 预测结果
        """
        if self.cluster_model is None:
            raise ValueError("模型尚未拟合，请先调用fit方法")
            
        # 准备数据
        prepared_data = self.prepare_data(data)
        
        # 提取特征
        features = self._extract_clustering_features()
        
        # 选择用于聚类的特征列
        clustering_features = [col for col in features.columns if col.endswith('_scaled')]
        
        # 预测聚类
        features['cluster'] = self.cluster_model.predict(features[clustering_features])
        
        return features
        
    def _extract_student_info(self, group):
        """
        从学生数据中提取基本信息
        
        Args:
            group: 包含单个学生数据的DataFrame
            
        Returns:
            dict: 学生基本信息
        """
        info = {
            'student_name': 'Unknown',
            'class_name': 'Unknown',
            'school_name': 'Unknown',
            'grade': 'Unknown'
        }
        
        if 'student_name' in group.columns:
            info['student_name'] = group['student_name'].iloc[0]
        
        if 'class_name' in group.columns:
            info['class_name'] = group['class_name'].iloc[0]
        
        if 'school_name' in group.columns:
            info['school_name'] = group['school_name'].iloc[0]
        
        if 'grade' in group.columns:
            info['grade'] = group['grade'].iloc[0]
        
        return info

    def prepare_data(self, data=None):
        """准备聚类分析数据"""
        if data is not None:
            self.raw_data = data
        
        if self.raw_data is None:
            raise ValueError("请提供数据")
        
        # 复制原始数据
        model_data = self.raw_data.copy()
        
        # 创建数值索引和名称
        model_data = self._create_numeric_indices(model_data)
        model_data = self._ensure_names_and_ids(model_data)
        
        # 聚类特有处理：确保考试顺序和标准化分数
        model_data = self._preprocess_time_series_data(model_data)
        
        # 保存处理后的数据
        self.data = model_data
        return model_data



