"""
教学增值核心算法模块
包含排名赋分、进步分析、综合评估等核心算法
"""

class ScoreStrategy:
    """赋分策略基类"""
    def calculate(self, data: pd.Series) -> pd.Series:
        raise NotImplementedError

class TieredScoring(ScoreStrategy):
    """
    分层赋分算法
    
    Args:
        tiers: 分层配置字典，格式为{分数: 最大排名}
               Example: {8:22, 6:52, 5:89, 4:127, 3:164, 2:194}
        ascending: 排序方向（True=升序，False=降序）
    """
    def __init__(self, tiers: dict, ascending: bool):
        self.tiers = sorted(tiers.items(), key=lambda x: x[1])
        self.ascending = ascending
        
    def calculate(self, data: pd.Series) -> pd.Series:
        """执行分层赋分计算"""
        ranked = data.rank(ascending=self.ascending, method="min")
        return ranked.apply(self._apply_tier_logic)

    def _apply_tier_logic(self, rank):
        for score, max_rank in self.tiers:
            if rank <= max_rank:
                return score
        return 0

class ProgressCalculator:
    """
    教学进步分析算法
    
    Args:
        baseline: 基准期数据 (DataFrame)
        current: 当前期数据 (DataFrame)
        config: 算法配置字典，包含：
               - 特殊学校ID
               - 权重配置
               - 指标字段映射
    """
    def __init__(self, baseline: pd.DataFrame, current: pd.DataFrame, config: dict):
        self.baseline = baseline.set_index(['xxh', 'bb'])
        self.current = current.set_index(['xxh', 'bb'])
        self.special_school_id = config.get('special_school_id', 78319)
        self.weights = config.get('weights', {'current':0.4, 'progress':0.6})
        
    def calculate_progress(self) -> pd.DataFrame:
        """执行完整进步分析流程"""
        # 数据对齐
        common_index = self.baseline.index.intersection(self.current.index)
        
        # 计算原始进步值
        progress_values = self.current - self.baseline
        
        # 特殊学校处理
        special_mask = self._get_special_school_mask()
        adjusted_progress = self._adjust_special_schools(progress_values, special_mask)
        
        # 计算各项得分
        current_scores = self._calculate_current_scores(special_mask)
        progress_scores = self._calculate_progress_scores(adjusted_progress, special_mask)
        
        # 综合评估
        return self._compile_final_scores(current_scores, progress_scores)

    def _get_special_school_mask(self):
        return self.current.index.get_level_values('xxh') == self.special_school_id

    def _adjust_special_schools(self, progress: pd.DataFrame, mask: pd.Series) -> pd.DataFrame:
        """特殊学校进步值调整"""
        adjusted = progress.copy()
        # 非低分率指标乘以系数
        non_dfl_cols = [col for col in progress.columns if not col.endswith('dfl')]
        adjusted.loc[mask, non_dfl_cols] *= 1.333
        return adjusted

    def _calculate_current_scores(self, special_mask: pd.Series) -> pd.DataFrame:
        """计算本期表现得分"""
        # 初始化评分策略
        main_strategy = TieredScoring(
            tiers={8:22, 6:52, 5:89, 4:127, 3:164, 2:194}, 
            ascending=False
        )
        dfl_strategy = TieredScoring(
            tiers={8:22, 6:52, 5:89, 4:127, 3:164, 2:194},
            ascending=True
        )
        
        scores = pd.DataFrame(index=self.current.index)
        for col in self.current.columns:
            strategy = dfl_strategy if col.endswith('dfl') else main_strategy
            scores[f"{col}_score"] = strategy.calculate(self.current[col])
        return scores

    def _calculate_progress_scores(self, progress: pd.DataFrame, special_mask: pd.Series) -> pd.DataFrame:
        """计算进步得分"""
        strategy = TieredScoring(
            tiers={8:22, 6:52, 5:89, 4:127, 3:164, 2:194},
            ascending=False
        )
        return progress.apply(strategy.calculate, axis=0)

    def _compile_final_scores(self, current_scores: pd.DataFrame, progress_scores: pd.DataFrame) -> pd.DataFrame:
        """生成最终综合得分"""
        # 计算总分
        current_total = current_scores.sum(axis=1)
        progress_total = progress_scores.sum(axis=1)
        
        # 综合评估
        composite_score = (current_total * self.weights['current'] + 
                          progress_total * self.weights['progress'])
        
        # 构建结果数据框
        result = self.current.reset_index()[['xxh', 'xxmc', 'bb']]
        result = result.merge(
            current_scores.add_prefix('current_'), 
            left_on=['xxh', 'bb'], 
            right_index=True
        )
        result = result.merge(
            progress_scores.add_prefix('progress_'),
            left_on=['xxh', 'bb'],
            right_index=True
        )
        result['composite_score'] = composite_score.values
        return result.sort_values('composite_score', ascending=False) 