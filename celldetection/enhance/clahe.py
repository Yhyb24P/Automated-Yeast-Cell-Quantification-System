#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
CLAHE增强模块

提供对比度受限的自适应直方图均衡化功能，用于增强细胞图像对比度。
"""

import cv2
import numpy as np
from typing import Tuple, Optional

def apply_clahe(image: np.ndarray, 
               clip_limit: float = 2.0,
               tile_grid_size: Tuple[int, int] = (8, 8)) -> np.ndarray:
    """应用CLAHE（对比度受限的自适应直方图均衡化）
    
    Args:
        image: 输入图像
        clip_limit: 对比度限制
        tile_grid_size: 网格大小
        
    Returns:
        增强后的图像
    """
    # 转换为LAB颜色空间
    lab = cv2.cvtColor(image, cv2.COLOR_RGB2LAB)
    l, a, b = cv2.split(lab)
    
    # 应用CLAHE到L通道
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid_size)
    l = clahe.apply(l)
    
    # 合并通道
    lab = cv2.merge((l, a, b))
    
    # 转换回RGB
    enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
    
    return enhanced

def adaptive_clahe(image: np.ndarray, 
                  low_contrast_threshold: int = 30,
                  min_clip_limit: float = 1.0,
                  max_clip_limit: float = 4.0) -> np.ndarray:
    """自适应CLAHE，根据图像特性动态调整参数
    
    Args:
        image: 输入图像
        low_contrast_threshold: 低对比度阈值
        min_clip_limit: 最小对比度限制
        max_clip_limit: 最大对比度限制
        
    Returns:
        增强后的图像
    """
    # 转换为灰度图以分析图像特性
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    else:
        gray = image
    
    # 计算标准差作为对比度指标
    std = np.std(gray)
    
    # 根据标准差动态调整clip limit
    # 低对比度图像使用更高的clip limit
    clip_limit = max(min_clip_limit, min(max_clip_limit, 5.0 - std / 50))
    
    # 低对比度图像使用更小的网格
    grid_size = (4, 4) if std < low_contrast_threshold else (8, 8)
    
    # 应用CLAHE
    return apply_clahe(image, clip_limit=clip_limit, tile_grid_size=grid_size)
