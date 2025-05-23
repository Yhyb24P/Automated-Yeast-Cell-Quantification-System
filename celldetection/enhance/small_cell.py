#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
小细胞增强模块

提供专门针对小尺寸细胞的增强算法，改善小目标的可见性。
"""

import cv2
import numpy as np

def enhance_small_cells(image, cell_size_threshold=0.005):
    """增强小细胞目标
    
    Args:
        image: 输入图像
        cell_size_threshold: 小细胞的相对大小阈值
        
    Returns:
        增强后的图像
    """
    # 图像尺寸
    h, w = image.shape[:2]
    min_dim = min(h, w)
    
    # 计算小细胞的像素尺寸阈值
    cell_pixel_threshold = int(min_dim * cell_size_threshold)
    
    # 转为灰度图
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    
    # 自适应阈值处理
    binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                  cv2.THRESH_BINARY_INV, 11, 2)
    
    # 获取连通区域
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary)
    
    # 创建掩码 - 只保留小细胞
    small_cells_mask = np.zeros_like(gray)
    
    for i in range(1, num_labels):  # 跳过背景
        width = stats[i, cv2.CC_STAT_WIDTH]
        height = stats[i, cv2.CC_STAT_HEIGHT]
        
        # 检查是否为小目标
        if max(width, height) < cell_pixel_threshold:
            x = stats[i, cv2.CC_STAT_LEFT]
            y = stats[i, cv2.CC_STAT_TOP]
            area = stats[i, cv2.CC_STAT_AREA]
            
            # 获取连通区域掩码
            component_mask = np.zeros_like(gray)
            component_mask[labels == i] = 255
            
            # 扩展掩码
            kernel = np.ones((3, 3), np.uint8)
            dilated_mask = cv2.dilate(component_mask, kernel, iterations=1)
            
            # 添加到总掩码
            small_cells_mask = cv2.bitwise_or(small_cells_mask, dilated_mask)
    
    # 应用边缘增强
    edges = cv2.Canny(gray, 50, 150)
    edges = cv2.dilate(edges, np.ones((2,2), np.uint8))
    
    # 合并小细胞掩码和边缘
    combined_mask = cv2.bitwise_or(small_cells_mask, edges)
    combined_mask = cv2.GaussianBlur(combined_mask, (3,3), 0)
    
    # 创建增强图像
    enhanced_img = image.copy()
    
    # 对掩码区域应用局部对比度增强
    mask_regions = np.where(combined_mask > 0)
    if len(mask_regions[0]) > 0:
        # 提取ROI
        min_y, max_y = np.min(mask_regions[0]), np.max(mask_regions[0])
        min_x, max_x = np.min(mask_regions[1]), np.max(mask_regions[1])
        
        # 确保ROI有效
        if min_y < max_y and min_x < max_x:
            roi = enhanced_img[min_y:max_y+1, min_x:max_x+1].copy()
            
            # 应用局部增强
            roi_lab = cv2.cvtColor(roi, cv2.COLOR_RGB2LAB)
            l, a, b = cv2.split(roi_lab)
            
            # 增强亮度通道
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(3, 3))
            l_enhanced = clahe.apply(l)
            
            # 锐化
            kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
            l_enhanced = cv2.filter2D(l_enhanced, -1, kernel)
            
            # 合并通道
            roi_lab_enhanced = cv2.merge([l_enhanced, a, b])
            roi_enhanced = cv2.cvtColor(roi_lab_enhanced, cv2.COLOR_LAB2RGB)
            
            # 将增强的ROI放回原图
            enhanced_img[min_y:max_y+1, min_x:max_x+1] = roi_enhanced
    
    return enhanced_img
