#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
图像增强主接口

为显微镜下的酵母细胞图像提供统一的增强接口。
支持多种增强方法和批量处理。
"""

import os
import cv2
import numpy as np
from pathlib import Path
from typing import Union, List, Tuple, Optional, Dict, Any

from .adaptive import enhance_microscopy_image
from .clahe import apply_clahe, adaptive_clahe
from .small_cell import enhance_small_cells

def enhance_image(
    image: Union[np.ndarray, str],
    method: str = 'adaptive',
    small_cell_enhancement: bool = True,
    denoise_level: int = 5,
    params: Optional[Dict[str, Any]] = None
) -> np.ndarray:
    """增强单个图像
    
    Args:
        image: 输入图像或图像路径
        method: 增强方法 ('adaptive', 'clahe', 'guided', 'basic')
        small_cell_enhancement: 是否应用小细胞增强
        denoise_level: 降噪强度 (0-10)，0表示不降噪
        params: 额外的方法特定参数
        
    Returns:
        增强后的图像
    """
    # 处理输入
    if isinstance(image, str):
        img = cv2.imread(image)
        if img is None:
            raise ValueError(f"无法读取图像: {image}")
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    else:
        img = image.copy()
    
    # 默认参数
    if params is None:
        params = {}
    
    # 根据选择的方法进行增强
    if method == 'adaptive':
        enhanced = enhance_microscopy_image(img)
    elif method == 'clahe':
        clip_limit = params.get('clip_limit', 2.0)
        tile_grid_size = params.get('tile_grid_size', (8, 8))
        enhanced = apply_clahe(img, clip_limit, tile_grid_size)
    elif method == 'adaptive_clahe':
        low_contrast_threshold = params.get('low_contrast_threshold', 30)
        min_clip_limit = params.get('min_clip_limit', 1.0)
        max_clip_limit = params.get('max_clip_limit', 4.0)
        enhanced = adaptive_clahe(img, low_contrast_threshold, min_clip_limit, max_clip_limit)
    elif method == 'guided':
        # 简化的引导滤波增强
        from .guided_filter import guided_filter
        enhanced = img.copy()
        radius = params.get('radius', 2)
        eps = params.get('eps', 0.2)
        for i in range(3):
            enhanced[:, :, i] = guided_filter(enhanced[:, :, i], enhanced[:, :, i], radius, eps)
    elif method == 'basic':
        # 基础增强 - 简单的对比度和亮度调整
        alpha = params.get('alpha', 1.2)  # 对比度
        beta = params.get('beta', 10)     # 亮度
        enhanced = cv2.convertScaleAbs(img, alpha=alpha, beta=beta)
    else:
        raise ValueError(f"不支持的增强方法: {method}")
    
    # 是否应用小细胞增强
    if small_cell_enhancement:
        cell_size_threshold = params.get('cell_size_threshold', 0.005)
        enhanced = enhance_small_cells(enhanced, cell_size_threshold)
    
    # 是否应用降噪
    if denoise_level > 0:
        h_param = denoise_level
        enhanced = cv2.fastNlMeansDenoisingColored(
            enhanced, None, 
            h=h_param, 
            hColor=h_param, 
            templateWindowSize=7, 
            searchWindowSize=21
        )
    
    return enhanced

def enhance_images_batch(
    input_paths: Union[str, List[str]],
    output_dir: str,
    method: str = 'adaptive',
    small_cell_enhancement: bool = True,
    denoise_level: int = 5,
    create_comparison: bool = True,
    params: Optional[Dict[str, Any]] = None
) -> List[str]:
    """批量增强图像
    
    Args:
        input_paths: 输入图像路径(单个路径、目录或路径列表)
        output_dir: 输出目录
        method: 增强方法
        small_cell_enhancement: 是否应用小细胞增强
        denoise_level: 降噪强度
        create_comparison: 是否创建对比图
        params: 额外参数
        
    Returns:
        增强后图像的路径列表
    """
    # 解析输入路径
    image_paths = []
    if isinstance(input_paths, str):
        if os.path.isdir(input_paths):
            # 是目录，获取所有图像
            input_dir = Path(input_paths)
            for ext in ['.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff']:
                image_paths.extend(list(input_dir.glob(f'*{ext}')))
                image_paths.extend(list(input_dir.glob(f'*{ext.upper()}')))
        else:
            # 单个文件
            image_paths = [input_paths]
    else:
        # 路径列表
        image_paths = input_paths
    
    if not image_paths:
        raise ValueError(f"未找到图像文件")
    
    # 确保输出目录存在
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 处理每张图像
    output_paths = []
    
    for img_path in image_paths:
        try:
            # 读取图像
            img_path = str(img_path)
            image = cv2.imread(img_path)
            if image is None:
                print(f"警告: 无法读取图像 {img_path}")
                continue
            
            # 转换为RGB
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            
            # 应用增强
            enhanced = enhance_image(
                image,
                method=method,
                small_cell_enhancement=small_cell_enhancement,
                denoise_level=denoise_level,
                params=params
            )
            
            # 准备输出路径
            filename = os.path.basename(img_path)
            name, ext = os.path.splitext(filename)
            output_path = output_dir / f"{name}_enhanced{ext}"
            
            # 转回BGR并保存
            enhanced_bgr = cv2.cvtColor(enhanced, cv2.COLOR_RGB2BGR)
            cv2.imwrite(str(output_path), enhanced_bgr)
            output_paths.append(str(output_path))
            
            # 创建对比图
            if create_comparison:
                comparison = np.concatenate([cv2.cvtColor(image, cv2.COLOR_RGB2BGR), enhanced_bgr], axis=1)
                comparison_path = output_dir / f"{name}_comparison{ext}"
                cv2.imwrite(str(comparison_path), comparison)
                
            print(f"图像 {filename} 增强完成")
            
        except Exception as e:
            print(f"处理图像 {img_path} 时出错: {str(e)}")
            import traceback
            traceback.print_exc()
    
    return output_paths
