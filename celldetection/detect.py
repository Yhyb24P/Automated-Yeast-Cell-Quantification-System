#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
酵母细胞检测推理接口

提供模型推理的命令行接口和检测函数。
"""

import os
import torch
import cv2
import numpy as np
import argparse
from pathlib import Path
import matplotlib.pyplot as plt
from tqdm import tqdm
import albumentations as A
from albumentations.pytorch import ToTensorV2
from typing import List, Tuple, Dict, Union, Optional

# 导入自定义模块
from models.detector import YeastCellDetector
from celldetection.enhance import enhance_microscopy_image

def load_model(model_path: str, device: torch.device, num_classes: int = 1) -> YeastCellDetector:
    """加载模型
    
    Args:
        model_path: 模型路径
        device: 设备
        num_classes: 类别数量
        
    Returns:
        加载的模型
    """
    # 加载模型权重
    checkpoint = torch.load(model_path, map_location=device)
    
    # 创建模型
    model = YeastCellDetector(num_classes=num_classes).to(device)
    model.load_state_dict(checkpoint['model_state_dict'])
    
    # 设置为评估模式
    model.eval()
    
    return model

def preprocess_image(image_path: str, img_size: int, use_enhancement: bool = True) -> Tuple[torch.Tensor, np.ndarray, np.ndarray]:
    """预处理图像
    
    Args:
        image_path: 图像路径
        img_size: 输入图像大小
        use_enhancement: 是否使用增强
        
    Returns:
        预处理后的图像张量, 原始图像, 增强后的图像
    """
    # 读取图像
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"无法读取图像: {image_path}")
    
    # 转换为RGB
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    
    # 保存原始图像
    orig_image = image.copy()
    
    # 增强图像
    if use_enhancement:
        enhanced_image = enhance_microscopy_image(image)
    else:
        enhanced_image = image.copy()
    
    # 应用变换
    transform = A.Compose([
        A.Resize(img_size, img_size),
        A.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ToTensorV2()
    ])
    
    transformed = transform(image=enhanced_image)
    image_tensor = transformed['image'].unsqueeze(0)  # 添加批次维度
    
    return image_tensor, orig_image, enhanced_image

def post_process(prediction: torch.Tensor, threshold: float = 0.5) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """后处理预测结果
    
    Args:
        prediction: 模型预测结果
        threshold: 置信度阈值
        
    Returns:
        边界框, 置信度, 类别
    """
    # 提取边界框, 置信度和类别
    boxes = prediction[:, 0:4].cpu().numpy()  # [x1, y1, x2, y2]
    scores = torch.sigmoid(prediction[:, 4]).cpu().numpy()  # [conf]
    
    # 应用阈值
    mask = scores > threshold
    filtered_boxes = boxes[mask]
    filtered_scores = scores[mask]
    
    # 如果有类别预测，也提取类别
    if prediction.shape[1] > 5:
        class_scores = prediction[:, 5:].cpu().numpy()
        filtered_class_ids = np.argmax(class_scores[mask], axis=1)
    else:
        filtered_class_ids = np.zeros(len(filtered_boxes), dtype=np.int32)
    
    # 应用非极大值抑制
    keep_indices = nms(filtered_boxes, filtered_scores, iou_threshold=0.5)
    
    return (
        filtered_boxes[keep_indices],
        filtered_scores[keep_indices],
        filtered_class_ids[keep_indices]
    )

def nms(boxes: np.ndarray, scores: np.ndarray, iou_threshold: float = 0.5) -> List[int]:
    """非极大值抑制
    
    Args:
        boxes: 边界框 [N, 4]
        scores: 置信度 [N]
        iou_threshold: IoU阈值
        
    Returns:
        保留的边界框索引
    """
    # 如果没有边界框，直接返回空列表
    if len(boxes) == 0:
        return []
    
    # 初始化选中的索引列表
    keep = []
    
    # 获取边界框坐标
    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 2]
    y2 = boxes[:, 3]
    
    # 计算边界框面积
    areas = (x2 - x1) * (y2 - y1)
    
    # 按照分数降序排序
    order = scores.argsort()[::-1]
    
    # 循环处理每个边界框
    while order.size > 0:
        # 取当前最高分数的边界框
        i = order[0]
        keep.append(i)
        
        # 获取当前边界框与剩余边界框的重叠区域
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        
        # 计算重叠区域宽高
        w = np.maximum(0.0, xx2 - xx1)
        h = np.maximum(0.0, yy2 - yy1)
        
        # 计算重叠区域面积
        inter = w * h
        
        # 计算IoU
        iou = inter / (areas[i] + areas[order[1:]] - inter)
        
        # 获取IoU小于阈值的边界框索引
        inds = np.where(iou <= iou_threshold)[0]
        
        # 更新order
        order = order[inds + 1]
    
    return keep

def draw_predictions(
    image: np.ndarray,
    boxes: np.ndarray,
    scores: np.ndarray,
    class_ids: np.ndarray,
    output_path: Optional[str] = None,
    line_thickness: int = 2
) -> np.ndarray:
    """绘制预测结果
    
    Args:
        image: 输入图像
        boxes: 边界框 [N, 4] (x1, y1, x2, y2)，值在[0,1]范围内
        scores: 置信度 [N]
        class_ids: 类别ID [N]
        output_path: 输出路径
        line_thickness: 线条粗细
        
    Returns:
        标注后的图像
    """
    # 复制图像以防修改原图
    image_with_boxes = image.copy()
    
    # 图像高度和宽度
    height, width = image.shape[:2]
    
    # 颜色映射
    colors = [
        (0, 255, 0),    # 绿色 - 默认
        (255, 0, 0),    # 红色 - 类别0
        (0, 0, 255),    # 蓝色 - 类别1
        (255, 255, 0),  # 黄色 - 类别2
        (255, 0, 255),  # 洋红 - 类别3
    ]
    
    # 绘制每个检测结果
    for box, score, class_id in zip(boxes, scores, class_ids):
        # 将边界框坐标转换为像素坐标
        x1, y1, x2, y2 = box
        x1 = int(x1 * width)
        y1 = int(y1 * height)
        x2 = int(x2 * width)
        y2 = int(y2 * height)
        
        # 选择颜色
        color = colors[int(class_id) + 1] if int(class_id) < len(colors) - 1 else colors[0]
        
        # 绘制边界框
        cv2.rectangle(image_with_boxes, (x1, y1), (x2, y2), color, line_thickness)
        
        # 绘制置信度分数
        label = f"{score:.2f}"
        text_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(image_with_boxes, (x1, y1 - text_size[1] - 5), (x1 + text_size[0], y1), color, -1)
        cv2.putText(image_with_boxes, label, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    
    # 保存结果
    if output_path:
        # 确保目录存在
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        # 转换为BGR并保存
        cv2.imwrite(output_path, cv2.cvtColor(image_with_boxes, cv2.COLOR_RGB2BGR))
    
    return image_with_boxes

def process_single_image(
    model: YeastCellDetector,
    image_path: str,
    output_dir: str,
    img_size: int,
    threshold: float,
    device: torch.device,
    use_enhancement: bool = True
) -> Dict[str, List]:
    """处理单个图像
    
    Args:
        model: 模型
        image_path: 图像路径
        output_dir: 输出目录
        img_size: 图像大小
        threshold: 置信度阈值
        device: 设备
        use_enhancement: 是否使用增强
        
    Returns:
        检测结果
    """
    # 预处理图像
    image_tensor, orig_image, enhanced_image = preprocess_image(
        image_path, img_size, use_enhancement=use_enhancement
    )
    
    # 推理
    with torch.no_grad():
        predictions = model(image_tensor.to(device))[0]
    
    # 后处理
    boxes, scores, class_ids = post_process(predictions, threshold)
    
    # 准备输出路径
    output_path = os.path.join(output_dir, f"{Path(image_path).stem}_detected.png")
    enhanced_path = os.path.join(output_dir, f"{Path(image_path).stem}_enhanced.png")
    
    # 保存增强后的图像
    if use_enhancement:
        # 转换为BGR并保存
        cv2.imwrite(enhanced_path, cv2.cvtColor(enhanced_image, cv2.COLOR_RGB2BGR))
    
    # 绘制检测结果
    result_image = draw_predictions(orig_image, boxes, scores, class_ids, output_path)
    
    # 输出检测结果信息
    detection_results = {
        'boxes': boxes.tolist(),
        'scores': scores.tolist(),
        'class_ids': class_ids.tolist(),
        'count': len(boxes)
    }
    
    return detection_results

def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='酵母细胞检测推理')
    
    # 输入输出参数
    parser.add_argument('--model', type=str, required=True,
                       help='模型路径')
    parser.add_argument('--input', type=str, required=True,
                       help='输入图像路径或目录')
    parser.add_argument('--output', type=str, default='detection_results',
                       help='输出目录')
    
    # 模型参数
    parser.add_argument('--img-size', type=int, default=224,
                       help='输入图像大小')
    parser.add_argument('--threshold', type=float, default=0.5,
                       help='检测阈值')
    parser.add_argument('--num-classes', type=int, default=1,
                       help='类别数量')
    
    # 其他参数
    parser.add_argument('--device', type=str, default='cuda',
                       help='使用设备 (cuda/cpu)')
    parser.add_argument('--no-enhance', action='store_true',
                       help='不使用图像增强')
    
    return parser.parse_args()

def main():
    """主函数"""
    args = parse_args()
    
    # 设置设备
    device = torch.device(args.device if torch.cuda.is_available() and args.device == 'cuda' else 'cpu')
    print(f"使用设备: {device}")
    
    # 设置输出目录
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 加载模型
    try:
        model = load_model(args.model, device, args.num_classes)
        print(f"成功加载模型: {args.model}")
    except Exception as e:
        print(f"加载模型失败: {str(e)}")
        return
    
    # 获取图像路径列表
    input_path = Path(args.input)
    if input_path.is_dir():
        image_paths = list(input_path.glob('*.jpg')) + list(input_path.glob('*.jpeg')) + \
                     list(input_path.glob('*.png')) + list(input_path.glob('*.bmp'))
        print(f"找到 {len(image_paths)} 张图像")
    else:
        image_paths = [input_path]
    
    # 处理每张图像
    results = {}
    
    for image_path in tqdm(image_paths, desc="处理图像"):
        try:
            result = process_single_image(
                model,
                str(image_path),
                str(output_dir),
                args.img_size,
                args.threshold,
                device,
                use_enhancement=not args.no_enhance
            )
            
            results[image_path.name] = {
                'count': len(result['boxes']),
                'scores': [round(score, 3) for score in result['scores']]
            }
            
            print(f"图像 {image_path.name}: 检测到 {len(result['boxes'])} 个细胞")
            
        except Exception as e:
            print(f"处理图像 {image_path.name} 失败: {str(e)}")
    
    # 保存结果摘要
    from datetime import datetime
    import json
    
    summary = {
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'model': args.model,
        'threshold': args.threshold,
        'total_images': len(image_paths),
        'total_cells': sum(r['count'] for r in results.values()),
        'results': results
    }
    
    with open(output_dir / 'detection_summary.json', 'w') as f:
        json.dump(summary, f, indent=2)
    
    print(f"检测完成. 结果已保存到 {output_dir}")
    print(f"总共检测到 {summary['total_cells']} 个细胞")

if __name__ == "__main__":
    main()
