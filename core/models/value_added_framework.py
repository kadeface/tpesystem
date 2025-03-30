"""
教育增值分析框架

提供统一的组件式架构，支持不同的增值分析模型和方法：
1. 贝叶斯多层次模型
2. 频率统计HLM模型  
3. CDF概率分布分析
4. 纵向增长曲线分析

架构特点：
- 组件可组合、可扩展
- 处理与建模分离
- 统一的数据接口
- 可插拔的模型实现
"""

import numpy as np
import pandas as pd
import logging
from abc import ABC, abstractmethod
import matplotlib.pyplot as plt
import os
from pathlib import Path
import json
from django.conf import settings

# 根据实际需求导入建模库
import pymc as pm
import arviz as az
import statsmodels.api as sm
import statsmodels.formula.api as smf

# 配置日志
logger = logging.getLogger(__name__)


#############################################
# 第一部分: 基础数据处理器
#############################################

class ValueAddedDataProcessor:
    """
    增值分析数据处理器
    
    提供数据获取、清洗、转换和准备的通用功能
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
            'classes': {}
        }
        self.data = None
        self.model_data = None
    
    def load_data(self, **kwargs):
        """
        加载原始数据
        
        Args:
            **kwargs: 传递给数据提供器的参数
            
        Returns:
            DataFrame: 加载的原始数据
        """
        if self.provider is None:
            # 导入默认数据提供器
            from core.management.commands.education_data_provider import EducationDataProvider
            self.provider = EducationDataProvider(**kwargs)
        
        self.data = self.provider.get_data()
        logger.info(f"加载了{len(self.data)}条原始数据记录")
        return self.data
    
    def prepare_model_data(self, data=None):
        """
        准备建模数据
        
        处理包括:
        - 计算前测成绩
        - 创建分类索引
        - 标准化分数
        - 验证数据完整性
        
        Args:
            data: 输入数据，如果为None则使用之前加载的数据
            
        Returns:
            DataFrame: 准备好的建模数据
        """
        if data is None:
            if self.data is None:
                raise ValueError("请先加载数据或提供数据")
            data = self.data
            
        # 前测后测处理
        model_data = self._process_pre_post_tests(data)
        
        # 创建数值索引
        model_data = self._create_numeric_indices(model_data)
        
        # 标准化分数
        model_data = self._standardize_scores(model_data)
        
        # 验证数据完整性
        self._validate_data(model_data)
        
        self.model_data = model_data
        logger.info(f"准备了{len(model_data)}条建模数据")
        return model_data
    
    def _process_pre_post_tests(self, data):
        """
        处理前测和后测数据
        
        包括:
        - 按时间排序
        - 创建时间点
        - 计算前测成绩
        
        Args:
            data: 输入数据
            
        Returns:
            DataFrame: 添加了前测信息的数据
        """
        # 确保数据包含必要字段
        required_fields = ['student_id', 'standard_score']
        missing_fields = [f for f in required_fields if f not in data.columns]
        if missing_fields:
            raise ValueError(f"数据缺少必要字段: {missing_fields}")
        
        # 按学生ID和时间排序
        if 'exam_date' in data.columns:
            prep_data = data.sort_values(['student_id', 'exam_date'])
        elif 'semester_id' in data.columns:
            prep_data = data.sort_values(['student_id', 'semester_id'])
        else:
            raise ValueError("数据缺少时间排序字段")
        
        # 为每个学生创建时间点索引
        prep_data['time_point'] = prep_data.groupby('student_id').cumcount()
        
        # 获取前测成绩(第一次考试)
        prior_scores = prep_data[prep_data['time_point'] == 0].copy()
        prior_scores = prior_scores[['student_id', 'standard_score']]
        prior_scores.rename(columns={'standard_score': 'prior_score'}, inplace=True)
        
        # 合并前测成绩到所有记录
        prep_data = pd.merge(prep_data, prior_scores, on='student_id', how='left')
        
        return prep_data
    
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
            self.mappings['school_indices'] = dict(zip(
                indexed_data['school_id'].unique(), 
                indexed_data['school_idx'].unique()
            ))
        
        # 创建班级索引
        class_col = 'norm_class_group' if 'norm_class_group' in indexed_data.columns else 'class_id'
        if class_col in indexed_data.columns:
            indexed_data['class_idx'] = indexed_data[class_col].astype('category').cat.codes
            self.mappings['class_indices'] = dict(zip(
                indexed_data[class_col].unique(), 
                indexed_data['class_idx'].unique()
            ))
        
        # 创建学生索引
        indexed_data['student_idx'] = indexed_data['student_id'].astype('category').cat.codes
        self.mappings['student_indices'] = dict(zip(
            indexed_data['student_id'].unique(), 
            indexed_data['student_idx'].unique()
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
    
    def _validate_data(self, data):
        """
        验证数据完整性
        
        Args:
            data: 需要验证的数据
            
        Raises:
            ValueError: 如果数据不满足建模要求
        """
        # 检查样本量
        if len(data) < 100:
            logger.warning(f"数据样本量较小: {len(data)}条记录")
        
        # 检查学校数量
        if 'school_idx' in data.columns and data['school_idx'].nunique() < 3:
            logger.warning(f"学校数量较少，可能影响学校层面分析: {data['school_idx'].nunique()}所学校")
        
        # 检查班级数量
        if 'class_idx' in data.columns and data['class_idx'].nunique() < 5:
            logger.warning(f"班级数量较少，可能影响班级层面分析: {data['class_idx'].nunique()}个班级")
        
        # 检查前测后测数据
        if 'time_point' in data.columns and data['time_point'].nunique() < 2:
            raise ValueError("至少需要两个时间点的数据")
        
        # 检查必要字段
        required_fields = ['prior_score', 'standard_score', 'student_idx']
        missing_fields = [f for f in required_fields if f not in data.columns]
        if missing_fields:
            raise ValueError(f"数据缺少必要字段: {missing_fields}")
        
        # 检查缺失值
        na_counts = data[required_fields].isna().sum()
        if na_counts.sum() > 0:
            raise ValueError(f"数据存在缺失值: {na_counts}")
            
        return True


#############################################
# 第二部分: 模型基类与实现
#############################################

class BaseValueAddedModel(ABC):
    """
    增值分析模型基类
    
    定义所有增值模型需要实现的通用接口
    """
    
    def __init__(self, data=None):
        """
        初始化模型
        
        Args:
            data: 建模数据
        """
        self.data = data
        self.model = None
        self.results = None
        self.metrics = {}
    
    def fit(self, data=None):
        """
        拟合模型
        
        Args:
            data: 建模数据，如果为None则使用初始化时的数据
            
        Returns:
            self: 支持链式调用
        """
        if data is not None:
            self.data = data
        
        if self.data is None:
            raise ValueError("请提供建模数据")
        
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
        if self.results is None:
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
        if self.results is None:
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
        if self.results is None:
            raise ValueError("请先拟合模型")
            
        # 确保目录存在
        os.makedirs(output_dir, exist_ok=True)
        
        # 保存指标
        metrics_path = os.path.join(output_dir, "model_metrics.json")
        with open(metrics_path, 'w') as f:
            json.dump(self.metrics, f, indent=2)
            
        # 子类可扩展此方法保存更多内容
        return {"metrics": metrics_path}

class FrequentistValueAddedModel(BaseValueAddedModel):
    """频率派多层次增值模型实现"""
    
    def _validate_data(self):
        """验证频率派模型所需数据"""
        required_fields = ['prior_score', 'standard_score']
        missing_fields = [f for f in required_fields if f not in self.data.columns]
        if missing_fields:
            raise ValueError(f"数据缺少频率派模型所需字段: {missing_fields}")
    
    def _build_model(self):
        """构建频率派多层次线性模型"""
        # 准备模型数据
        model_data = self.data.copy()
        
        # 构建混合线性模型公式
        if 'school_idx' in model_data.columns and 'class_idx' in model_data.columns:
            formula = "standard_score ~ prior_score + (1|school_idx) + (1|class_idx)"
        elif 'class_idx' in model_data.columns:
            formula = "standard_score ~ prior_score + (1|class_idx)"
        else:
            formula = "standard_score ~ prior_score"
        
        # 创建模型
        self.model = smf.mixedlm(formula, model_data, groups=model_data["student_id"])
    
    def _fit_model(self):
        """拟合频率派模型"""
        self.results = self.model.fit()
        
        # 计算模型评估指标
        self.metrics = {
            'aic': self.results.aic,
            'bic': self.results.bic,
            'r_squared': self.results.rsquared,
            'r_squared_adj': self.results.rsquared_adj,
            'log_likelihood': self.results.llf
        }
    
    def _predict_impl(self, new_data):
        """频率派模型预测实现"""
        return self.results.predict(new_data)
    
    def _calculate_value_added_impl(self):
        """计算频率派模型的增值效应"""
        # 提取随机效应
        re_results = self.results.random_effects
        
        # 班级增值效应
        if 'class_idx' in self.data.columns:
            class_effects = pd.DataFrame({
                'class_id': self.data['class_idx'].map(
                    {v: k for k, v in self.data.groupby('class_idx')['norm_class_group'].first().items()}
                ).unique(),
                'value_added': [re.get(1, [0])[0] for re in re_results.values()]
            })
            class_effects = class_effects.set_index('class_id')
        else:
            class_effects = pd.DataFrame()
        
        # 学校增值效应（如果有）
        if 'school_idx' in self.data.columns:
            school_effects = pd.DataFrame({
                'school_id': self.data['school_idx'].map(
                    {v: k for k, v in self.data.groupby('school_idx')['school_id'].first().items()}
                ).unique(),
                'value_added': [re.get(2, [0])[0] if len(re) > 1 else 0 for re in re_results.values()]
            })
            school_effects = school_effects.set_index('school_id')
        else:
            school_effects = pd.DataFrame()
        
        return {
            'schools': school_effects,
            'classes': class_effects,
            'students': pd.DataFrame()  # 此模型未计算学生层面效应
        }
    
class BayesianValueAddedModel(BaseValueAddedModel):
    """贝叶斯多层次增值模型实现"""
    
    def __init__(self, data=None, mcmc_samples=2000, tune=1000, chains=4):
        """
        初始化贝叶斯模型
        
        Args:
            data: 建模数据
            mcmc_samples: MCMC采样次数
            tune: 调优步数
            chains: 链数量
        """
        super().__init__(data)
        self.mcmc_samples = mcmc_samples
        self.tune = tune
        self.chains = chains
        self.trace = None
    
    def _validate_data(self):
        """验证贝叶斯模型所需数据"""
        required_fields = [
            'prior_score_z', 'standard_score_z', 
            'school_idx', 'class_idx', 'student_idx'
        ]
        
        missing_fields = [f for f in required_fields if f not in self.data.columns]
        if missing_fields:
            raise ValueError(f"数据缺少贝叶斯模型所需字段: {missing_fields}")
    
    def _build_model(self):
        """构建贝叶斯多层次线性模型"""
        # 获取模型输入
        y = self.data['standard_score_z'].values  # 标准化后测成绩
        x = self.data['prior_score_z'].values     # 标准化前测成绩
        school_idx = self.data['school_idx'].values
        class_idx = self.data['class_idx'].values
        student_idx = self.data['student_idx'].values
        
        # 唯一索引数量
        n_schools = len(np.unique(school_idx))
        n_classes = len(np.unique(class_idx))
        n_students = len(np.unique(student_idx))
        
        # 构建模型
        with pm.Model() as model:
            # 全局截距和斜率
            intercept = pm.Normal('intercept', mu=0, sigma=1)
            beta_prior = pm.Normal('beta_prior', mu=0.8, sigma=0.2)
            
            # 学校随机效应
            sigma_school = pm.HalfNormal('sigma_school', sigma=0.5)
            school_effects = pm.Normal('school_effects', mu=0, sigma=sigma_school, shape=n_schools)
            
            # 班级随机效应
            sigma_class = pm.HalfNormal('sigma_class', sigma=0.5)
            class_effects = pm.Normal('class_effects', mu=0, sigma=sigma_class, shape=n_classes)
            
            # 学生随机效应
            sigma_student = pm.HalfNormal('sigma_student', sigma=0.5)
            student_effects = pm.Normal('student_effects', mu=0, sigma=sigma_student, shape=n_students)
            
            # 模型期望值
            mu = (intercept + beta_prior * x + 
                 school_effects[school_idx] + class_effects[class_idx] + student_effects[student_idx])
            
            # 观测误差
            sigma_y = pm.HalfNormal('sigma_y', sigma=0.5)
            
            # 似然函数
            y_obs = pm.Normal('y_obs', mu=mu, sigma=sigma_y, observed=y)
        
        self.model = model
    
    def _fit_model(self):
        """拟合贝叶斯模型"""
        with self.model:
            # MCMC采样
            self.trace = pm.sample(
                draws=self.mcmc_samples,
                tune=self.tune,
                chains=self.chains,
                return_inferencedata=True,
                target_accept=0.9
            )
            
        # 收敛性检查
        rhat_values = az.rhat(self.trace)
        max_rhat = float(np.max(rhat_values.values))
        
        self.metrics = {
            'max_rhat': max_rhat,
            'converged': max_rhat < 1.05,
            'n_samples': self.mcmc_samples,
            'n_chains': self.chains,
            'effective_sample_size': float(az.ess(self.trace)["y_obs"].mean())
        }
        
        self.results = {
            'trace': self.trace,
            'metrics': self.metrics
        }
    
    def _predict_impl(self, new_data):
        """贝叶斯模型预测实现"""
        # 简单实现：使用后验均值进行点预测
        intercept = float(self.trace.posterior.intercept.mean())
        beta_prior = float(self.trace.posterior.beta_prior.mean())
        
        # 获取随机效应均值
        school_effects = self.trace.posterior.school_effects.mean(dim=("chain", "draw")).values
        class_effects = self.trace.posterior.class_effects.mean(dim=("chain", "draw")).values
        student_effects = self.trace.posterior.student_effects.mean(dim=("chain", "draw")).values
        
        # 映射新数据索引
        school_idx = new_data['school_idx'].values
        class_idx = new_data['class_idx'].values
        student_idx = new_data['student_idx'].values
        prior_z = new_data['prior_score_z'].values
        
        # 计算预测值
        predictions = (
            intercept + 
            beta_prior * prior_z + 
            school_effects[school_idx] + 
            class_effects[class_idx] + 
            student_effects[student_idx]
        )
        
        return predictions
    
    def _calculate_value_added_impl(self):
        """计算贝叶斯模型的增值效应"""
        # 班级增值效应
        class_value_added = az.summary(self.trace.posterior.class_effects)
        class_value_added.index = self.data['class_idx'].map(
            {v: k for k, v in self.data.groupby('class_idx')['norm_class_group'].first().items()}
        ).unique()
        
        # 学校增值效应
        school_value_added = az.summary(self.trace.posterior.school_effects)
        school_value_added.index = self.data['school_idx'].map(
            {v: k for k, v in self.data.groupby('school_idx')['school_id'].first().items()}
        ).unique()
        
        # 学生增值效应
        student_value_added = az.summary(self.trace.posterior.student_effects)
        student_value_added.index = self.data['student_idx'].map(
            {v: k for k, v in self.data.groupby('student_idx')['student_id'].first().items()}
        ).unique()
        
        return {
            'schools': school_value_added,
            'classes': class_value_added,
            'students': student_value_added
        }
    
    def save_results(self, output_dir):
        """保存贝叶斯模型结果"""
        # 调用父类方法保存通用指标
        saved_paths = super().save_results(output_dir)
        
        # 保存模型特有结果
        trace_path = os.path.join(output_dir, "bayesian_trace.nc")
        self.trace.to_netcdf(trace_path)
        saved_paths["trace"] = trace_path
        
        # 保存后验分布图
        post_path = os.path.join(output_dir, "posterior_distributions.png")
        az.plot_posterior(self.trace, var_names=['intercept', 'beta_prior'])
        plt.tight_layout()
        plt.savefig(post_path, dpi=300)
        saved_paths["posterior_plot"] = post_path
        
        # 保存增值效应
        value_added = self.calculate_value_added()
        for level, df in value_added.items():
            va_path = os.path.join(output_dir, f"{level}_value_added.csv")
            df.to_csv(va_path)
            saved_paths[f"{level}_value_added"] = va_path
        
        return saved_paths





class DynamicBayesianValueAddedModel(BaseValueAddedModel):
    """
    动态贝叶斯模型(卡尔曼滤波)实现的学习潜力跟踪
    
    使用卡尔曼滤波算法实时更新学生学习潜力估计，能够：
    1. 实时跟踪学生潜力变化
    2. 检测异常表现
    3. 提供个性化干预建议
    """
    
    def __init__(self, data=None, process_var=2.0, obs_var=5.0, initial_var=10.0):
        """
        初始化动态贝叶斯模型
        
        Args:
            data: 建模数据
            process_var: 过程噪声方差(Q)，表示潜力变化的随机性
            obs_var: 观测噪声方差(R)，表示考试成绩的随机误差
            initial_var: 初始状态方差(P0)，表示对首次成绩的不确定性
        """
        super().__init__(data)
        self.process_var = process_var  # Q
        self.obs_var = obs_var          # R
        self.initial_var = initial_var  # P0
        
        # 存储滤波结果
        self.state_means = {}  # 每个学生在每个时间点的潜力估计均值
        self.state_vars = {}   # 每个学生在每个时间点的潜力估计方差
        self.innovations = {}  # 每个学生在每个时间点的新息序列
        self.anomalies = {}    # 记录异常状态
        
    def _validate_data(self):
        """验证动态贝叶斯模型所需数据"""
        required_fields = ['student_id', 'standard_score', 'time_point']
        missing_fields = [f for f in required_fields if f not in self.data.columns]
        if missing_fields:
            raise ValueError(f"数据缺少动态贝叶斯模型所需字段: {missing_fields}")
            
        # 验证时间点完整性
        time_points = self.data.groupby('student_id')['time_point'].nunique()
        if time_points.min() < 2:
            logger.warning(f"有{sum(time_points < 2)}名学生数据点少于2个，模型可能无法准确估计其潜力变化")
            
        # 验证时间排序
        time_order = self.data.groupby('student_id')['time_point'].apply(lambda x: all(np.diff(x) > 0))
        if not all(time_order):
            raise ValueError("部分学生的时间点数据未按顺序排列，请先对数据进行排序")
    
    def _build_model(self):
        """构建卡尔曼滤波状态空间模型"""
        # 卡尔曼滤波不需要像PyMC那样预先构建完整模型
        # 而是在_fit_model方法中实现递归更新算法
        self.model = {
            'process_var': self.process_var,    # Q - 状态转移噪声方差
            'obs_var': self.obs_var,            # R - 观测噪声方差
            'initial_var': self.initial_var     # P0 - 初始状态方差
        }
        logger.info(f"构建卡尔曼滤波模型: Q={self.process_var}, R={self.obs_var}, P0={self.initial_var}")
    
    def _fit_model(self):
        """实现卡尔曼滤波递归算法"""
        # 按学生分组进行滤波
        student_groups = self.data.groupby('student_id')
        
        # 存储结果
        all_theta = []  # 所有学生的潜力估计
        all_P = []      # 所有学生的估计方差
        all_K = []      # 所有学生的卡尔曼增益
        all_inn = []    # 所有学生的新息序列
        anomaly_flags = []  # 异常标记
        
        for student_id, student_data in student_groups:
            # 按时间排序
            student_data = student_data.sort_values('time_point')
            scores = student_data['standard_score'].values
            time_points = student_data['time_point'].values
            
            # 初始化状态
            theta = np.zeros(len(scores))  # 潜力估计
            P = np.zeros(len(scores))      # 估计方差
            K = np.zeros(len(scores))      # 卡尔曼增益
            innovations = np.zeros(len(scores))  # 新息
            anomaly = np.zeros(len(scores), dtype=bool)  # 异常标记
            
            # 初始状态设置
            theta[0] = scores[0]  # 首次成绩作为初始潜力估计
            P[0] = self.initial_var  # 初始不确定性
            
            # 卡尔曼滤波递归更新
            for t in range(1, len(scores)):
                # 预测步
                theta_pred = theta[t-1]  # 状态预测 (线性假设: theta_t = theta_{t-1})
                P_pred = P[t-1] + self.process_var  # 预测方差更新
                
                # 计算卡尔曼增益
                K[t] = P_pred / (P_pred + self.obs_var)
                
                # 计算新息(观测残差)
                innovations[t] = scores[t] - theta_pred
                
                # 异常检测(新息超过3个标准差)
                anomaly[t] = abs(innovations[t]) > 3 * np.sqrt(P_pred + self.obs_var)
                
                # 更新步
                theta[t] = theta_pred + K[t] * innovations[t]  # 状态更新
                P[t] = (1 - K[t]) * P_pred  # 方差更新
            
            # 保存该学生的滤波结果
            self.state_means[student_id] = theta
            self.state_vars[student_id] = P
            self.innovations[student_id] = innovations
            self.anomalies[student_id] = anomaly
            
            # 添加到总结果
            rows = student_data.index
            all_theta.extend(list(zip(rows, theta)))
            all_P.extend(list(zip(rows, P)))
            all_K.extend(list(zip(rows, K)))
            all_inn.extend(list(zip(rows, innovations)))
            anomaly_flags.extend(list(zip(rows, anomaly)))
        
        # 转换为DataFrame格式
        self.results = {
            'filtered_theta': pd.DataFrame([{'index': idx, 'theta': val} for idx, val in all_theta]).set_index('index')['theta'],
            'filter_variance': pd.DataFrame([{'index': idx, 'P': val} for idx, val in all_P]).set_index('index')['P'],
            'kalman_gain': pd.DataFrame([{'index': idx, 'K': val} for idx, val in all_K]).set_index('index')['K'],
            'innovations': pd.DataFrame([{'index': idx, 'inn': val} for idx, val in all_inn]).set_index('index')['inn'],
            'anomaly': pd.DataFrame([{'index': idx, 'is_anomaly': val} for idx, val in anomaly_flags]).set_index('index')['is_anomaly'],
        }
        
        # 计算评估指标
        self.metrics = {
            'mean_innovation': float(np.nanmean([i for i in self.results['innovations'] if not np.isnan(i)])),
            'innovation_std': float(np.nanstd([i for i in self.results['innovations'] if not np.isnan(i)])),
            'anomaly_rate': float(np.mean(self.results['anomaly'])),
            'mean_kalman_gain': float(np.nanmean([k for k in self.results['kalman_gain'] if not np.isnan(k)])),
        }
        
        # 合并结果到原始数据
        for col, values in self.results.items():
            self.data[col] = values
            
        logger.info(f"动态贝叶斯模型拟合完成: 平均新息={self.metrics['mean_innovation']:.4f}, 异常率={self.metrics['anomaly_rate']:.2%}")
    
    def _predict_impl(self, new_data):
        """动态贝叶斯模型预测实现"""
        # 如果新数据是单个学生的后续考试
        predictions = []
        
        for i, row in new_data.iterrows():
            student_id = row['student_id']
            if student_id in self.state_means and len(self.state_means[student_id]) > 0:
                # 使用该学生的最后一个潜力估计作为预测
                last_theta = self.state_means[student_id][-1]
                predictions.append(last_theta)
            else:
                # 对于新学生，使用总体平均潜力
                avg_theta = np.mean([theta[-1] for theta in self.state_means.values()])
                predictions.append(avg_theta)
                
        return np.array(predictions)
    
    def _calculate_value_added_impl(self):
        """计算动态贝叶斯模型的增值效应"""
        # 计算学生层面的潜力增长率
        student_growth = {}
        for student_id, theta in self.state_means.items():
            if len(theta) >= 2:
                # 计算首尾潜力差值
                growth = theta[-1] - theta[0]
                # 计算平均每单位时间的增长率
                time_span = len(theta) - 1
                growth_rate = growth / time_span
                student_growth[student_id] = growth_rate
        
        # 转换为DataFrame
        student_va = pd.DataFrame({
            'student_id': list(student_growth.keys()),
            'value_added': list(student_growth.values())
        })
        student_va = student_va.set_index('student_id')
        
        # 聚合到班级层面
        student_class = self.data[['student_id', 'norm_class_group']].drop_duplicates()
        student_class = student_class.set_index('student_id')
        
        if not student_va.empty and not student_class.empty:
            # 合并学生增值和班级信息
            merged = student_va.join(student_class, how='inner')
            
            # 计算班级平均增值
            class_va = merged.groupby('norm_class_group')['value_added'].agg(['mean', 'std', 'count']).reset_index()
            class_va = class_va.rename(columns={'mean': 'value_added'})
            class_va = class_va.set_index('norm_class_group')
            
            # 如果有学校信息，也计算学校层面增值
            if 'school_id' in self.data.columns:
                student_school = self.data[['student_id', 'school_id']].drop_duplicates()
                student_school = student_school.set_index('student_id')
                
                # 合并学生增值和学校信息
                school_merged = student_va.join(student_school, how='inner')
                
                # 计算学校平均增值
                school_va = school_merged.groupby('school_id')['value_added'].agg(['mean', 'std', 'count']).reset_index()
                school_va = school_va.rename(columns={'mean': 'value_added'})
                school_va = school_va.set_index('school_id')
            else:
                school_va = pd.DataFrame()
        else:
            class_va = pd.DataFrame()
            school_va = pd.DataFrame()
        
        return {
            'students': student_va,
            'classes': class_va,
            'schools': school_va
        }
    
    def get_potential_trajectory(self, student_id):
        """
        获取学生潜力轨迹
        
        Args:
            student_id: 学生ID
            
        Returns:
            dict: 包含潜力轨迹、方差和异常标记
        """
        if student_id not in self.state_means:
            return None
            
        student_data = self.data[self.data['student_id'] == student_id].sort_values('time_point')
        time_points = student_data['time_point'].values
        scores = student_data['standard_score'].values
        
        return {
            'time_points': time_points,
            'observed_scores': scores,
            'potential': self.state_means[student_id],
            'variance': self.state_vars[student_id],
            'anomalies': self.anomalies[student_id],
            'innovations': self.innovations[student_id]
        }
    
    def detect_anomalies(self):
        """
        检测并返回异常表现
        
        Returns:
            DataFrame: 包含异常表现的记录
        """
        # 合并结果到完整数据集
        anomaly_data = self.data.copy()
        
        # 添加Z分数(标准化新息)
        anomaly_data['z_score'] = anomaly_data['innovations'] / np.sqrt(
            anomaly_data['filter_variance'] + self.obs_var
        )
        
        # 筛选异常记录
        anomalies = anomaly_data[anomaly_data['anomaly']]
        
        # 添加异常类型
        anomalies['anomaly_type'] = np.where(
            anomalies['z_score'] > 0,
            '异常进步',
            '异常退步'
        )
        
        return anomalies
    
    def analyze_potential_trends(self):
        """
        分析学生潜力变化趋势
        
        Returns:
            DataFrame: 学生潜力趋势分析结果
        """
        trend_results = []
        
        for student_id, theta in self.state_means.items():
            if len(theta) < 3:
                continue
                
            # 计算线性趋势(简单回归)
            time_points = np.arange(len(theta))
            slope, intercept = np.polyfit(time_points, theta, 1)
            
            # 判断趋势类型
            if slope > 0.05:
                trend = "上升"
            elif slope < -0.05:
                trend = "下降"
            else:
                trend = "稳定"
                
            # 计算波动性(均方根误差)
            line = intercept + slope * time_points
            volatility = np.sqrt(np.mean((theta - line)**2))
            
            trend_results.append({
                'student_id': student_id,
                'slope': slope,
                'volatility': volatility,
                'trend': trend
            })
            
        return pd.DataFrame(trend_results)
        
    def save_results(self, output_dir):
        """保存动态贝叶斯模型结果"""
        # 调用父类方法保存通用指标
        saved_paths = super().save_results(output_dir)
        
        # 保存潜力轨迹
        trajectory_path = os.path.join(output_dir, "potential_trajectories.csv")
        
        # 构建轨迹数据
        trajectories = []
        for student_id in self.state_means:
            student_data = self.data[self.data['student_id'] == student_id].sort_values('time_point')
            for i, row in student_data.iterrows():
                time_idx = int(row['time_point'])
                if time_idx < len(self.state_means[student_id]):
                    trajectories.append({
                        'student_id': student_id,
                        'time_point': time_idx,
                        'observed_score': row['standard_score'],
                        'potential_estimate': self.state_means[student_id][time_idx],
                        'estimate_variance': self.state_vars[student_id][time_idx],
                        'is_anomaly': self.anomalies[student_id][time_idx]
                    })
        
        trajectory_df = pd.DataFrame(trajectories)
        trajectory_df.to_csv(trajectory_path, index=False)
        saved_paths["trajectories"] = trajectory_path
        
        # 保存异常检测结果
        anomalies = self.detect_anomalies()
        anomaly_path = os.path.join(output_dir, "anomalies.csv")
        anomalies.to_csv(anomaly_path, index=False)
        saved_paths["anomalies"] = anomaly_path
        
        # 保存趋势分析结果
        trends = self.analyze_potential_trends()
        trends_path = os.path.join(output_dir, "potential_trends.csv")
        trends.to_csv(trends_path, index=False)
        saved_paths["trends"] = trends_path
        
        # 可视化潜力变化示例(选择几个有代表性的学生)
        self._plot_example_trajectories(output_dir)
        
        return saved_paths
    
    def _plot_example_trajectories(self, output_dir):
        """绘制示例学生潜力轨迹"""
        # 获取数据丰富的学生(至少3次考试)
        rich_students = [sid for sid, theta in self.state_means.items() if len(theta) >= 3]
        if not rich_students:
            return
            
        # 选择最多4个学生展示
        sample_size = min(4, len(rich_students))
        
        # 选择样本学生(可以根据特定规则选择)
        # 这里简单随机选择
        np.random.seed(42)  # 固定随机数种子以保证可复现
        sample_students = np.random.choice(rich_students, sample_size, replace=False)
        
        # 创建多子图
        fig, axes = plt.subplots(sample_size, 1, figsize=(10, 4*sample_size))
        if sample_size == 1:
            axes = [axes]
            
        for i, student_id in enumerate(sample_students):
            ax = axes[i]
            trajectory = self.get_potential_trajectory(student_id)
            
            if trajectory:
                # 绘制实际成绩
                ax.scatter(trajectory['time_points'], trajectory['observed_scores'], 
                           color='blue', label='实际成绩', zorder=3)
                
                # 绘制潜力估计曲线
                ax.plot(trajectory['time_points'], trajectory['potential'], 
                        color='red', label='潜力估计', zorder=2)
                
                # 绘制95%置信区间
                upper = trajectory['potential'] + 1.96 * np.sqrt(trajectory['variance'])
                lower = trajectory['potential'] - 1.96 * np.sqrt(trajectory['variance'])
                ax.fill_between(trajectory['time_points'], lower, upper, 
                                color='red', alpha=0.2, label='95%置信区间')
                
                # 标记异常点
                anomaly_points = np.where(trajectory['anomalies'])[0]
                if len(anomaly_points) > 0:
                    anomaly_x = [trajectory['time_points'][j] for j in anomaly_points]
                    anomaly_y = [trajectory['observed_scores'][j] for j in anomaly_points]
                    ax.scatter(anomaly_x, anomaly_y, color='orange', s=100, marker='*', 
                               label='异常表现', zorder=4)
                
                ax.set_title(f'学生{student_id}潜力轨迹')
                ax.set_xlabel('时间点')
                ax.set_ylabel('分数/潜力估计值')
                ax.grid(True, linestyle='--', alpha=0.7)
                ax.legend()
        
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, "example_trajectories.png"), dpi=300)
        plt.close()


#############################################
# 第三部分: 结果输出与可视化
#############################################

class ValueAddedVisualizer:
    """增值分析结果可视化器"""
    
    def __init__(self, results=None):
        """
        初始化可视化器
        
        Args:
            results: 模型结果字典
        """
        self.results = results
    
    def visualize(self, output_dir, results=None):
        """
        生成可视化结果
        
        Args:
            output_dir: 输出目录
            results: 模型结果字典，如果为None则使用初始化时的结果
            
        Returns:
            dict: 保存的文件路径
        """
        if results is not None:
            self.results = results
            
        if self.results is None:
            raise ValueError("请提供模型结果")
            
        # 确保目录存在
        os.makedirs(output_dir, exist_ok=True)
        
        # 保存的文件路径
        saved_paths = {}
        
        # 1. 生成各层级增值效应分布图
        for level in ['schools', 'classes']:
            if level in self.results and not self.results[level].empty:
                fig_path = os.path.join(output_dir, f"{level}_value_added_dist.png")
                self._plot_value_added_distribution(
                    self.results[level], 
                    title=f"{level.capitalize()} Value-Added Distribution",
                    output_path=fig_path
                )
                saved_paths[f"{level}_dist"] = fig_path
        
        # 2. 生成学校-班级关系图
        if 'schools' in self.results and 'classes' in self.results:
            if not self.results['schools'].empty and not self.results['classes'].empty:
                fig_path = os.path.join(output_dir, "school_class_relationship.png")
                self._plot_school_class_relationship(output_path=fig_path)
                saved_paths["school_class_relationship"] = fig_path
        
        # 3. 生成增值效应评级图
        for level in ['schools', 'classes']:
            if level in self.results and not self.results[level].empty:
                fig_path = os.path.join(output_dir, f"{level}_rating.png")
                self._plot_rating_distribution(
                    self.results[level], 
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
        schools = self.results['schools']
        classes = self.results['classes']
        
        # 通过合并数据准备绘图数据
        # 这里需要具体的数据结构来实现
        # ...
        
        plt.figure(figsize=(12, 8))
        # 实现绘图代码
        # ...
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


#############################################
# 第四部分: 命令示例
#############################################

# 示例：如何在Django命令中使用
"""
使用方法示例:

from django.core.management.base import BaseCommand
from core.models.value_added_framework import (
    ValueAddedDataProcessor, 
    BayesianValueAddedModel,
    ValueAddedVisualizer
)

class Command(BaseCommand):
    help = '使用贝叶斯多层次模型进行增值分析'
    
    def add_arguments(self, parser):
        parser.add_argument('--exams', nargs='+', required=True)
        parser.add_argument('--subject', required=True)
        parser.add_argument('--output', default='results/')
        
    def handle(self, *args, **options):
        # 1. 初始化数据处理器
        from core.management.commands.education_data_provider import EducationDataProvider
        provider = EducationDataProvider(
            exam_ids=options['exams'],
            subject_id=options['subject']
        )
        processor = ValueAddedDataProcessor(provider)
        
        # 2. 加载和处理数据
        processor.load_data()
        model_data = processor.prepare_model_data()
        
        # 3. 初始化和拟合模型
        model = BayesianValueAddedModel(model_data)
        model.fit()
        
        # 4. 计算增值效应
        value_added = model.calculate_value_added()
        
        # 5. 可视化结果
        visualizer = ValueAddedVisualizer(value_added)
        visualizer.visualize(options['output'])
        
        # 6. 保存结果
        model.save_results(options['output'])
""" 