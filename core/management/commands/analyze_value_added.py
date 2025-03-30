"""
班级增值效应分析命令

使用贝叶斯多层次模型分析学生成绩数据，计算班级增值效应和学生学习潜力。
该命令调用EducationDataProvider获取处理后的数据，并应用PyMC3建模。

示例用法:
python manage.py analyze_value_added --exams EXAM2023-1 EXAM2023-2 EXAM2023-3 EXAM2023-4 EXAM2023-5 --subject MATH --output results/

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
import pymc as pm
import arviz as az
import matplotlib.pyplot as plt
from django.core.management.base import BaseCommand
from django.conf import settings

from core.management.commands.education_data_provider import EducationDataProvider
from models.bayesian_hierarchical import build_education_model
from analysis.value_added import calculate_value_added
from viz.model_diagnostics import plot_potential_analysis


class Command(BaseCommand):
    """
    班级增值效应分析命令
    
    分析前测和后测成绩差异，评估班级教学效果。
    """
    
    help = '使用贝叶斯多层次模型分析班级增值效应和学生学习潜力'
    
    def add_arguments(self, parser):
        """
        添加命令行参数
        
        Args:
            parser: 命令行参数解析器
        """
        parser.add_argument('--exams', nargs='+', required=True, help='考试ID列表')
        parser.add_argument('--subject', required=True, help='学科ID')
        parser.add_argument('--output', default='results/', help='结果输出目录')
        parser.add_argument('--chains', type=int, default=4, help='MCMC链数量')
        parser.add_argument('--iter', type=int, default=2000, help='MCMC迭代次数')
        parser.add_argument('--plot', action='store_true', help='是否生成图表')
    
    def handle(self, *args, **options):
        """
        命令主函数
        
        Args:
            options: 命令行参数字典
        """
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
        """
        加载教育数据
        
        Args:
            exam_ids: 考试ID列表
            subject_id: 学科ID
            
        Returns:
            DataFrame 处理后的教育数据
        """
        provider = EducationDataProvider(
            exam_ids=exam_ids,
            subject_id=subject_id
        )
        data = provider.get_data()
        return data
    
    def _prepare_model_data(self, data):
        """
        准备建模数据
        
        Args:
            data: 原始教育数据
            
        Returns:
            DataFrame 准备好的建模数据
        """
        # 检查数据完整性
        if 'is_posttest' not in data.columns:
            raise ValueError("数据缺少后测标识")
            
        # 验证每个学生有且仅有一个后测
        posttest_counts = data.groupby('student_id')['is_posttest'].sum()
        if not all(posttest_counts == 1):
            problem_students = posttest_counts[posttest_counts != 1].index.tolist()
            raise ValueError(f"有{len(problem_students)}名学生后测数据异常")
            
        # 验证班级信息
        if 'norm_class_group' not in data.columns:
            raise ValueError("数据缺少规范化班级信息")
            
        # 预处理：分离前测和后测
        pretest_data = data[~data['is_posttest']].copy()
        posttest_data = data[data['is_posttest']].copy()
        
        # 确保前测和后测都有足够数据
        if len(pretest_data) < len(posttest_data) * 0.8:
            raise ValueError(f"前测数据不足: 前测{len(pretest_data)}条，后测{len(posttest_data)}条")
            
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
        
        # 检查完整性
        if model_data['pretest_score'].isna().any():
            raise ValueError("存在缺失的前测分数")
            
        return model_data
    
    def _build_and_sample_model(self, model_data, n_chains=4, n_iter=2000):
        """
        构建并采样贝叶斯多层次模型
        
        Args:
            model_data: 准备好的建模数据
            n_chains: MCMC链数量
            n_iter: MCMC迭代次数
            
        Returns:
            tuple(model, trace): PyMC3模型和采样结果
        """
        # 提取班级数据
        class_data = model_data[['norm_class_group', 'class_code']].drop_duplicates()
        
        # 构建模型
        model = build_education_model(model_data, class_data)
        
        # 采样
        with model:
            # 采样调整参数
            tune = int(n_iter * 0.25)  # 调适期为总迭代次数的25%
            
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
        """
        保存分析结果
        
        Args:
            value_added_results: 增值效应计算结果
            model_data: 建模数据
            output_dir: 输出目录
        """
        # 保存班级增值效应结果
        value_added_df = pd.DataFrame(value_added_results['total_value_added'])
        value_added_df['class_id'] = model_data['norm_class_group'].unique()
        
        # 添加班级和学校信息
        class_info = model_data[['norm_class_group', 'school_id']].drop_duplicates()
        value_added_df = pd.merge(
            value_added_df,
            class_info,
            left_on='class_id',
            right_on='norm_class_group',
            how='left'
        )
        
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
        """
        生成分析图表
        
        Args:
            trace: 模型采样结果
            model_data: 建模数据
            output_dir: 输出目录
        """
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
        
        # 图4: Pair plot
        az.plot_pair(
            trace, 
            var_names=['mu_alpha', 'mu_beta', 'sigma_alpha', 'sigma_beta'],
            kind='kde'
        )
        plt.savefig(os.path.join(output_dir, 'parameter_pairs.png'), dpi=300) 