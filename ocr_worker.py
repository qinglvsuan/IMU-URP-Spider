"""
ocr_worker.py — 验证码识别子进程入口

用法（由主进程通过 subprocess 调用）：
    python ocr_worker.py <base64_encoded_image>

子进程加载 ddddocr ONNX 模型，识别后将结果打印到 stdout，
然后进程退出，操作系统完整回收所有内存（包含 ONNX C++ runtime 层）。
这样主进程永远不会被 ONNX 权重污染。
"""

import sys
import base64

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("", end="")
        sys.exit(0)

    try:
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
