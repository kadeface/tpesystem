"""
班级增值效应分析命令

使用贝叶斯多层次模型分析学生成绩数据，计算班级增值效应和学生学习潜力。
该命令整合了数据提供、贝叶斯建模、增值分析和可视化输出功能。

示例用法:
python manage.py value_added_analysis --exams EXAM2023-1 EXAM2023-2 EXAM2023-3 EXAM2023-4 EXAM2023-5 --subject MATH --output results/

支持参数:
--exams: 考试ID列表，至少需要两次考试（前测和后测）
--subject: 学科ID
--output: 结果输出目录
--chains: MCMC链数量，默认4
--iter: MCMC迭代次数，默认2000
--plot: 是否生成图表，默认False
"""

import os
import pandas as pd
import numpy as np
import pymc3 as pm
import arviz as az
import matplotlib.pyplot as plt
import logging
from django.core.management.base import BaseCommand
from django.conf import settings
from core.models import (
    Score, 
    Exam, 
    Student, 
    Subject,
    StudentHistory, 
    School
)

# 配置日志
logger = logging.getLogger(__name__)

#############################################
# 第一部分: 教育数据提供器
#############################################

class EducationDataProvider:
    """
    教育数据提供器
    
    提供统一接口获取并处理教育数据，为贝叶斯模型提供标准化数据源
    """
    
    def __init__(self, exam_ids=None, subject_id=None, semester_range=3, student_ids=None):
        """
        初始化数据提供器
        
        Args:
            exam_ids: list 考试ID列表
            subject_id: str 学科ID
            semester_range: int 学期范围
            student_ids: list 学生ID列表
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
    
    def get_data(self, normalize_classes=True, clean_data=True, include_history=True):
        """获取并处理教育数据"""
        # 步骤1: 获取考试信息
        exams = self._get_exams()
        if not exams:
            raise ValueError("未找到符合条件的考试")
        
        logger.info(f"找到{len(exams)}个考试: {[e.exam_id for e in exams]}")
        
        # 步骤2: 获取成绩数据
        scores_df = self._get_scores(exams)
        if scores_df.empty:
            raise ValueError("未找到符合条件的成绩记录")
        
        logger.info(f"初始数据: {len(scores_df)}条成绩记录，涉及{scores_df['student_id'].nunique()}名学生")
        
        # 步骤3: 如果需要，获取学生历史记录
        if include_history:
            data_df = self._get_student_history(scores_df)
            logger.info(f"添加历史数据后: {len(data_df)}条记录")
        else:
            data_df = scores_df.copy()
        
        # 步骤4: 如果需要，规范化班级信息
        if normalize_classes and 'class_id' in data_df.columns:
            data_df = self._normalize_class_groups(data_df)
            logger.info(f"规范化后班级数量: {data_df['norm_class_group'].nunique()}")
        
        # 步骤5: 如果需要，清洗数据
        if clean_data:
            data_df = self._clean_data(data_df)
            logger.info(f"清洗后数据: {len(data_df)}条记录")
        
        # 缓存处理后的数据
        self._processed_df = data_df
        
        return data_df
    
    def _get_exams(self):
        """获取目标考试信息"""
        if self._exams is not None:
            return self._exams
            
        # 如果直接指定了考试ID列表
        if self.exam_ids:
            # 获取匹配的考试
            exam_query = Exam.objects.filter(status='COMPLETE')
            exact_match = exam_query.filter(exam_id__in=self.exam_ids)
            if exact_match.exists():
                self._exams = list(exact_match.select_related('semester'))
                return self._exams
        
        # 如果没有指定考试ID，则获取最近的考试
        latest_exams = list(Exam.objects.filter(
            status='COMPLETE'
        ).order_by('-start_time')[:self.semester_range])
        
        if not latest_exams:
            raise ValueError("未找到活动考试")
            
        self._exams = latest_exams
        return self._exams
    
    def _get_scores(self, exams):
        """获取成绩数据（设定后测）"""
        exam_ids = [exam.exam_id for exam in exams]
        
        # 构建查询
        query = Score.objects.filter(
            exam_id__in=exam_ids
        ).select_related('exam', 'subject', 'student')
        
        # 如果指定了学科，添加过滤
        if self.subject_id:
            query = query.filter(subject_id=self.subject_id)
            
        # 如果指定了学生，添加过滤
        if self.student_ids:
            query = query.filter(student_id__in=self.student_ids)
            
        # 为每个学生按考试时间排序
        scores_by_student = {}
        for score in query:
            student_id = score.student_id
            if student_id not in scores_by_student:
                scores_by_student[student_id] = []
            scores_by_student[student_id].append(score)
            
        # 确保每个学生的最后一次考试为后测
        scores = []
        for student_id, student_scores in scores_by_student.items():
            # 按考试时间排序
            sorted_scores = sorted(student_scores, key=lambda s: s.exam.start_time)
            
            for i, score in enumerate(sorted_scores):
                # 标记后测（最后一次考试）
                is_posttest = (i == len(sorted_scores) - 1)
                
                # 验证T分数有效性
                if score.standard_score < 200 or score.standard_score > 900:
                    continue
                    
                # 记录学生信息
                self.mappings['students'][score.student_id] = score.student.name
                    
                # 添加记录
                scores.append({
                    'student_id': score.student_id,
                    'exam_id': score.exam_id,
                    'is_posttest': is_posttest,  # 后测标识
                    'subject_id': score.subject_id,
                    'semester_id': score.exam.semester_id,
                    'standard_score': score.standard_score,
                    'raw_score': score.score,
                    'exam_date': score.exam.start_time,
                    'max_score': score.exam.total_score
                })
            
        return pd.DataFrame(scores)
    
    def _get_student_history(self, scores_df):
        """获取学生历史记录并关联班级和学校信息"""
        # 获取需要查询的学生ID列表
        student_ids = scores_df['student_id'].unique().tolist()
        
        # 使用select_related获取历史记录
        student_records = StudentHistory.objects.filter(
            student_id__in=student_ids,
            status='ACTIVE'
        ).select_related('school', 'class_field').values(
            'student_id', 'semester_id', 'class_field_id', 
            'grade_id', 'school_id', 'school__school_name'
        )
        
        # 转换为DataFrame
        records_df = pd.DataFrame(list(student_records))
        if records_df.empty:
            logger.warning(f"未找到任何学生历史记录")
            return scores_df
            
        # 重命名列
        records_df = records_df.rename(columns={
            'class_field_id': 'class_id',
            'school__school_name': 'school_name',
            'grade_id': 'grade_level'
        })
        
        # 与成绩数据合并
        merged_df = pd.merge(
            scores_df, 
            records_df,
            on=['student_id', 'semester_id'],
            how='left'
        )
        
        return merged_df
    
    def _normalize_class_groups(self, data):
        """规范化班级群组ID，处理跨学期班级变化"""
        # 使用最后一次考试的班级作为规范化班级ID
        data = data.sort_values(['student_id', 'semester_id'])
        
        # 获取每个学生最后一次考试记录
        latest_exams = data.groupby('student_id').tail(1)
        
        # 提取学生最后一次考试的班级ID
        student_latest_class = dict(zip(latest_exams['student_id'], latest_exams['class_id']))
        
        # 为每个学生的所有记录分配最后一次考试的班级ID
        data['norm_class_group'] = data['student_id'].map(student_latest_class)
        
        return data
    
    def _clean_data(self, df):
        """数据清洗和验证"""
        logger.info(f"清洗前数据条数: {len(df)}")
        
        # 检查后测标识字段
        if 'is_posttest' not in df.columns:
            raise ValueError("数据缺少后测标识字段")
        
        posttest_counts = df.groupby('student_id')['is_posttest'].sum()
        invalid_students = posttest_counts[posttest_counts != 1].index.tolist()
        if invalid_students:
            logger.error(f"{len(invalid_students)}名学生后测记录异常")
            df = df[~df['student_id'].isin(invalid_students)]
        
        # 移除缺失关键字段的记录
        if 'standard_score' in df.columns:
            clean_df = df.dropna(subset=['standard_score'])
        else:
            clean_df = df
        
        # 移除标准分异常的记录
        if 'standard_score' in clean_df.columns:
            clean_df = clean_df[(clean_df['standard_score'] >= 200) & (clean_df['standard_score'] <= 900)]
        
        # 处理班级信息
        if 'norm_class_group' in clean_df.columns:
            clean_df = clean_df.dropna(subset=['norm_class_group'])
        elif 'class_id' in clean_df.columns:
            clean_df = clean_df.dropna(subset=['class_id'])
        
        # 确保数据集不为空
        if len(clean_df) == 0:
            raise ValueError("清洗后无有效数据剩余，请检查数据质量")
        
        return clean_df
    
    def prepare_for_modeling(self, add_indices=True, add_time_points=True):
        """为建模准备数据"""
        if self._processed_df is None:
            self.get_data()
            
        df = self._processed_df.copy()
        
        # 添加数值编码
        if add_indices:
            if 'student_id' in df.columns:
                df['student_code'] = df['student_id'].astype('category').cat.codes
                
            if 'school_id' in df.columns:
                df['school_code'] = df['school_id'].astype('category').cat.codes
                
            if 'norm_class_group' in df.columns:
                df['class_code'] = df['norm_class_group'].astype('category').cat.codes
            elif 'class_id' in df.columns:
                df['class_code'] = df['class_id'].astype('category').cat.codes
        
        # 添加时间点和前测特征
        if add_time_points:
            # 标记后测
            df['is_posttest'] = df.groupby('student_id')['exam_id'].transform(
                lambda x: x == x.iloc[-1]
            )
            # 前测特征
            df['pretest_features'] = df.groupby('student_id')['standard_score'].shift(1)
        
        return df


#############################################
# 第二部分: 贝叶斯多层次模型
#############################################

def build_education_model(student_data, class_data):
    """
    构建贝叶斯多层次线性模型
    
    Args:
        student_data: 学生层面数据
        class_data: 班级层面数据
    
    Returns:
        pm.Model: 构建完成的概率模型
    """
    with pm.Model() as edu_model:
        # 班级层面的随机截距
        mu_alpha = pm.Normal('mu_alpha', mu=0, sigma=10)
        sigma_alpha = pm.HalfNormal('sigma_alpha', sigma=5)
        class_intercept = pm.Normal('class_intercept', mu=mu_alpha, 
                                  sigma=sigma_alpha, 
                                  shape=len(class_data))
        
        # 学习潜力的随机斜率
        mu_beta = pm.Normal('mu_beta', mu=0, sigma=5)
        sigma_beta = pm.HalfNormal('sigma_beta', sigma=3)
        beta_potential = pm.Normal('beta_potential', mu=mu_beta,
                                 sigma=sigma_beta,
                                 shape=len(class_data))
        
        # 前测和参与度数据
        X_pretest = student_data['pretest_z'].values  # 使用Z分数
        X_engagement = student_data['posttest_z'].values  # 简化：使用参与度
        
        # 班级编码
        class_idx = student_data['class_code'].values
        
        # 线性组合
        mu = (class_intercept[class_idx] + 
             beta_potential[class_idx] * X_pretest)
        
        # 似然函数
        sigma_y = pm.HalfNormal('sigma_y', sigma=5)
        y = pm.Normal('y', mu=mu, sigma=sigma_y, observed=X_engagement)
    
    return edu_model


#############################################
# 第三部分: 增值效应计算
#############################################

def calculate_value_added(trace, class_ids):
    """
    计算班级增值效应
    
    Args:
        trace: 模型追踪结果
        class_ids: 需要评估的班级ID列表
    
    Returns:
        dict: 各班级增值效应后验统计量
    """
    return {
        'intercept_effect': az.summary(trace.posterior.class_intercept),
        'potential_coef': az.summary(trace.posterior.beta_potential),
        'total_value_added': az.summary(
            trace.posterior.class_intercept + 0.5*trace.posterior.beta_potential
        )
    }


#############################################
# 第四部分: 可视化函数
#############################################

def plot_potential_analysis(trace):
    """
    绘制学习潜力后验分布可视化
    
    Args:
        trace: 模型追踪结果
    
    Returns:
        matplotlib Figure: 包含随机斜率分布的森林图
    """
    return az.plot_forest(
        trace, 
        var_names=['beta_potential'],
        combined=True,
        hdi_prob=0.95
    )


#############################################
# 第五部分: 主命令类
#############################################

class Command(BaseCommand):
    """
    班级增值效应分析命令
    
    使用贝叶斯多层次模型分析学生成绩数据，评估班级增值效应
    """
    
    help = '使用贝叶斯多层次模型分析班级增值效应和学生学习潜力'
    
    def add_arguments(self, parser):
        """添加命令行参数"""
        parser.add_argument('--exams', nargs='+', required=True, help='考试ID列表')
        parser.add_argument('--subject', required=True, help='学科ID')
        parser.add_argument('--output', default='results/', help='结果输出目录')
        parser.add_argument('--chains', type=int, default=4, help='MCMC链数量')
        parser.add_argument('--iter', type=int, default=2000, help='MCMC迭代次数')
        parser.add_argument('--plot', action='store_true', help='是否生成图表')
    
    def handle(self, *args, **options):
        """命令主函数"""
        self.stdout.write(self.style.NOTICE('开始分析班级增值效应...'))
        
        # 参数解析
        exam_ids = options['exams']
        subject_id = options['subject']
        output_dir = options['output']
        n_chains = options['chains']
        n_iter = options['iter']
        make_plots = options['plot']
        
        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)
        
        # 步骤1: 加载和准备数据
        self.stdout.write('1. 正在加载教育数据...')
        try:
            data = self._load_educational_data(exam_ids, subject_id)
            self.stdout.write(self.style.SUCCESS(f'✓ 加载了{len(data)}条记录，涉及{data["student_id"].nunique()}名学生，{data["norm_class_group"].nunique()}个班级'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ 数据加载失败: {str(e)}'))
            return
        
        # 步骤2: 数据验证和准备
        self.stdout.write('2. 正在验证数据完整性...')
        try:
            model_data = self._prepare_model_data(data)
            self.stdout.write(self.style.SUCCESS(f'✓ 数据验证完成，模型输入包含{len(model_data)}条有效记录'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ 数据准备失败: {str(e)}'))
            return
            
        # 步骤3: 建立贝叶斯模型
        self.stdout.write('3. 正在构建贝叶斯多层次模型...')
        try:
            model, trace = self._build_and_sample_model(model_data, n_chains, n_iter)
            self.stdout.write(self.style.SUCCESS(f'✓ 模型拟合完成，采样{n_chains}链，每链{n_iter}次迭代'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ 模型构建失败: {str(e)}'))
            return
            
        # 步骤4: 计算增值效应
        self.stdout.write('4. 正在计算班级增值效应...')
        try:
            class_ids = model_data['norm_class_group'].unique().tolist()
            value_added_results = calculate_value_added(trace, class_ids)
            self.stdout.write(self.style.SUCCESS(f'✓ 增值效应计算完成'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ 增值效应计算失败: {str(e)}'))
            return
            
        # 步骤5: 保存结果
        self.stdout.write('5. 正在保存分析结果...')
        try:
            self._save_results(value_added_results, model_data, output_dir)
            self.stdout.write(self.style.SUCCESS(f'✓ 结果保存至 {output_dir}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ 结果保存失败: {str(e)}'))
            return
            
        # 步骤6: 生成图表（可选）
        if make_plots:
            self.stdout.write('6. 正在生成分析图表...')
            try:
                self._generate_plots(trace, model_data, output_dir)
                self.stdout.write(self.style.SUCCESS(f'✓ 图表生成完成'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'✗ 图表生成失败: {str(e)}'))
                
        self.stdout.write(self.style.SUCCESS('分析完成!'))
    
    def _load_educational_data(self, exam_ids, subject_id):
        """加载教育数据"""
        provider = EducationDataProvider(
            exam_ids=exam_ids,
            subject_id=subject_id
        )
        data = provider.get_data()
        return data
    
    def _prepare_model_data(self, data):
        """准备建模数据"""
        # 检查数据完整性
        if 'is_posttest' not in data.columns:
            raise ValueError("数据缺少后测标识")
            
        # 预处理：分离前测和后测
        pretest_data = data[~data['is_posttest']].copy()
        posttest_data = data[data['is_posttest']].copy()
        
        # 计算学生前测平均分作为预测变量
        pretest_avg = pretest_data.groupby('student_id')['standard_score'].mean().reset_index()
        pretest_avg.rename(columns={'standard_score': 'pretest_score'}, inplace=True)
        
        # 合并前测和后测数据
        model_data = pd.merge(
            posttest_data,
            pretest_avg,
            on='student_id',
            how='left'
        )
        
        # 标准化分数
        model_data['pretest_z'] = (model_data['pretest_score'] - model_data['pretest_score'].mean()) / model_data['pretest_score'].std()
        model_data['posttest_z'] = (model_data['standard_score'] - model_data['standard_score'].mean()) / model_data['standard_score'].std()
        
        # 添加数值编码
        model_data['student_code'] = model_data['student_id'].astype('category').cat.codes
        model_data['class_code'] = model_data['norm_class_group'].astype('category').cat.codes
        
        return model_data
    
    def _build_and_sample_model(self, model_data, n_chains=4, n_iter=2000):
        """构建并采样贝叶斯多层次模型"""
        # 提取班级数据
        class_data = model_data[['norm_class_group', 'class_code']].drop_duplicates()
        
        # 构建模型
        model = build_education_model(model_data, class_data)
        
        # 采样
        with model:
            # 调适期为总迭代次数的25%
            tune = int(n_iter * 0.25)
            
            # 执行采样
            trace = pm.sample(
                draws=n_iter,
                tune=tune,
                chains=n_chains,
                return_inferencedata=True,
                target_accept=0.9
            )
            
        # 收敛性检查
        if np.any(az.rhat(trace) > 1.05):
            self.stdout.write(self.style.WARNING('⚠ 收敛性检查：部分参数Rhat > 1.05，可能需要增加迭代次数'))
            
        return model, trace
    
    def _save_results(self, value_added_results, model_data, output_dir):
        """保存分析结果"""
        # 保存班级增值效应结果
        value_added_df = pd.DataFrame(value_added_results['total_value_added'])
        value_added_df['class_id'] = model_data['norm_class_group'].unique()
        
        # 按增值效应排序
        value_added_df = value_added_df.sort_values('mean', ascending=False)
        
        # 保存到CSV
        value_added_path = os.path.join(output_dir, 'class_value_added.csv')
        value_added_df.to_csv(value_added_path, index=False)
        
        # 保存学生学习潜力转化系数
        potential_df = pd.DataFrame(value_added_results['potential_coef'])
        potential_df['class_id'] = model_data['norm_class_group'].unique()
        potential_path = os.path.join(output_dir, 'learning_potential.csv')
        potential_df.to_csv(potential_path, index=False)
        
        # 保存基础效能系数
        intercept_df = pd.DataFrame(value_added_results['intercept_effect'])
        intercept_df['class_id'] = model_data['norm_class_group'].unique()
        intercept_path = os.path.join(output_dir, 'class_intercept.csv')
        intercept_df.to_csv(intercept_path, index=False)
        
        # 保存汇总报告
        summary = {
            '分析参数': {
                '班级数量': model_data['norm_class_group'].nunique(),
                '学生数量': model_data['student_id'].nunique(),
                '前测均分': model_data['pretest_score'].mean(),
                '后测均分': model_data['standard_score'].mean(),
                '分析日期': pd.Timestamp.now().strftime('%Y-%m-%d')
            },
            '班级增值效应排名': value_added_df[['class_id', 'mean']].head(10).values.tolist(),
            '学习潜力系数排名': potential_df[['class_id', 'mean']].sort_values('mean', ascending=False).head(10).values.tolist()
        }
        
        # 保存汇总为JSON
        import json
        with open(os.path.join(output_dir, 'summary_report.json'), 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
    
    def _generate_plots(self, trace, model_data, output_dir):
        """生成分析图表"""
        # 图1: 潜力系数森林图
        forest_fig = plot_potential_analysis(trace)
        forest_fig.savefig(os.path.join(output_dir, 'potential_forest_plot.png'), dpi=300)
        
        # 图2: 后验分布
        az.plot_posterior(trace, var_names=['mu_alpha', 'mu_beta', 'sigma_alpha', 'sigma_beta'])
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, 'posterior_distributions.png'), dpi=300)
        
        # 图3: 班级增值效应与班级规模的关系
        class_sizes = model_data.groupby('norm_class_group')['student_id'].nunique()
        va_results = pd.read_csv(os.path.join(output_dir, 'class_value_added.csv'))
        
        plt.figure(figsize=(10, 6))
        plt.scatter(class_sizes.values, va_results['mean'].values)
        plt.xlabel('班级规模')
        plt.ylabel('增值效应')
        plt.title('班级规模与增值效应关系')
        plt.grid(True, linestyle='--', alpha=0.7)
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, 'size_vs_value_added.png'), dpi=300)
        
        # 图4: 参数对图
        az.plot_pair(
            trace, 
            var_names=['mu_alpha', 'mu_beta', 'sigma_alpha', 'sigma_beta'],
            kind='kde'
        )
        plt.savefig(os.path.join(output_dir, 'parameter_pairs.png'), dpi=300) 