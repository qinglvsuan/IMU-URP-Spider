"""
ocr_worker.py — 验证码识别子进程入口

用法（由主进程通过 subprocess 调用）：
    python ocr_worker.py <base64_encoded_image>

子进程加载 ddddocr ONNX 模型，识别后将结果打印到 stdout，
然后进程退出，操作系统完整回收所有内存（包含 ONNX C++ runtime 层）。
这样主进程永远不会被 ONNX 权重污染。

OCR 依赖被安装在独立路径（/app/ocr_packages），由 OCR_PYTHONPATH 环境变量指定，
不污染主应用的 site-packages，是镜像瘦身的关键。
"""

import sys
import os

# 注入 OCR 专属包路径（多阶段构建时，OCR 依赖被隔离在这里）
ocr_path = os.environ.get("OCR_PYTHONPATH", "")
if ocr_path and ocr_path not in sys.path:
    sys.path.insert(0, ocr_path)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("", end="")
        sys.exit(0)

    try:
        import base64
        image_b64 = sys.argv[1]
        image_bytes = base64.b64decode(image_b64)

        import ddddocr
        ocr = ddddocr.DdddOcr(show_ad=False)
        result = ocr.classification(image_bytes)
        print(result, end="")
    except Exception as e:
        # 识别失败时输出空字符串，让主进程安全继续
        print("", end="")
        sys.exit(1)
