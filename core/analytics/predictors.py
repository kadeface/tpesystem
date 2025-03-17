# core/analytics/predictors.py
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.model_selection import train_test_split
import joblib
import os

class StudentPerformancePredictor:
    """学生表现预测器"""
    
    def __init__(self, model_path=None):
        self.model_path = model_path or 'student_predictor.joblib'
        self.model = self._load_model() if os.path.exists(self.model_path) else None
        
    def _load_model(self):
        """加载预训练模型"""
        try:
            return joblib.load(self.model_path)
        except:
            return None
            
    def train(self, features_df, target_column, force_retrain=False):
        """
        训练学生表现预测模型
        
        Args:
            features_df: 特征数据框
            target_column: 目标列名
            force_retrain: 是否强制重新训练
            
        Returns:
            训练好的模型
        """
        if self.model is not None and not force_retrain:
            return self.model
            
        if features_df.empty:
            raise ValueError("无法使用空数据框训练模型")
            
        # 区分数值和分类特征
        numeric_features = features_df.select_dtypes(include=['int64', 'float64']).columns.tolist()
        categorical_features = features_df.select_dtypes(include=['object', 'category']).columns.tolist()
        
        # 排除目标列
        if target_column in numeric_features:
            numeric_features.remove(target_column)
        if target_column in categorical_features:
            categorical_features.remove(target_column)
            
        # 特征工程管道
        preprocessor = ColumnTransformer(
            transformers=[
                ('num', StandardScaler(), numeric_features),
                ('cat', OneHotEncoder(handle_unknown='ignore'), categorical_features)
            ],
            remainder='drop'
        )
        
        # 创建模型管道
        self.model = Pipeline(steps=[
            ('preprocessor', preprocessor),
            ('regressor', RandomForestRegressor(n_estimators=100, random_state=42))
        ])
        
        # 准备训练数据
        X = features_df.drop(columns=[target_column])
        y = features_df[target_column]
        
        # 训练模型
        self.model.fit(X, y)
        
        # 保存模型
        joblib.dump(self.model, self.model_path)
        
        return self.model
    
    def predict_next_scores(self, student_history, next_semester_features):
        """
        预测学生下学期成绩
        
        Args:
            student_history: 学生历史数据
            next_semester_features: 下学期特征
            
        Returns:
            dict: 各学科预测成绩
        """
        if self.model is None:
            raise ValueError("模型尚未训练，无法预测")
            
        # 确保特征与训练时一致
        prediction = self.model.predict(next_semester_features)
        
        return prediction